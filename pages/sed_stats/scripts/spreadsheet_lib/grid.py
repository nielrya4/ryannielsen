"""Tabulator-backed spreadsheet macro."""
import js

from antioch.elements import Div
from antioch.macros.js_library import JSLibraryMacro

# Row operations run entirely in JS. Tabulator's row and cell components must
# never reach Python: Pyodide probes an incoming object for `next`, `get`,
# `has` and friends to decide how to wrap it, and Tabulator's components warn
# loudly on every unknown property. Doing the component work here and handing
# back only a count keeps that boundary clean.
_ROW_OPS_ID = "spreadsheet-lib-row-ops"
_ROW_OPS_NAME = "__sedStatsRowOps"
_ROW_OPS = """
window.__sedStatsRowOps = {
  deleteSelected: function (table) {
    var doomed = new Set();
    (table.getRanges() || []).forEach(function (range) {
      (range.getRows() || []).forEach(function (row) { doomed.add(row); });
    });
    doomed.forEach(function (row) { row.delete(); });
    return doomed.size;
  },
  insertBelowSelection: function (table, blank) {
    var rows = [];
    (table.getRanges() || []).forEach(function (range) {
      (range.getRows() || []).forEach(function (row) { rows.push(row); });
    });
    if (!rows.length) { table.addRow(blank); return 1; }
    var last = rows[rows.length - 1];
    table.addRow(blank, false, last);
    return 1;
  }
};
"""


def _ensure_row_ops():
    # Not `is None`: Pyodide represents JS null as a `jsnull` sentinel, which
    # is not Python None, so `is None` is always False and the script would
    # never be injected. Truthiness is correct for both null and a real node.
    if not js.document.getElementById(_ROW_OPS_ID):
        script = js.document.createElement("script")
        script.id = _ROW_OPS_ID
        script.textContent = _ROW_OPS
        js.document.head.appendChild(script)

    if not hasattr(js.window, _ROW_OPS_NAME):
        raise RuntimeError(
            "the spreadsheet row helper script did not run — "
            "check the browser console for a script error")


def _row_ops():
    """
    The row-ops shim, fetched by name.

    Not `js.window.__sedStatsRowOps`: inside a class body Python mangles any
    leading-double-underscore attribute, so that expression silently becomes
    `js.window._TabulatorSheet__sedStatsRowOps`. getattr sidesteps the rewrite.
    """
    return getattr(js.window, _ROW_OPS_NAME)


class TabulatorSheet(JSLibraryMacro):
    """
    Editable spreadsheet backed by the Tabulator JS library.

    Usage:
        sheet = TabulatorSheet(data=[{"a": 1, "b": 2}], height="400px")
        DOM.add(sheet.element)

        @when(sheet.events.data_change)
        def on_change(sender, data):
            ...
    """

    def __init__(self, data=None, columns=None, height="400px", options=None,
                 editable=True, sortable=True, **kwargs):
        """
        Args:
            data: List of row dicts
            columns: Tabulator column definitions; if None, columns are
                     auto-generated from the data (and regenerate on set_data)
            height: CSS height of the table; falsy sizes to content
            options: Extra Tabulator options merged over the defaults
            editable: Whether auto-generated columns accept typing
            sortable: Whether auto-generated columns sort on their header
        """
        super().__init__(macro_type="tabulator_sheet", **kwargs)

        self._set_state(
            data=data or [],
            columns=columns,
            height=height,
            options=options or {},
            editable=editable,
            sortable=sortable,
        )

        self._create_event('data_change')

        # Tabulator's constructor returns before the table exists: it builds
        # asynchronously and announces itself with `tableBuilt`. Anything that
        # touches the rendered table has to wait for that, so a redraw asked
        # for too early is remembered rather than thrown at a half-built table.
        self._built = False
        self._pending_redraw = False

        self._init_macro()

    def _get_library_dependencies(self):
        return {
            'scripts': ['antioch/lib/vendor/tabulator.min.js'],
            'stylesheets': ['antioch/lib/vendor/tabulator.min.css'],
        }

    def _get_library_global_name(self):
        return 'Tabulator'

    def _create_elements(self):
        container = self._register_element(
            'container', self._create_container({"width": "100%"})
        )
        holder = self._register_element('holder', Div())
        holder.set_attribute("id", f"tabulator_{self._id}")
        container.add(holder)
        return container

    def _column_definitions(self):
        columns = self._get_state('columns')
        if columns:
            return columns
        fields = []
        for row in self._get_state('data'):
            for key in row:
                if key not in fields:
                    fields.append(key)
        column = {'headerSort': self._get_state('sortable'), 'minWidth': 110}
        if self._get_state('editable'):
            column['editor'] = 'input'
            # Open with the existing value selected, so typing replaces it.
            # Editing already costs a double-click, and someone who has gone
            # to that trouble usually means to overwrite the cell rather than
            # append to it; one more click puts the caret where they want.
            column['editorParams'] = {'selectContents': True}
        return [{'title': field, 'field': field, **column} for field in fields]

    def _build_options(self):
        options = {
            'data': self._get_state('data'),
            'layout': 'fitColumns',
            'columns': self._column_definitions(),
            # A row-number gutter, as a spreadsheet has. With row selection on,
            # Tabulator's range module otherwise claims the first visible
            # column as its row header — skipping it in every range and
            # dropping it from the copy. Its own column keeps the first data
            # column being data.
            'rowHeader': {
                'formatter': 'rownum',
                'hozAlign': 'center',
                'headerSort': False,
                'resizable': False,
                'frozen': True,
                'width': 44,
            },
            'nestedFieldSeparator': False,
            'selectableRange': True,
            'selectableRangeColumns': True,
            'selectableRangeRows': True,
            'selectableRangeClearCells': self._get_state('editable'),
            'clipboard': True,
            'clipboardCopyRowRange': 'range',
            'clipboardCopyConfig': {'columnHeaders': True, 'rowHeaders': False},
            'clipboardPasteParser': 'range',
            'clipboardPasteAction': 'range',
            # Single click selects, so editing needs the second one — the
            # spreadsheet convention, and the only way both gestures fit.
            'editTriggerEvent': 'dblclick',
            'editorEmptyValue': None,
            # Tabulator warns that a sortable header and column range selection
            # fight over the same click; confining sorting to the icon is the
            # resolution it recommends.
            'headerSortClickElement': 'icon',
        }
        height = self._get_state('height')
        if height:
            options['height'] = height
        options.update(self._get_state('options'))
        return options

    def _create_js_instance(self):
        _ensure_row_ops()
        holder = self._get_element('holder')
        table = js.Tabulator.new(holder._dom_element, self._to_js(self._build_options()))
        # dataChanged passes the plain data array; Tabulator components (cell,
        # row) must never cross into Python — Pyodide's capability probes
        # trigger Tabulator's unknown-property warnings.
        table.on('dataChanged', self._create_proxy(self._handle_data_changed))
        table.on('tableBuilt', self._create_proxy(self._handle_table_built))
        return table

    def _handle_table_built(self, *args):
        self._built = True
        if self._pending_redraw:
            self._pending_redraw = False
            self.redraw()

    def _handle_data_changed(self, data):
        rows = data.to_py()
        self._set_state(data=rows)
        self._fire_event('data_change', rows)

    # ========== Public API ==========

    def get_data(self):
        """Current table contents as a list of row dicts."""
        if not self.is_initialized:
            return list(self._get_state('data'))
        return self.js_instance.getData().to_py()

    def set_data(self, data):
        """Replace table contents, regenerating auto columns from the new data."""
        self._set_state(data=data)
        if self.is_initialized:
            if not self._get_state('columns'):
                self.js_instance.setColumns(self._to_js(self._column_definitions()))
            self.js_instance.setData(self._to_js(data))
        self._fire_event('data_change', data)
        return self

    def add_row(self):
        """Insert a blank row below the selection, or at the end if none."""
        if not self.is_initialized:
            return self
        blank = {field: "" for field in self._fields()}
        _row_ops().insertBelowSelection(
            self.js_instance, self._to_js(blank))
        self._sync_after_row_change()
        return self

    def delete_selected_rows(self):
        """
        Remove every row touched by the current selection.

        Returns the number deleted, so a caller can say nothing was selected
        rather than silently doing nothing.
        """
        if not self.is_initialized:
            return 0
        removed = int(_row_ops().deleteSelected(self.js_instance))
        if removed:
            self._sync_after_row_change()
        return removed

    def _fields(self):
        """Column field names, from explicit columns or the current data."""
        columns = self._get_state('columns')
        if columns:
            return [c['field'] for c in columns if 'field' in c]
        fields = []
        for row in self._get_state('data'):
            for key in row:
                if key not in fields:
                    fields.append(key)
        return fields

    def _sync_after_row_change(self):
        """Adding or deleting a row does not fire Tabulator's dataChanged."""
        rows = self.js_instance.getData().to_py()
        self._set_state(data=rows)
        self._fire_event('data_change', rows)

    def redraw(self):
        """Recompute layout. Needed after the table becomes visible again:
        Tabulator sizes itself on render and measures zero while hidden."""
        if not self.is_initialized:
            return self
        if not self._built:
            self._pending_redraw = True
            return self
        try:
            self.js_instance.redraw(True)
        except Exception:
            # A table torn down between the request and the call has nothing
            # to redraw, and a failed relayout is never worth an error box.
            pass
        return self

    @property
    def is_ready(self):
        return self.is_initialized