"""
Sed/Stats

Editor-style layout: an Outputs tab holding a tool menu and the generated
graphs, and a Spreadsheet tab holding the data. Tools are grouped into
Univariate and Multivariate menus; each opens a wizard that collects samples,
dimensions and options, and graphs are produced
only on demand. Selecting several dimensions yields one tabbed output with a
tab per dimension. Data comes from the built-in example, an uploaded
csv/xls/xlsx file, or a file opened from the user's Google Drive.

The pieces live in the `dashboard` package; this module only assembles them.
"""
import asyncio

from antioch.event import when
from antioch import DOM
from dashboard import AppShell, build_tools
from ui_lib import LoadingOverlay


def main():
    DOM.clear()
    DOM.title = "Sed/Stats"
    shell = AppShell()
    overlay = LoadingOverlay()

    tools = build_tools(
        get_rows=shell.table.get_data,
        gallery=shell.gallery,
        overlay=overlay,
        # The PCA axes tool writes derived columns back; set_data fires
        # data_change, which re-syncs every tool's dimension list.
        set_rows=shell.table.set_data,
    )

    # The toolbar opens tools, so it can only be wired once they exist.
    shell.set_tool_menu(tools)

    def sync_tool_options(*args, **kwargs):
        rows = shell.table.get_data()
        for tool in tools.values():
            tool.sync_options(rows)

    sync_tool_options()

    # If the user connected Google before, re-attach silently. Google
    # re-issues a token with no UI while the grant is live, so a reload keeps
    # them signed in; if it cannot, they just see the sign-in button again.
    asyncio.ensure_future(shell.drive.restore())

    @when(shell.tabs.events.change)
    def on_top_tab(sender, tab, *args):
        # Both widgets measure themselves on render and read zero while hidden.
        if tab.title == "Spreadsheet":
            shell.table.redraw()
        else:
            shell.gallery.resize_all()

    @when(shell.table.events.data_change)
    def on_table_change(sender, *args):
        sync_tool_options()

    def load_rows(rows):
        """Put a freshly parsed spreadsheet into the grid."""
        try:
            shell.table.set_data(rows)
            sync_tool_options()
        finally:
            # Whatever happens, the curtain has to come back up.
            overlay.hide()

    # Parsing a large workbook and handing it to Tabulator both block the UI
    # thread, so loading a file gets the same overlay as generating a graph.
    # Both loaders announce load_start, and both always finish with
    # data_loaded or error.
    for loader in (shell.upload, shell.drive):
        @when(loader.events.load_start)
        def on_load_start(sender, filename, *args):
            overlay.show(f"Loading {filename}…")

        @when(loader.events.data_loaded)
        def on_loaded(sender, rows, filename, *args):
            load_rows(rows)

        @when(loader.events.error)
        def on_load_error(sender, message, *args):
            overlay.hide()


if __name__ == "__main__":
    main()
