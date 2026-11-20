"""
Knowing when there is unsaved work, and looking after it.

The tracker compares a signature of the current spreadsheet and workflow with
the signature at the last point they were known to be saved. Comparing, rather
than flipping a flag on each change event, is what makes it robust: loading a
project fires change events in an order nobody should depend on, and an edit
that is typed and then undone leaves nothing to save.

Whenever the work differs from its saved state it:
    - marks the Projects button,
    - warns before the page is closed (when a Drive save is possible),
    - writes a recovery copy to IndexedDB,
    - and, if the user opted in and the project already has a Drive file,
      overwrites that file shortly after the last change.
"""
import asyncio
import hashlib
import json
from datetime import datetime, timezone

from antioch.event import when

from project_lib import dump_project

from .confirm import ConfirmDialog
from .recovery import set_unsaved_flag

# Changes arrive in bursts (typing, a load firing several events), so work
# waits for things to settle. Autosave waits longer: a Drive write is a
# network call and the user is likely still editing.
EVALUATE_DELAY = 0.6
AUTOSAVE_DELAY = 5.0

DISCARD_PROMPT = "You have unsaved changes. Continue and discard them?"


def signature(rows, workflow=None):
    """
    A fingerprint of the work: the sheet and the workflow, its steps and the tools the user
    made. A workflow with neither counts as none. Where the blocks sit on the canvas is part
    of the steps, so moving one counts as a change.
    """
    document = ({key: workflow[key] for key in ("steps", "tools", "layout", "groups") if workflow.get(key)}
                if workflow else None)
    payload = json.dumps([rows, document or None], sort_keys=True, default=str)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


class WorkTracker:
    """
    Usage:
        tracker = WorkTracker(table.get_data, workflow_panel.to_dict, project,
                              store, table, drive_usable=lambda: ...)
        # the sheet's data_change and the project's events are wired here

        tracker.is_dirty()
        tracker.confirm_discard()   # False if the user declines to lose work
    """

    def __init__(self, get_rows, get_workflow, project, store, table, drive_usable):
        self._get_rows = get_rows
        self._get_workflow = get_workflow
        self._project = project
        self._store = store
        self._drive_usable = drive_usable

        self.baseline = None      # signature when last saved; None = unknown
        self._adopt = True        # take the next settled state as the baseline
        self._hold_storage = True # until startup has offered any recovery copy
        self._stored = True       # a recovery copy may exist, so clean up once
        self._dirty = False
        self._evaluate_handle = None
        self._autosave_handle = None
        self._autosaving = False
        self._discard_dialog = None   # built on first use

        @when(table.events.data_change)
        def on_table_change(sender, *args):
            self.changed()

        @when(project.events.saved)
        def on_saved(sender, rows, workflow, *args):
            # The state that was written, not whatever the sheet holds by the
            # time the upload returned: edits made meanwhile are still unsaved.
            self.mark_clean(rows, workflow)

        @when(project.events.project_loaded)
        def on_project_loaded(sender, *args):
            self.mark_clean()

    # ------------------------------------------------------------------ state

    def is_dirty(self):
        """Whether the work differs from its last saved state, right now."""
        if self._adopt:
            return False
        if self.baseline is None:
            return True
        return self._now() != self.baseline

    def _now(self):
        return signature(self._get_rows(), self._get_workflow())

    def mark_clean(self, rows=None, workflow=None):
        """
        Declare the work saved.

        With rows (and the workflow), the baseline is exactly that state. Without
        them (a project just opened) the next settled state is adopted
        instead, since the sheet may still be taking in the data it was given.
        """
        if rows is None:
            self._adopt = True
        else:
            self._adopt = False
            self.baseline = signature(rows, workflow)
        self.changed()

    def mark_unsaved(self):
        """The work has no known saved state, e.g. it was restored from recovery."""
        self._adopt = False
        self.baseline = None
        self.changed()

    def release_storage(self):
        """Startup is done offering recovery; the copy may now be managed."""
        self._hold_storage = False
        self.changed()

    # ----------------------------------------------------------------- events

    def changed(self):
        """Something may have changed; look again once things settle."""
        self._reschedule("_evaluate_handle", EVALUATE_DELAY, self._evaluate)

    def _reschedule(self, attribute, delay, callback):
        handle = getattr(self, attribute)
        if handle is not None:
            handle.cancel()
        setattr(self, attribute,
                asyncio.get_event_loop().call_later(delay, callback))

    def _evaluate(self):
        self._evaluate_handle = None
        if self._adopt:
            self.baseline = self._now()
            self._adopt = False

        dirty = self.is_dirty()
        if dirty != self._dirty:
            self._dirty = dirty
            self._project.set_dirty(dirty)
        # Leaving only loses work if there was a Drive to save it to.
        set_unsaved_flag(dirty and bool(self._drive_usable()))

        if not self._hold_storage:
            if dirty:
                self._stored = True
                asyncio.ensure_future(self._write_recovery())
            elif self._stored:
                self._stored = False
                asyncio.ensure_future(self._store.clear())

        if (dirty and self._project.autosave_enabled
                and self._project.can_autosave):
            self._reschedule("_autosave_handle", AUTOSAVE_DELAY, self._start_autosave)

    async def _write_recovery(self):
        rows = self._get_rows()
        workflow = self._get_workflow()
        await self._store.put({
            "text": dump_project(self._project.name, rows, workflow=workflow),
            "name": self._project.name,
            "file_id": self._project.file_id or "",
            "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "rows": len(rows),
            "steps": len((workflow or {}).get("steps") or []),
        })

    def _start_autosave(self):
        self._autosave_handle = None
        if self._autosaving or not self._project.can_autosave or not self.is_dirty():
            return
        asyncio.ensure_future(self._autosave())

    async def _autosave(self):
        self._autosaving = True
        try:
            # A failure leaves the work dirty and is reported by the project;
            # the next change schedules another try, so a persistent fault
            # cannot turn into a retry loop.
            await self._project.autosave()
        finally:
            self._autosaving = False

    # ---------------------------------------------------------------- guarding

    async def confirm_discard(self):
        """True if it is fine to replace the current work."""
        if not self.is_dirty():
            return True
        if self._discard_dialog is None:
            self._discard_dialog = ConfirmDialog("Unsaved changes")
        # Closing the dialog unanswered is "no": nothing is lost by default.
        return bool(await self._discard_dialog.ask(
            DISCARD_PROMPT, "Discard changes", "Keep editing"))
