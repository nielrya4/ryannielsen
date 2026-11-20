"""The page frame: header, top-level tabs, and the two panels.

Everything here is chrome. The tab bar is anchored and only the panel bodies scroll, so the
app behaves like an editor rather than a document.
"""
import asyncio

from antioch.dom import DOM
from antioch.elements import Button, Div, H1, Span
from antioch.event import when

from spreadsheet_lib import SpreadsheetUpload, TabulatorSheet
from ui_lib import TabItem, TabView

from .drive import DrivePanel
from .example_data import generate_example_rows
from .maps_panel import MapsPanel
from .project import ProjectPanel
from .prompt import PromptDialog
from .recovery import RecoveryStore
from .tracker import WorkTracker
from .workflow_panel import WorkflowPanel

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
        project  - ProjectPanel: the title-bar Projects button and its dialog
        tracker  - WorkTracker: unsaved-work marker, recovery copy, autosave
        recovery - RecoveryStore: the IndexedDB recovery copy
        workflow_panel - the Workflow tab: the canvas, its tools and blocks, and each block's
                   output
        maps     - MapsPanel: the Maps tab — delineate watersheds and fetch gauges and climate,
                   handing the results to the workflow
        tabs     - top-level TabView (Workflow, Spreadsheet, then Maps)
    """

    def __init__(self, title="Sed/Stats"):
        self._style_body()

        self.table = TabulatorSheet(data=generate_example_rows(), height=TABLE_HEIGHT)
        self.upload = SpreadsheetUpload()
        self.drive = DrivePanel(get_rows=self.table.get_data)
        # The workflow panel does not exist yet, so its state is fetched lazily.
        self.project = ProjectPanel(
            self.drive, get_rows=self.table.get_data,
            get_workflow=lambda: self.workflow_panel.to_dict())

        @when(self.drive.events.sign_in_change)
        def on_sign_in_change(sender, usable, *args):
            self.project.set_enabled(usable)
            # Whether leaving the page loses work depends on being able to save.
            self.tracker.changed()
        DOM.add(self._header(title))

        # Watches the sheet and the workflow for unsaved work: marks the
        # Projects button, warns before leaving, keeps a recovery copy in
        # IndexedDB and, if opted in, autosaves the open project.
        self.recovery = RecoveryStore()
        self.tracker = WorkTracker(
            self.table.get_data, lambda: self.workflow_panel.to_dict(), self.project,
            self.recovery, self.table,
            drive_usable=lambda: (self.drive.session.signed_in
                                  and self.drive.session.has_drive_access))
        self.project.guard = self.tracker.confirm_discard
        # The workflow's steps are part of the work, so editing them counts.
        # A step's output lives with its block, so there is nowhere else to look for results.
        # "Save to Drive" is offered only when there is a Drive to save to.
        self.workflow_panel = WorkflowPanel(
            self.table.get_data, on_change=self.tracker.changed,
            on_save=self.drive.save_bytes if self.drive.configured else None,
            set_rows=self.table.set_data,
            on_view_spreadsheet=lambda: self.tabs.set_active(1),
            on_view_map=self._view_on_map)
        self.maps = MapsPanel(self.table.get_data, self.workflow_panel)

        self.tabs = TabView(fill=True, tabs=[
            TabItem("Workflow", self._workflow_tab()),
            TabItem("Spreadsheet", self._spreadsheet_panel()),
            TabItem("Maps", Div(self.maps.element, style=dict(PANEL_STYLE))),
        ])
        DOM.add(Div(self.tabs.element, style={
            "flex": "1", "min-height": "0", "padding": "0 16px 16px",
            "display": "flex", "flex-direction": "column",
        }))

    def _view_on_map(self, step_id):
        """A Watershed block's "View on the map": open the Maps tab and show it."""
        self.tabs.set_active(2)
        self.maps.show_block(step_id)

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
            # Right-aligned together. The Projects button comes first, so it
            # sits to the left of the signed-in email; both are hidden when
            # Google sign-in is not configured or the user is signed out.
            Div(self.project.button_element, self.drive.account_element, style={
                "margin-left": "auto", "display": "flex",
                "align-items": "center", "gap": "12px",
            }),
            style={
                "flex-shrink": "0", "padding": "10px 16px",
                "background-color": "#2c3e50", "color": "#fff",
                "display": "flex", "align-items": "center", "gap": "12px",
            },
        )

    def _row_controls(self):
        """
        Row and column buttons, and undo.

        Tabulator has no built-in affordance for these, and a spreadsheet the user is
        expected to edit needs them. Deleting works on whatever the current selection
        touches — click a row number or a column header, or drag a range. The same things,
        and renaming a column, are on the right-click menus of the rows and the headers.
        """
        add = Button("Add row", style=ROW_BUTTON_STYLE)
        add_column = Button("Add column", style=ROW_BUTTON_STYLE)
        delete = Button("Delete selected rows", style=ROW_BUTTON_STYLE)
        delete_columns = Button("Delete selected columns", style=ROW_BUTTON_STYLE)
        undo = Button("Undo", style=ROW_BUTTON_STYLE)
        redo = Button("Redo", style=ROW_BUTTON_STYLE)
        status = Span("", style=STATUS_STYLE)
        self.table.on_message = status.set_text
        self.table.prompt = PromptDialog().ask

        @when(add.events.click)
        def on_add(sender, *args):
            self.table.add_row()
            status.set_text("Row added.")

        @when(add_column.events.click)
        def on_add_column(sender, *args):
            asyncio.ensure_future(self.table.request_add_column())

        @when(delete.events.click)
        def on_delete(sender, *args):
            removed = self.table.delete_selected_rows()
            status.set_text(
                f"Deleted {removed} row{'s' if removed != 1 else ''}."
                if removed else
                "Nothing selected — click a row number, or drag across cells.")

        @when(delete_columns.events.click)
        def on_delete_columns(sender, *args):
            removed = self.table.delete_selected_columns()
            status.set_text(
                f"Deleted {removed} column{'s' if removed != 1 else ''}."
                if removed else
                "Nothing selected — click a column header, or drag across cells.")

        @when(undo.events.click)
        def on_undo(sender, *args):
            status.set_text("Undone." if self.table.undo() else "Nothing to undo.")

        @when(redo.events.click)
        def on_redo(sender, *args):
            status.set_text("Redone." if self.table.redo() else "Nothing to redo.")

        return Div(add, add_column, delete, delete_columns, undo, redo, status, style={
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

    def _workflow_tab(self):
        return Div(Div(self.workflow_panel.element, style=SCROLL_STYLE),
                   style=PANEL_STYLE)
