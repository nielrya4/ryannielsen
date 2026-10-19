"""The list of generated outputs, each downloadable and deletable."""
import asyncio

from antioch.elements import Button, Div, H3, P, Span
from antioch.event import when

from plot_lib import charts_to_zip, download_bytes, safe_filename

DOWNLOAD_STYLE = {
    "background-color": "#146c2e", "color": "#fff", "border": "none",
    "padding": "5px 12px", "border-radius": "4px", "cursor": "pointer",
    "font-size": "13px", "margin-right": "8px",
}
DELETE_STYLE = {
    "background-color": "#b00020", "color": "#fff", "border": "none",
    "padding": "5px 12px", "border-radius": "4px", "cursor": "pointer",
    "font-size": "13px",
}
SAVE_STATUS_STYLE = {
    "font-size": "13px", "color": "#b00020", "margin-left": "8px",
    "flex-basis": "100%",
}
CARD_STYLE = {
    "border": "1px solid #ddd", "border-radius": "8px",
    "padding": "14px", "margin-bottom": "16px", "background-color": "#fff",
}


class Gallery:
    """
    Holds generated outputs as cards.

    Each entry keeps its (name, chart) pairs so the charts can be re-fitted
    when they become visible again and exported on demand.
    """

    def __init__(self, empty_text="No graphs yet. Pick a tool above to make one.",
                 on_save=None):
        """
        Args:
            on_save: optional `async (filename, data, mime_type)` sink. When
                given, each card grows a "Save to Drive" button alongside the
                download; when None the button is left off entirely.
        """
        self._on_save = on_save
        self._entries = []
        self._empty = P(empty_text, style={"color": "#6c757d"})
        self._list = Div()
        self.element = Div(self._empty, self._list)

    @property
    def entries(self):
        return list(self._entries)

    def resize_all(self):
        """Charts measure themselves on render and read zero while hidden."""
        for entry in self._entries:
            for _, chart in entry["charts"]:
                chart.resize()

    def add(self, title, body, charts, tabview=None):
        entry = {"element": None, "charts": charts, "tabview": tabview}
        base_name = safe_filename(title, "graph")

        download = Button("Download SVG", style=DOWNLOAD_STYLE)
        delete = Button("Delete", style=DELETE_STYLE)
        buttons = [download]
        if not charts:
            download.style.display = "none"

        # The Drive panel's own status line lives in the Spreadsheet tab, so a
        # failure here would otherwise be invisible from the Outputs tab.
        save_status = Span("", style=SAVE_STATUS_STYLE)
        if self._on_save and charts:
            buttons.insert(1, self._save_button(entry, base_name, save_status))

        async def download_archive():
            try:
                download.set_text("Zipping…")
                data = await charts_to_zip(entry["charts"])
                download_bytes(data, f"{base_name}.zip")
            finally:
                download.set_text("Download SVG")

        @when(download.events.click)
        def on_download(sender, *args):
            named = entry["charts"]
            if len(named) == 1:
                named[0][1].download_svg(base_name)
            else:
                # One file per plot would mean a browser download storm, and
                # most browsers block all but the first anyway.
                asyncio.ensure_future(download_archive())

        @when(delete.events.click)
        def on_delete(sender, *args):
            self._remove(entry)

        header = Div(
            H3(title, style={"font-size": "16px", "margin": "0",
                             "flex": "1", "min-width": "0"}),
            Div(*buttons, delete, style={"flex-shrink": "0"}),
            save_status,
            style={
                "display": "flex", "align-items": "center", "gap": "10px",
                "flex-wrap": "wrap", "margin-bottom": "10px",
            },
        )

        entry["element"] = Div(header, body, style=CARD_STYLE)
        self._entries.append(entry)
        self._list.add(entry["element"])
        self._sync_empty()
        return entry

    def _save_button(self, entry, base_name, status):
        """A "Save to Drive" twin of the download button."""
        save = Button("Save to Drive", style=DOWNLOAD_STYLE)

        async def upload():
            try:
                save.set_text("Saving…")
                status.set_text("")
                named = entry["charts"]
                if len(named) == 1:
                    await self._on_save(f"{base_name}.svg",
                                        await named[0][1].to_svg(),
                                        "image/svg+xml")
                else:
                    await self._on_save(f"{base_name}.zip",
                                        await charts_to_zip(named),
                                        "application/zip")
            except Exception as error:
                # Without this the failure escapes into the event loop and the
                # user sees nothing but a button that went back to normal.
                status.set_text(str(error))
            finally:
                save.set_text("Save to Drive")

        @when(save.events.click)
        def on_save(sender, *args):
            asyncio.ensure_future(upload())

        return save

    def _remove(self, entry):
        for _, chart in entry["charts"]:
            try:
                chart.destroy()
            except Exception:
                # A chart that never initialized has nothing to tear down, and
                # a failure here must not strand the card on screen.
                pass
        entry["element"].remove()
        self._entries.remove(entry)
        self._sync_empty()

    def _sync_empty(self):
        self._empty.style.display = "none" if self._entries else "block"
