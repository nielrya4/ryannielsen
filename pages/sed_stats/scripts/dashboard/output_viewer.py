"""
Expanding a step's output: the plots, tables and notes it made, large, with what can be done
with them — download, save to Drive.

A step's output belongs to its block on the canvas; this is the window it opens in. One viewer
serves every block, showing whichever output it is given.
"""
import asyncio

from antioch.dom import DOM
from antioch.elements import Button, Div, Span
from antioch.event import when
from antioch.macros import Modal

from plot_lib import charts_to_zip, download_bytes, safe_filename

async def charts_as_file(charts, base_name):
    """
    The plots as one file to hand over: (filename, bytes, mime type). A single plot is its
    SVG; several are a zip of SVGs, because a browser blocks all but the first of many
    downloads at once.
    """
    if len(charts) == 1:
        return f"{base_name}.svg", await charts[0][1].to_svg(), "image/svg+xml"
    return f"{base_name}.zip", await charts_to_zip(charts), "application/zip"


def download_charts(charts, base_name):
    """
    Download the plots: one as an SVG straight away, several as a zip (a coroutine to
    await, since zipping takes a moment).
    """
    if len(charts) == 1:
        charts[0][1].download_svg(base_name)
        return None

    async def archive():
        download_bytes(await charts_to_zip(charts), f"{base_name}.zip")
    return archive()


MODAL_STYLE = {"width": "94vw", "max-width": "1240px", "max-height": "92vh", "min-width": "0"}
BUTTON_STYLE = {
    "background-color": "#146c2e", "color": "#fff", "border": "none", "padding": "5px 12px",
    "border-radius": "4px", "cursor": "pointer", "font-size": "13px", "margin-right": "8px",
}
STATUS_STYLE = {"font-size": "13px", "color": "#b00020"}
ACTIONS_STYLE = {"display": "flex", "align-items": "center", "flex-wrap": "wrap",
                 "gap": "4px", "margin-bottom": "12px"}


class OutputViewer:
    """
    Args:
        on_save: optional `async (filename, data, mime_type)` sink; given, a "Save to Drive"
            button is offered beside the download
    """

    def __init__(self, on_save=None):
        self._on_save = on_save
        self._output = None
        self._base_name = "output"
        self._download = Button("Download SVG", style=dict(BUTTON_STYLE))
        self._save = Button("Save to Drive", style=dict(BUTTON_STYLE))
        self._status = Span("", style=dict(STATUS_STYLE))
        self._holder = Div()
        if not on_save:
            self._save.style.display = "none"

        @when(self._download.events.click)
        def on_download(sender, *args):
            asyncio.ensure_future(self.download())

        @when(self._save.events.click)
        def on_save_click(sender, *args):
            asyncio.ensure_future(self.save())

        self.modal = Modal(title="Output", modal_style=dict(MODAL_STYLE))
        self.modal.set_content(Div(
            Div(self._download, self._save, self._status, style=dict(ACTIONS_STYLE)),
            self._holder))
        DOM.add(self.modal.element)

        @when(self.modal.events.open)
        def on_open(sender, *args):
            # Plots that were made while nothing showed them have no size yet.
            asyncio.get_event_loop().call_later(0.12, self.resize)

    @property
    def charts(self):
        return self._output.charts if self._output is not None else []

    def show(self, title, output):
        """Open the viewer on a step's output (a `StepOutput`: body, charts)."""
        self._output = output
        self._base_name = safe_filename(title, "output")
        self._status.set_text("")
        self.modal.set_title(title)
        self._holder._dom_element.innerHTML = ""
        self._holder.add(output.body)
        has_charts = bool(output.charts)
        self._download.style.display = "inline-block" if has_charts else "none"
        self._download.set_text("Download SVG" if len(output.charts) <= 1 else "Download SVGs (zip)")
        self._save.style.display = "inline-block" if (has_charts and self._on_save) else "none"
        self.modal.open()
        self.resize()

    def close(self):
        self.modal.close()

    def resize(self):
        for _, chart in self.charts:
            chart.resize()

    async def download(self, output=None, title=None):
        """Download the shown output's plots (or another output's, without opening it)."""
        charts = (output or self._output).charts
        base = safe_filename(title, "output") if title else self._base_name
        if not charts:
            return
        pending = download_charts(charts, base)
        if pending is not None:
            await pending

    async def save(self, output=None, title=None):
        """Save the plots to Drive."""
        charts = (output or self._output).charts
        base = safe_filename(title, "output") if title else self._base_name
        if not charts or not self._on_save:
            return
        try:
            self._save.set_text("Saving…")
            self._status.set_text("")
            await self._on_save(*await charts_as_file(charts, base))
        except Exception as error:
            # Otherwise the failure escapes into the event loop and the button just goes back.
            self._status.set_text(str(error))
        finally:
            self._save.set_text("Save to Drive")
