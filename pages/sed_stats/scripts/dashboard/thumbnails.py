"""
The small pictures on a block: what its output looks like, at a glance.

A graph's thumbnail is its first plot, exported as SVG and shrunk; a table's is drawn here, a few
rows and columns as a miniature grid. Everything is an SVG data URL, which an <img> shows at any
size, so no extra rendering is needed and nothing is kept but the string.
"""
import math
from urllib.parse import quote
from xml.sax.saxutils import escape

# The most rows of a table a table view builds; more are counted and left out.
MAX_TABLE_ROWS = 5000

# Most of a table that a miniature can hold and still be read.
THUMB_COLUMNS = 4
THUMB_ROWS = 5
WIDTH, HEIGHT = 200, 84


def svg_data_url(svg):
    """An SVG markup string as a data URL for <img src>."""
    return "data:image/svg+xml;charset=utf-8," + quote(svg, safe="")


def cell_value(value):
    """
    A cell as the table view shows it: a number to six significant figures (still a number, so it
    sorts as one), "" for nothing, anything else as text.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            if not math.isfinite(value):
                return ""
            return float(f"{value:.6g}")
        return value
    return str(value)


def table_columns(rows, columns=None):
    """The column names of rows: `columns` if given (those that exist), else every key in first-seen order."""
    found = []
    for row in rows:
        for key in row:
            if key not in found:
                found.append(key)
    if columns:
        return [c for c in columns if c in found]
    return found


def table_cells(rows, columns=None, limit=None):
    """
    Rows as the lists of cells a table view takes.

    Returns:
        (titles, cells, total): the column names, at most `limit` rows of cell values, and how many
        rows there were
    """
    titles = table_columns(rows, columns)
    chosen = rows if limit is None else rows[:limit]
    return titles, [[cell_value(row.get(t, "")) for t in titles] for row in chosen], len(rows)


def _short(value, length):
    text = str(value)
    return text if len(text) <= length else text[:length - 1] + "…"


def table_svg(titles, cells, width=WIDTH, height=HEIGHT, max_columns=THUMB_COLUMNS, max_rows=THUMB_ROWS):
    """
    A miniature of a table: its header and first rows, as SVG markup.

    Only the first few columns and rows are drawn; a cell is cut to fit. An empty table is a blank
    grid with its column names, if it has any.
    """
    shown = list(titles)[:max_columns]
    count = max(len(shown), 1)
    row_height = height / (max_rows + 1)
    column_width = width / count
    limit = max(3, int(column_width / 5.2))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}" font-family="sans-serif" font-size="8">',
             f'<rect width="{width}" height="{height}" fill="#fff"/>',
             f'<rect width="{width}" height="{row_height:.1f}" fill="#e9eef3"/>']
    for r in range(max_rows + 1):
        y = r * row_height
        if r and r % 2 == 0:
            parts.append(f'<rect y="{y:.1f}" width="{width}" height="{row_height:.1f}" fill="#f6f8fa"/>')
        parts.append(f'<line x1="0" x2="{width}" y1="{y + row_height:.1f}" y2="{y + row_height:.1f}" '
                     'stroke="#d8dee4" stroke-width="0.6"/>')
    for c, title in enumerate(shown):
        x = c * column_width + 3
        parts.append(f'<text x="{x:.1f}" y="{row_height - 3:.1f}" font-weight="bold" fill="#2c3e50">'
                     f'{escape(_short(title, limit))}</text>')
        for r, row in enumerate(cells[:max_rows]):
            value = row[c] if c < len(row) else ""
            parts.append(f'<text x="{x:.1f}" y="{(r + 2) * row_height - 3:.1f}" fill="#44505c">'
                         f'{escape(_short(value, limit))}</text>')
    if len(titles) > max_columns:
        parts.append(f'<text x="{width - 3}" y="{row_height - 3:.1f}" text-anchor="end" fill="#6c757d">…</text>')
    parts.append("</svg>")
    return "".join(parts)
