"""
Sed/Stats

Editor-style layout: an Outputs tab holding a tool ribbon and the generated
graphs, and a Spreadsheet tab holding the data. Each ribbon tool opens a
wizard that collects samples, dimensions and options; graphs are produced
only on demand. Selecting several dimensions yields one tabbed output with a
tab per dimension. Data comes from the built-in example or an uploaded
csv/xls/xlsx file.

The pieces live in the `dashboard` package; this module only assembles them.
"""
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
        # Closing a tool's modal, however it was closed, un-presses its button.
        on_close=lambda tool: shell.ribbon.select(None),
    )

    def sync_tool_options(*args, **kwargs):
        rows = shell.table.get_data()
        for tool in tools.values():
            tool.sync_options(rows)

    sync_tool_options()

    @when(shell.ribbon.events.select)
    def on_tool_select(sender, key):
        tools[key].open()

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

    @when(shell.upload.events.data_loaded)
    def on_upload(sender, rows, filename):
        shell.table.set_data(rows)
        sync_tool_options()


if __name__ == "__main__":
    main()
