"""
Result tables, as read-only Tabulator sheets.

Outputs are read, selected through and copied out of — a comparison matrix goes
into a paper, a contribution table into a caption — so they get a real grid
rather than a static <table>: range selection and clipboard copy.

Every column is data, including the first. Sample names are a measured column
like any other and are selected, copied and aligned on the same terms, rather
than being treated as a row header the grid draws differently.

Editing is off throughout. These cells are computed; typing into one would
change nothing and imply otherwise.
"""
import js

from antioch.elements import Div
from spreadsheet_lib import TabulatorSheet

# Fields are generated rather than taken from the titles. A Tabulator field
# containing a dot is a nested-property accessor, and sample names are free to
# contain anything at all.
FIELD_PREFIX = "c"

ROW_HEIGHT = 30
HEADER_HEIGHT = 40
# Past this many rows the sheet scrolls rather than growing; a per-sample
# table stays short, but nothing stops someone loading forty samples.
MAX_VISIBLE_ROWS = 14


# Cells that stand in for a value rather than being one. A column of these
# plus numbers is still a numeric column.
PLACEHOLDERS = {"", "—", "-", "n/a", "na", "nan"}


def _is_numeric(value) -> bool:
    text = str(value).strip()
    if text.lower() in PLACEHOLDERS:
        return True
    try:
        float(text.replace(",", ""))
    except ValueError:
        return False
    return True


def _alignment(values) -> str:
    """
    Right-align a column of numbers, left-align anything else.

    Decided from what a column holds rather than where it sits, so the first
    column is aligned by the same rule as the rest. A column of all
    placeholders has nothing to align on and reads fine either way.
    """
    if any(str(v).strip().lower() not in PLACEHOLDERS for v in values) and \
            all(_is_numeric(v) for v in values):
        return "right"
    return "left"


def result_table(titles, rows, sortable=False):
    """
    A read-only sheet.

    Args:
        titles: column headings
        rows: one list of cell values per row, matching `titles` in length
        sortable: header sorting. Off by default — a comparison matrix's rows
            and columns have to stay in the same order to read as a matrix,
            and every table here shares the plot's sample order.

    Returns:
        A Div wrapping the sheet, with `.sheet` on it for the caller.
    """
    fields = [f"{FIELD_PREFIX}{index}" for index in range(len(titles))]
    columns = []
    for index, (field, title) in enumerate(zip(fields, titles)):
        column_values = [row[index] if index < len(row) else "" for row in rows]
        columns.append({
            "title": str(title),
            "field": field,
            "headerSort": sortable,
            "headerHozAlign": "center",
            "hozAlign": _alignment(column_values),
            "minWidth": 90,
        })

    data = [dict(zip(fields, ["" if v is None else v for v in row]))
            for row in rows]

    visible = min(len(data), MAX_VISIBLE_ROWS)
    height = (HEADER_HEIGHT + visible * ROW_HEIGHT + 2
              if len(data) > MAX_VISIBLE_ROWS else None)

    sheet = TabulatorSheet(
        data=data,
        columns=columns,
        height=f"{height}px" if height else None,
        options={
            "layout": "fitDataFill",
            # Sample names may contain dots; without this Tabulator would read
            # them as nested-property paths and find nothing.
            "nestedFieldSeparator": False,
            "movableColumns": False,
            # A row-number gutter, as a spreadsheet has. It is not decoration:
            # with row selection on, Tabulator's range module claims the first
            # visible column as its row header — skipping it in every range
            # (`start.col = 1`) and dropping it from the copy. Giving it a
            # column of its own is what keeps the first *data* column being
            # data, selectable and copied like the rest.
            "rowHeader": {
                "formatter": "rownum",
                "hozAlign": "center",
                "headerSort": False,
                "resizable": False,
                "frozen": True,
                "width": 44,
            },
            # The point of a grid over a static table: select a block of
            # results and paste it somewhere useful.
            "selectableRange": True,
            "selectableRangeColumns": True,
            "selectableRangeRows": True,
            "clipboard": "copy",
            "clipboardCopyRowRange": "range",
            # Column headings travel with the copy; the row-number gutter does
            # not, since it is numbering rather than data.
            "clipboardCopyConfig": {"columnHeaders": True, "rowHeaders": False},
            "placeholder": "Nothing to show",
        },
    )

    _ensure_css()
    wrapper = Div(sheet.element, style={"max-width": "100%"})
    wrapper.sheet = sheet
    _redraw_when_shown(sheet, wrapper)
    return wrapper


def _redraw_when_shown(sheet, wrapper):
    """
    Redraw the sheet the first time it has a size.

    Tabulator measures itself on render. A table built inside a hidden tab —
    every tab but the first, in a multi-dimension output — measures zero and
    draws as an empty strip. Watching for the element gaining width fixes it
    wherever it is mounted, without the gallery or the tab view needing to
    know a table is in there.
    """
    element = wrapper._dom_element

    def on_resize(entries, observer):
        # Nothing here may raise: this runs from a browser callback, where an
        # exception surfaces as an uncaught error rather than anything useful.
        try:
            if element.offsetWidth > 0:
                sheet.redraw()
        except Exception:
            pass

    try:
        observer = js.ResizeObserver.new(sheet._create_proxy(on_resize))
        observer.observe(element)
        # Held on the macro so the proxy and observer outlive this call.
        sheet._result_observer = observer
    except Exception:
        # Without ResizeObserver the table still renders; it just may need a
        # tab switch to size itself.
        pass


_CSS_ID = "dashboard-result-table-css"
_CSS = """
.tabulator .tabulator-header { border-bottom: 2px solid #b8b2a8; }
.tabulator .tabulator-col { background-color: #f6f3ee; }
"""


def _ensure_css():
    # Not `is None`: Pyodide represents JS null as a `jsnull` sentinel, so
    # `is None` never matched and this re-injected the style on every call.
    if not js.document.getElementById(_CSS_ID):
        style = js.document.createElement("style")
        style.id = _CSS_ID
        style.textContent = _CSS
        js.document.head.appendChild(style)
