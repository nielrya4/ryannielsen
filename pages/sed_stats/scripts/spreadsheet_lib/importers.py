"""Parsers that turn uploaded spreadsheet files into a list of row dicts."""
import csv
import io
from datetime import date, datetime, time

SUPPORTED_EXTENSIONS = (".csv", ".xls", ".xlsx")


def _plain(value):
    """
    A cell as the sheet holds it. An Excel date cell arrives as a datetime; it becomes the text
    "2021-01-16" (or "2021-01-16 13:45:00" with a time), which the date-reading tools understand, the
    grid shows as it is, and a project file can store (a datetime cannot be written to one).
    """
    if isinstance(value, datetime):
        if value.hour or value.minute or value.second or value.microsecond:
            return value.replace(microsecond=0).isoformat(sep=" ")
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.replace(microsecond=0).isoformat()
    return value


def _rows_to_dicts(rows):
    rows = [row for row in rows if any(cell not in (None, "") for cell in row)]
    if not rows:
        return []

    headers = [
        str(header) if header not in (None, "") else f"column_{i + 1}"
        for i, header in enumerate(rows[0])
    ]
    result = []
    for row in rows[1:]:
        padded = list(row) + [""] * (len(headers) - len(row))
        result.append({
            header: "" if value is None else _plain(value)
            for header, value in zip(headers, padded)
        })
    return result


def parse_csv(text: str):
    return _rows_to_dicts(list(csv.reader(io.StringIO(text))))


def parse_xlsx(content: bytes):
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.active
    return _rows_to_dicts([list(row) for row in sheet.iter_rows(values_only=True)])


def _xls_value(book, cell):
    """A cell of an .xls file: a date cell as a datetime (xlrd gives only an Excel serial number)."""
    import xlrd
    if cell.ctype == xlrd.XL_CELL_DATE:
        try:
            return xlrd.xldate.xldate_as_datetime(cell.value, book.datemode)
        except (ValueError, xlrd.xldate.XLDateError):
            return cell.value
    return cell.value


def parse_xls(content: bytes):
    import xlrd

    book = xlrd.open_workbook(file_contents=content)
    sheet = book.sheet_by_index(0)
    return _rows_to_dicts([[_xls_value(book, sheet.cell(i, j)) for j in range(sheet.ncols)]
                           for i in range(sheet.nrows)])


def parse_file(filename: str, content):
    lower = filename.lower()
    if lower.endswith(".csv"):
        return parse_csv(content)
    if lower.endswith(".xlsx"):
        return parse_xlsx(content)
    if lower.endswith(".xls"):
        return parse_xls(content)
    raise ValueError(
        f"Unsupported file type: {filename} (supported: {', '.join(SUPPORTED_EXTENSIONS)})"
    )

def rows_to_csv(rows) -> str:
    """
    Turn row dicts back into CSV text.

    The inverse of `parse_csv`, for handing the grid's contents to something
    that wants a file. Column order follows the first row, with any key a later
    row introduces appended, so a ragged set of rows still round-trips.
    """
    rows = list(rows)
    if not rows:
        return ""

    headers = list(rows[0].keys())
    seen = set(headers)
    for row in rows[1:]:
        for key in row:
            if key not in seen:
                seen.add(key)
                headers.append(key)

    buffer = io.StringIO()
    # Excel and Sheets both expect CRLF, and csv defaults to it; asking for it
    # explicitly keeps the output the same wherever this runs.
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if row.get(h) is None else row.get(h, "")
                         for h in headers])
    return buffer.getvalue()
