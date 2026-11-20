"""
Sed/Stats

A canvas and a spreadsheet. Analyses are built on the canvas, in the Workflow tab, from tools
(pre-wired chains of blocks, grouped in toolboxes) and the blocks they are made of; each block
that makes something keeps it, to expand, download or save to Drive. The Spreadsheet tab holds
the data, which comes from the built-in example, an uploaded csv/xls/xlsx file, or a file opened
from the user's Google Drive. A project (.sedprj) is the spreadsheet and the workflow.

The pieces live in the `dashboard` package; this module only assembles them.
"""
import asyncio

from antioch.event import when
from antioch import DOM
from dashboard import AppShell
from dashboard.toolboxes import builtin_registry
from ui_lib import LoadingOverlay


def main():
    DOM.clear()
    DOM.title = "Sed/Stats"
    shell = AppShell()
    overlay = LoadingOverlay()
    panel = shell.workflow_panel

    registry = builtin_registry()
    panel.attach(overlay, registry)
    shell.maps.attach(overlay)

    def refresh_tools():
        """Tools were added or removed: the menus and the palette follow."""
        panel.refresh_tool_menu()
        panel.notify_changed()

    registry.on_change = refresh_tools
    # Whatever the app starts with is the first saved state; without this the
    # first edit would be taken as the baseline and never read as a change.
    shell.tracker.mark_clean()

    @when(shell.tabs.events.change)
    def on_top_tab(sender, tab, *args):
        # The grid measures itself on render and reads zero while hidden.
        if tab.title == "Spreadsheet":
            shell.table.redraw()
        elif tab.title == "Maps":
            shell.maps.shown()

    def load_rows(rows):
        """Put a freshly parsed spreadsheet into the grid."""
        try:
            shell.table.set_data(rows)
        finally:
            # Whatever happens, the curtain has to come back up.
            overlay.hide()

    def apply_loaded(rows):
        # This data is not the open project's, so a later "Save" must ask where
        # to save rather than overwrite that project.
        shell.project.detach()
        load_rows(rows)

    async def confirm_then_load(rows):
        # The loading curtain would sit over the dialog, so it comes down first.
        overlay.hide()
        if await shell.tracker.confirm_discard():
            apply_loaded(rows)

    # Parsing a large workbook and handing it to Tabulator both block the UI
    # thread, so loading a file gets the same overlay as running a workflow.
    # Both loaders announce load_start, and both always finish with
    # data_loaded or error.
    for loader in (shell.upload, shell.drive):
        @when(loader.events.load_start)
        def on_load_start(sender, filename, *args):
            overlay.show(f"Loading {filename}…")

        @when(loader.events.data_loaded)
        def on_loaded(sender, rows, filename, *args):
            # Replacing the sheet loses whatever was unsaved. The file is
            # already parsed, so declining just drops it.
            if shell.tracker.is_dirty():
                asyncio.ensure_future(confirm_then_load(rows))
            else:
                apply_loaded(rows)

        @when(loader.events.error)
        def on_load_error(sender, message, *args):
            overlay.hide()

    # Projects (.sedprj) restore the spreadsheet and the workflow at once. The workflow's
    # steps are not run: some (MDS, unmixing) take seconds, so that waits for the user.
    @when(shell.project.events.load_start)
    def on_project_start(sender, filename, *args):
        overlay.show(f"Loading {filename}…")

    def load_workflow(project):
        """
        Replace the workflow with the project's saved one (or with none).

        A project from before outputs belonged to the workflow lists them separately; each is
        added to the canvas as the tool that made it, unrun.

        Returns:
            a sentence saying so, or "" when there was nothing of the kind
        """
        panel.load_or_clear(project.workflow)
        if not project.history:
            return ""
        added, skipped = panel.import_legacy(project.history)
        message = (f"{added} output{'s' if added != 1 else ''} saved by an older version "
                   f"{'were' if added != 1 else 'was'} added to the workflow as tools.")
        if skipped:
            message += f" {skipped} came from a tool this version lacks."
        return message

    @when(shell.project.events.project_loaded)
    def on_project_loaded(sender, project, filename, *args):
        load_rows(project.rows)
        message = load_workflow(project)
        if message:
            panel.say(message + " Run the workflow to rebuild them.")

    @when(shell.project.events.error)
    def on_project_error(sender, message, *args):
        overlay.hide()

    async def offer_recovery():
        """
        On startup, offer the work that was in progress when the page closed.

        The copy is only ever deleted by an explicit Discard. The dialog cannot
        be dismissed any other way, and the tracker is held off from touching
        the copy until it has been answered.
        """
        from dashboard.confirm import ConfirmDialog
        from project_lib import load_project

        try:
            entry = await shell.recovery.get()
            if not entry:
                return
            try:
                project = load_project(entry["text"])
            except Exception:
                await shell.recovery.clear()
                return

            steps = len((project.workflow or {}).get("steps") or []) + len(project.history)
            question = (
                f"Unsaved work from {entry.get('saved_at', 'an earlier session')} was "
                f"found in this browser: {len(project.rows)} rows, "
                f"{steps} step{'s' if steps != 1 else ''}.\n\n"
                f"Restore it, or discard it?")
            answer = await ConfirmDialog("Restore your work?").ask(
                question, "Restore", "Discard", dismissible=False)
            if not answer:
                await shell.recovery.clear()
                return

            load_rows(project.rows)
            message = load_workflow(project)
            shell.project.adopt_recovered(entry.get("file_id"), entry.get("name"))
            # Its saved state is unknown, so it counts as unsaved until saved.
            shell.tracker.mark_unsaved()
            # What was open shows its outputs again, as it did before the page closed.
            if panel.workflow.steps:
                await panel.run_workflow()
            if message:
                panel.append_note(message)
        finally:
            shell.tracker.release_storage()

    async def startup():
        # One thing at a time. Offering the recovery copy comes first so
        # nothing competes with it, and Google's sign-in restore (which opens
        # a popup and moves focus) runs only once it is settled. If the user
        # connected Google before, Google re-issues a token with no UI while
        # the grant is live, so a reload keeps them signed in; if it cannot,
        # they just see the sign-in button again.
        await offer_recovery()
        await shell.drive.restore()

    asyncio.ensure_future(startup())

if __name__ == "__main__":
    main()
