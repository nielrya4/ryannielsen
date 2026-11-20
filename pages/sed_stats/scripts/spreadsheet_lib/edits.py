"""
The edits a spreadsheet can make, on plain data: rows as dicts, and the order of the columns.

Nothing here touches the page, so every rule — what pasting past the last row does, how a new
column is named — can be tested. The grid (`grid.py`) asks for an edit, gets back the new rows and
column order, and shows them. No function changes what it was given.

A cell is a string, a number or "": an emptied cell is "", not None, so an empty cell reads the same
whether it was never filled or was cleared.
"""
import csv
import io


def columns_of(rows, order=()):
    """The column order: `order` first, then any key a row has that it does not list."""
    columns = [c for c in order]
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def blank_row(columns):
    return {column: "" for column in columns}


def unique_name(wanted, existing, fallback="column"):
    """`wanted` if it is free, else with _2, _3… added; `fallback` for a blank one."""
    base = str(wanted or "").strip() or fallback
    if base not in existing:
        return base
    n = 2
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


def next_column_name(columns):
    """column_1, column_2, … the first not in use (counting from the number of columns)."""
    n = len(columns) + 1
    while f"column_{n}" in columns:
        n += 1
    return f"column_{n}"


# --------------------------------------------------------------------------- rows

def insert_rows(rows, columns, index, count=1):
    """
    `count` blank rows so that the first is at position `index` (0-based; one past the end
    appends).

    Returns:
        the new rows
    """
    index = max(0, min(int(index), len(rows)))
    return rows[:index] + [blank_row(columns) for _ in range(count)] + rows[index:]


def delete_rows(rows, indexes):
    """The rows without those at the given positions (0-based; ones that do not exist are ignored)."""
    doomed = {int(i) for i in indexes}
    return [row for i, row in enumerate(rows) if i not in doomed]


def duplicate_rows(rows, indexes):
    """Each chosen row copied just below itself."""
    chosen = {int(i) for i in indexes}
    out = []
    for i, row in enumerate(rows):
        out.append(row)
        if i in chosen:
            out.append(dict(row))
    return out


# ------------------------------------------------------------------------ columns

def add_column(rows, columns, name=None, index=None):
    """
    A new, empty column.

    Args:
        name: what to call it (made unique; blank gives column_N)
        index: where among the columns (0-based); the end if None

    Returns:
        (rows, columns, the name used)
    """
    name = unique_name(name, columns) if (name or "").strip() else next_column_name(columns)
    position = len(columns) if index is None else max(0, min(int(index), len(columns)))
    new_columns = columns[:position] + [name] + columns[position:]
    return [{**row, name: ""} for row in rows], new_columns, name


def rename_column(rows, columns, old, new):
    """
    Rename a column, keeping its place and its values.

    Raises:
        ValueError: if `old` is not a column, or `new` is blank or already a column
    """
    new = str(new or "").strip()
    if old not in columns:
        raise ValueError(f"There is no column '{old}'.")
    if not new:
        raise ValueError("A column needs a name.")
    if new != old and new in columns:
        raise ValueError(f"There is already a column called '{new}'.")
    renamed = [new if c == old else c for c in columns]
    return [{(new if k == old else k): v for k, v in row.items()} for row in rows], renamed


def delete_columns(rows, columns, fields):
    """The rows and columns without the named columns."""
    gone = set(fields)
    return ([{k: v for k, v in row.items() if k not in gone} for row in rows],
            [c for c in columns if c not in gone])


# ---------------------------------------------------------------------- clipboard

def parse_clipboard(text):
    """
    The cells of text copied from a spreadsheet: tab-separated, a line a row, with a cell that
    holds a tab or a line break wrapped in double quotes (an inner quote doubled), as Excel and
    Google Sheets write it. One trailing line break is the end of the last row, not a blank row.

    Returns:
        [[cell, ...], ...]
    """
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if text.endswith("\n"):
        text = text[:-1]
    if text == "":
        return []
    if '"' not in text:
        return [line.split("\t") for line in text.split("\n")]
    return [list(row) for row in csv.reader(io.StringIO(text), delimiter="\t", quotechar='"')]


def paste_block(rows, columns, cells, row, column_index, fill_rows=1, fill_columns=1):
    """
    Write copied cells into the sheet from a cell, growing it as needed.

    Rows past the last one are added, and columns past the last one are added as column_N, so
    nothing pasted is lost. A single copied value pasted over a larger selection fills the
    whole selection, as a spreadsheet does.

    Args:
        cells: the copied block, from `parse_clipboard`
        row, column_index: the top-left cell, 0-based
        fill_rows, fill_columns: the size of the selection pasted over

    Returns:
        (rows, columns, (first row, first column, rows written, columns written))
    """
    if not cells:
        return rows, columns, (row, column_index, 0, 0)
    if len(cells) == 1 and len(cells[0]) == 1 and (fill_rows > 1 or fill_columns > 1):
        cells = [[cells[0][0]] * fill_columns for _ in range(fill_rows)]
    width = max(len(line) for line in cells)
    rows = [dict(r) for r in rows]
    columns = list(columns)
    while len(columns) < column_index + width:
        columns.append(next_column_name(columns))
        for existing in rows:
            existing[columns[-1]] = ""
    while len(rows) < row + len(cells):
        rows.append(blank_row(columns))
    for i, line in enumerate(cells):
        for j, value in enumerate(line):
            rows[row + i][columns[column_index + j]] = value
    return rows, columns, (row, column_index, len(cells), width)


# ----------------------------------------------------------------------- clearing

def clear_cells(rows, selections):
    """
    The rows with some cells emptied.

    Args:
        selections: [{"rows": [0-based row positions], "fields": [column names]}, ...], one for each
            selected block; a position that is not a row, or a field that is not a column, is
            ignored

    Returns:
        (rows, how many cells were emptied)
    """
    wanted = {}
    for block in selections:
        for index in block.get("rows", []):
            for field in block.get("fields", []):
                wanted.setdefault(int(index), set()).add(field)
    out, count = [], 0
    for i, row in enumerate(rows):
        fields = [f for f in wanted.get(i, ()) if f in row]
        if fields:
            row = {**row, **{f: "" for f in fields}}
            count += len(fields)
        out.append(row)
    return out, count


def to_clipboard(cells):
    """
    Cells as text a spreadsheet reads: tabs between cells, a line for each row, and a cell that
    holds a tab, a line break or a quote wrapped in quotes with inner quotes doubled — the form
    `parse_clipboard` reads back.
    """
    def one(value):
        text = "" if value is None else str(value)
        if any(c in text for c in '\t\n\r"'):
            return '"' + text.replace('"', '""') + '"'
        return text
    return "\n".join("\t".join(one(v) for v in row) for row in cells)
