"""The page frame: header, top-level tabs, ribbon, and the two panels.

Everything here is chrome. The tab bar and ribbon are anchored and only the
panel bodies scroll, so the app behaves like an editor rather than a document.
"""
from antioch.dom import DOM
from antioch.elements import Div, H1

from spreadsheet_lib import SpreadsheetUpload, TabulatorSheet
from ui_lib import Ribbon, TabItem, TabView

from .config import TOOLS
from .example_data import generate_example_rows
from .gallery import Gallery

# A definite height: Tabulator sizes its virtual viewport from this, and a
# percentage would resolve against an auto-height parent and collapse.
TABLE_HEIGHT = "calc(100vh - 210px)"

PANEL_STYLE = {
    "display": "flex", "flex-direction": "column",
    "height": "100%", "min-height": "0",
}
SCROLL_STYLE = {
    "flex": "1", "min-height": "0", "overflow-y": "auto", "padding": "16px",
}


class AppShell:
    """
    Builds and mounts the page.

    Attributes:
        table    - TabulatorSheet holding the data
        upload   - SpreadsheetUpload above it
        ribbon   - Ribbon of tool buttons
        gallery  - Gallery of generated outputs
        tabs     - top-level TabView (Outputs first, then Spreadsheet)
    """

    def __init__(self, title="Sed/Stats"):
        self._style_body()
        DOM.add(self._header(title))

        self.table = TabulatorSheet(data=generate_example_rows(), height=TABLE_HEIGHT)
        self.upload = SpreadsheetUpload()
        self.ribbon = Ribbon(tools=list(TOOLS.items()))
        self.ribbon.element.style.margin_bottom = "0"
        self.gallery = Gallery()

        self.tabs = TabView(fill=True, tabs=[
            TabItem("Outputs", self._outputs_panel()),
            TabItem("Spreadsheet", self._spreadsheet_panel()),
        ])
        DOM.add(Div(self.tabs.element, style={
            "flex": "1", "min-height": "0", "padding": "0 16px 16px",
            "display": "flex", "flex-direction": "column",
        }))

    @staticmethod
    def _style_body():
        # Viewport-height flex column with no page scroll, so the tab bar and
        # ribbon stay put and only the panels scroll.
        DOM.body.style.update({
            "margin": "0",
            "height": "100vh",
            "overflow": "hidden",
            "display": "flex",
            "flex-direction": "column",
            "font-family": "system-ui, -apple-system, sans-serif",
        })

    @staticmethod
    def _header(title):
        return Div(
            H1(title, style={"margin": "0", "font-size": "20px"}),
            style={
                "flex-shrink": "0", "padding": "10px 16px",
                "background-color": "#2c3e50", "color": "#fff",
            },
        )

    def _spreadsheet_panel(self):
        return Div(
            Div(self.upload.element, style={
                "flex-shrink": "0", "padding": "10px 16px",
                "border-bottom": "1px solid #e9ecef",
            }),
            Div(self.table.element, style={
                "flex": "1", "min-height": "0", "padding": "16px",
            }),
            style=PANEL_STYLE,
        )

    def _outputs_panel(self):
        return Div(
            Div(self.ribbon.element, style={"flex-shrink": "0"}),
            # Only this scrolls.
            Div(self.gallery.element, style=SCROLL_STYLE),
            style=PANEL_STYLE,
        )
