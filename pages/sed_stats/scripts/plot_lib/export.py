"""Packaging plots for download."""
import io
import re
import zipfile

import js
from pyodide.ffi import to_js


def safe_filename(name, fallback="chart"):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("_")
    return cleaned or fallback


async def charts_to_zip(named_charts):
    """
    Zip several plots' SVGs into one archive.

    Args:
        named_charts: [(name, PlotlyChart), ...]

    Returns:
        bytes of the .zip
    """
    buffer = io.BytesIO()
    used = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, chart in named_charts:
            base = safe_filename(name)
            filename = base
            index = 2
            while filename in used:
                filename = f"{base}_{index}"
                index += 1
            used.add(filename)
            archive.writestr(f"{filename}.svg", await chart.to_svg())
    return buffer.getvalue()


def download_bytes(data, filename, mime="application/zip"):
    """Hand a bytes payload to the browser as a download."""
    array = js.Uint8Array.new(len(data))
    array.assign(data)
    blob = js.Blob.new(
        [array], to_js({"type": mime}, dict_converter=js.Object.fromEntries)
    )
    url = js.URL.createObjectURL(blob)

    anchor = js.document.createElement("a")
    anchor.href = url
    anchor.download = filename
    js.document.body.appendChild(anchor)
    anchor.click()
    js.document.body.removeChild(anchor)
    js.URL.revokeObjectURL(url)
