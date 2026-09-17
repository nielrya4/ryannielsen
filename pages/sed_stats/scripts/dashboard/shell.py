"""The page frame: header, top-level tabs, toolbar, and the two panels.

Everything here is chrome. The tab bar and toolbar are anchored and only the
panel bodies scroll, so the app behaves like an editor rather than a document.
"""
from antioch.dom import DOM
from antioch.elements import Button, Div, H1, Span
from antioch.event import when

from spreadsheet_lib import SpreadsheetUpload, TabulatorSheet
from ui_lib import TabItem, TabView, Toolbar

from .config import TOOL_MENU
from .drive import DrivePanel
from .example_data import generate_example_rows
from .gallery import Gallery

# A definite height: Tabulator sizes its virtual viewport from this, and a
# percentage would resolve against an auto-height parent and collapse.
TABLE_HEIGHT = "calc(100vh - 262px)"

PANEL_STYLE = {
    "display": "flex", "flex-direction": "column",
    "height": "100%", "min-height": "0",
}
SCROLL_STYLE = {
    "flex": "1", "min-height": "0", "overflow-y": "auto", "padding": "16px",
}

ROW_BUTTON_STYLE = {
    "background-color": "#34495e", "color": "#fff", "border": "none",
    "padding": "6px 14px", "cursor": "pointer", "font-size": "13px",
    "margin-right": "8px",
}
STATUS_STYLE = {"font-size": "13px", "color": "#6c757d"}


class AppShell:
    """
    Builds and mounts the page.

    Attributes:
        table    - TabulatorSheet holding the data
        upload   - SpreadsheetUpload above it
        drive    - DrivePanel beside it; empty and hidden when Google
                   sign-in is not configured
        toolbar  - Toolbar of tool menus; fill it with set_tool_menu()
        gallery  - Gallery of generated outputs
        tabs     - top-level TabView (Outputs first, then Spreadsheet)
    """

    def __init__(self, title="Sed/Stats"):
        self._style_body()

        self.table = TabulatorSheet(data=generate_example_rows(), height=TABLE_HEIGHT)
        self.upload = SpreadsheetUpload()
        self.drive = DrivePanel(get_rows=self.table.get_data)
        DOM.add(self._header(title))
        # Built empty: the tools it opens do not exist until the gallery does,
        # so main.py fills it in through set_tool_menu once they are wired.
        self.toolbar = Toolbar(
            toolbar_style={"background_color": "#34495e"},
            menu_item_style={"font_size": "14px", "padding": "10px 18px"},
        )
        # Cards only offer "Save to Drive" when there is a Drive to save to.
        self.gallery = Gallery(
            on_save=self.drive.save_bytes if self.drive.configured else None)

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
        # toolbar stay put and only the panels scroll.
        DOM.body.style.update({
            "margin": "0",
            "height": "100vh",
            "overflow": "hidden",
            "display": "flex",
            "flex-direction": "column",
            "font-family": "system-ui, -apple-system, sans-serif",
        })

    def _header(self, title):
        return Div(
            H1(title, style={"margin": "0", "font-size": "20px"}),
            # Right-aligned by its own margin-left:auto, and empty and hidden
            # when Google sign-in is not configured.
            self.drive.account_element,
            style={
                "flex-shrink": "0", "padding": "10px 16px",
                "background-color": "#2c3e50", "color": "#fff",
                "display": "flex", "align-items": "center", "gap": "12px",
            },
        )

    def set_tool_menu(self, tools):
        """
        Point the toolbar's menu entries at the tools they open.

        TOOL_MENU holds tool *keys*; this swaps each for a callback that opens
        that tool's wizard, leaving the nesting as written.
        """
        def resolve(node):
            if isinstance(node, dict):
                return {label: resolve(child) for label, child in node.items()}
            tool = tools[node]
            return lambda tool=tool: tool.open()

        self.toolbar.update_menu(resolve(TOOL_MENU))
        return self

    def _row_controls(self):
        """
        Add and delete rows.

        Tabulator has no built-in affordance for either, and a spreadsheet the
        user is expected to edit needs both. Deletion works on whatever the
        current selection touches — click a row number, or drag a range.
        """
        add = Button("Add row", style=ROW_BUTTON_STYLE)
        delete = Button("Delete selected rows", style=ROW_BUTTON_STYLE)
        status = Span("", style=STATUS_STYLE)

        @when(add.events.click)
        def on_add(sender, *args):
            self.table.add_row()
            status.set_text("Row added.")

        @when(delete.events.click)
        def on_delete(sender, *args):
            removed = self.table.delete_selected_rows()
            status.set_text(
                f"Deleted {removed} row{'s' if removed != 1 else ''}."
                if removed else
                "Nothing selected — click a row number, or drag across cells.")

        return Div(add, delete, status, style={
            "display": "flex", "align-items": "center", "flex-wrap": "wrap",
            "gap": "4px",
        })

    def _spreadsheet_panel(self):
        return Div(
            Div(self.upload.element, self.drive.element, style={
                "flex-shrink": "0", "padding": "10px 16px",
                "border-bottom": "1px solid #e9ecef",
                "display": "flex", "align-items": "center",
                "flex-wrap": "wrap", "gap": "8px",
            }),
            Div(self._row_controls(), style={
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
            Div(self.toolbar.element, style={"flex-shrink": "0",
                                             "margin-bottom": "12px"}),
            # Only this scrolls.
            Div(self.gallery.element, style=SCROLL_STYLE),
            style=PANEL_STYLE,
        )
