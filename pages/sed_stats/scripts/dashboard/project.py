"""
Projects (.sedprj) on Google Drive, from a button in the title bar.

A project is the spreadsheet plus the workflow (see `project_lib`); a step's output is made
again by running the workflow. The **Projects** button sits beside the account email and
only appears while Drive is usable; it opens one dialog that holds everything: the projects
Sed/Stats saved (click one to open it), Save, Save as…, and Browse Drive… for a file saved
elsewhere.

Under the `drive.file` scope the app cannot search a whole Drive, so the list
is of the app's own files; a file picked through Browse Drive… is also one the
app may overwrite afterwards.
"""
import asyncio

import js
from antioch.dom import DOM
from antioch.elements import Button, Div, Input, Label, P, Span
from antioch.event import when
from antioch.macros import Modal
from antioch.macros.base import Macro
from component_lib.button import ButtonSecondary, ButtonSuccess

from project_lib import (
    EXTENSION, MIME_TYPE, dump_project, load_project, project_filename,
)

from .drive import ACCOUNT_BUTTON_HOVER, ACCOUNT_BUTTON_STYLE
from .save_dialog import SaveDialog

DEFAULT_NAME = "sed-stats-project"
AUTOSAVE_KEY = "sedStats.autosave"
ERROR_COLOR = "#b00020"
MUTED_COLOR = "#555"

# Everything the app can see that looks like a project: our own type, or the
# extension in the name (a file uploaded by hand has neither our type nor a
# reliable one, so the name has to be allowed to match).
PROJECT_QUERY = (f"(mimeType = '{MIME_TYPE}' or name contains 'sedprj') "
                 f"and trashed = false")

MODAL_STYLE = {"max-width": "540px", "width": "92vw"}
CURRENT_STYLE = {"font-size": "14px", "font-weight": "600", "margin": "0 0 4px 0"}
STATUS_STYLE = {"font-size": "13px", "color": MUTED_COLOR, "margin": "0 0 10px 0",
                "min-height": "18px"}
LIST_STYLE = {"max-height": "40vh", "overflow-y": "auto", "margin": "6px 0 14px"}
ITEM_STYLE = {
    "display": "flex", "justify-content": "space-between", "gap": "12px",
    "width": "100%", "text-align": "left", "padding": "9px 12px",
    "margin-bottom": "6px", "background-color": "#f6f8fa",
    "border": "1px solid #d8dee4", "border-radius": "4px",
    "cursor": "pointer", "font-size": "14px",
}
ITEM_DATE_STYLE = {"color": "#6c757d", "font-size": "12px", "white-space": "nowrap"}
ACTIONS_STYLE = {"display": "flex", "flex-wrap": "wrap", "gap": "8px"}


class ProjectPanel(Macro):
    """
    The Projects button and the dialog behind it.

    Usage:
        project = ProjectPanel(drive, get_rows=table.get_data,
                               get_workflow=workflow_panel.to_dict)
        header.add(project.button_element)      # beside the account control

        @when(project.events.project_loaded)
        def on_loaded(sender, project, filename): ...

    Fires `load_start(filename)` before reading a file, `project_loaded(project,
    filename)` once it parsed, `saved(rows, workflow)` after anything was written to
    Drive (with exactly what was written), and `error(message)` on any failure.

    The work tracker drives `set_dirty`, `autosave` and the `guard`: the button
    shows a dot while there are unsaved changes, and `guard()` is asked before
    a project replaces the current work.
    """

    def __init__(self, drive, get_rows=None, get_workflow=None, **kwargs):
        super().__init__(macro_type="project_panel", **kwargs)
        self._drive = drive
        self._get_rows = get_rows
        self._get_workflow = get_workflow
        self._save_dialog = None     # built lazily: each mounts itself in the page
        self._menu = None
        self.file_id = None          # the Drive file this project is saved as
        self.name = ""               # its name, without the extension
        self._dirty = False          # unsaved changes, as told by the tracker
        self._busy = False           # a save is in flight; autosave stands aside
        # Awaited before opening a project over the current work; resolves to
        # False to cancel. The app replaces this with the tracker's confirmation.
        async def allow():
            return True
        self.guard = allow

        self._create_event('load_start')
        self._create_event('project_loaded')
        self._create_event('saved')
        self._create_event('error')

        self._init_macro()

    @property
    def configured(self):
        return self._drive.configured

    # -------------------------------------------------------------- elements

    def _create_elements(self):
        # The macro's own container stays empty and unmounted; the only thing
        # placed in the page is the title-bar button.
        container = self._register_element('container', self._create_container({}))
        button = self._register_element(
            'button', Button("Projects", style=dict(ACCOUNT_BUTTON_STYLE)))
        # Hidden until Drive is usable: no project can be opened or saved
        # without it, so there is nothing for the button to offer.
        button.style.display = "none"

        def hover(active):
            button.style.background_color = (
                ACCOUNT_BUTTON_HOVER if active else "transparent")

        button.on_mouseenter(lambda e: hover(True))
        button.on_mouseleave(lambda e: hover(False))

        @when(button.events.click)
        def on_click(sender, *args):
            self._show_menu()

        return container

    @property
    def button_element(self):
        """The title-bar button; place it beside the account control."""
        return self._get_element('button')

    def set_dirty(self, dirty):
        """Mark the button (and the dialog's heading) for unsaved changes."""
        self._dirty = bool(dirty)
        self.button_element.set_text("Projects •" if dirty else "Projects")
        if self._menu is not None:
            self._current.set_text(self._current_text())

    def _current_text(self):
        text = ("Current project: " + project_filename(self.name) if self.file_id
                else "Current project: not saved to Drive yet")
        return text + (" — unsaved changes" if self._dirty else "")

    @property
    def autosave_enabled(self):
        try:
            return js.window.localStorage.getItem(AUTOSAVE_KEY) == "1"
        except Exception:
            return False

    def _remember_autosave(self, enabled):
        try:
            if enabled:
                js.window.localStorage.setItem(AUTOSAVE_KEY, "1")
            else:
                js.window.localStorage.removeItem(AUTOSAVE_KEY)
        except Exception:
            pass  # a preference; blocked site data just means it is not kept

    @property
    def can_autosave(self):
        """Autosave only overwrites a project that already has a Drive file."""
        session = self._drive.session
        return bool(self.file_id and session.signed_in and session.has_drive_access)

    def set_enabled(self, usable):
        """Follow the Drive panel: shown only while signed in with access."""
        if not self.configured:
            return
        self.button_element.style.display = "inline-block" if usable else "none"

    # ------------------------------------------------------------ the dialog

    def _ensure_menu(self):
        if self._menu is not None:
            return
        self._current = P("", style=dict(CURRENT_STYLE))
        self._status = P("", style=dict(STATUS_STYLE))
        self._list = Div(style=dict(LIST_STYLE))

        save = ButtonSuccess("Save", size="small")
        save_as = ButtonSecondary("Save as…", size="small")
        browse = ButtonSecondary("Browse Drive…", size="small")
        close = ButtonSecondary("Close", size="small")

        self._autosave_box = Input("checkbox")
        self._autosave_box._dom_element.checked = self.autosave_enabled
        autosave = Label(
            self._autosave_box,
            Span(" Autosave to Drive — overwrites the open project a few seconds "
                 "after a change. Needs a project already saved to Drive.",
                 style={"font-size": "13px", "color": MUTED_COLOR}),
            style={"display": "block", "margin": "0 0 12px 0", "cursor": "pointer"})

        self._autosave_box.on(
            'change',
            lambda e: self._remember_autosave(self._autosave_box._dom_element.checked))

        @when(save.events.click)
        def on_save(sender, *args):
            asyncio.ensure_future(self._save(save_as=False))

        @when(save_as.events.click)
        def on_save_as(sender, *args):
            asyncio.ensure_future(self._save(save_as=True))

        @when(browse.events.click)
        def on_browse(sender, *args):
            asyncio.ensure_future(self._browse())

        @when(close.events.click)
        def on_close_click(sender, *args):
            self._menu.close()

        body = Div(
            self._current, self._status, self._list, autosave,
            Div(save, save_as, browse, close,
                style=dict(ACTIONS_STYLE)),
        )
        self._menu = Modal(title="Projects", modal_style=MODAL_STYLE)
        self._menu.set_content(body)
        DOM.add(self._menu.element)

    def _show_menu(self, status=None, is_error=False):
        """Open the dialog, refreshed; `status` carries on a message across it."""
        self._ensure_menu()
        self._current.set_text(self._current_text())
        self._autosave_box._dom_element.checked = self.autosave_enabled
        self._set_status("" if status is None else status, is_error)
        self._menu.open()
        asyncio.ensure_future(self._populate())

    def _set_status(self, message, is_error=False):
        if self._menu is None:
            return
        self._status.set_text(message)
        self._status.style.color = ERROR_COLOR if is_error else MUTED_COLOR

    async def _populate(self):
        """Fill the list with the projects Sed/Stats saved, newest first."""
        self._list.clear()
        try:
            found = await self._drive.client.list_files(PROJECT_QUERY)
        except Exception as error:
            self._set_status(f"Could not search Drive: {error}", True)
            return
        projects = [f for f in found
                    if str(f.get("name", "")).lower().endswith(EXTENSION)]
        if not projects:
            self._list.add(P(
                "No projects saved by Sed/Stats yet. Save this one, or use "
                "Browse Drive… to pick a project file from anywhere.",
                style={"font-size": "13px", "color": MUTED_COLOR, "margin": "0"}))
            return
        for project in projects:
            self._list.add(self._item(project))

    def _item(self, project):
        item = Button(style=dict(ITEM_STYLE))
        item.add(Span(project["name"], style={"overflow": "hidden",
                                              "text-overflow": "ellipsis"}),
                 Span(_when(project.get("modifiedTime")), style=ITEM_DATE_STYLE))

        @when(item.events.click)
        def on_click(sender, *args):
            asyncio.ensure_future(self._open_file(project["id"], project["name"]))
        return item

    # ------------------------------------------------------------------ open

    async def _browse(self):
        try:
            self._drive._require_drive()
            # No type filter: Drive types an uploaded .sedprj as whatever it
            # guesses, usually octet-stream, so any filter would hide it.
            picked = await self._drive.session.pick_file(None)
        except Exception as error:
            self._set_status(str(error), True)
            return
        if picked:
            await self._open_file(picked["id"], picked["name"])

    async def _open_file(self, file_id, name):
        if not await self.guard():
            return
        # Closed so the loading curtain (and Google's picker) are not behind it.
        self._menu.close()
        try:
            self._drive._require_drive()
            self._fire_event('load_start', name)
            text = await self._drive.client.download_text(file_id)
            project = load_project(text)
        except Exception as error:
            # A ProjectError's message already says what is wrong with the
            # file (not a project, from a newer version, ...).
            self._fire_event('error', str(error))
            self._show_menu(f"Could not open {name}: {error}", is_error=True)
            return

        self.file_id = file_id
        self.name = _stem(name)
        # The workflow comes back with its steps unrun: some (MDS, unmixing) take seconds, so
        # the user runs it when they want its outputs.
        self._fire_event('project_loaded', project, name)

    def adopt_recovered(self, file_id, name):
        """Take the Drive file a recovered session was working on."""
        self.file_id = file_id or None
        self.name = name or ""

    def detach(self):
        """
        Forget the Drive file this project came from.

        Called when other data replaces the spreadsheet, so the next "Save"
        asks where to save instead of overwriting a project with data that is
        not its own.
        """
        self.file_id = None
        self.name = ""

    # ------------------------------------------------------------------ save

    def _workflow(self):
        return self._get_workflow() if self._get_workflow else None

    async def _overwrite(self, rows, workflow):
        """Write the current state over the project's Drive file."""
        name = project_filename(self.name)
        await self._drive.client.update(
            self.file_id, dump_project(self.name, rows, workflow=workflow), MIME_TYPE)
        self._fire_event('saved', rows, workflow)
        return name

    async def autosave(self):
        """
        Overwrite the open project quietly; the tracker calls this after a change.

        Never creates a file and never asks anything, so it does nothing unless
        there is already a project to overwrite. A failure is shown in the
        dialog and leaves the work marked unsaved.
        """
        rows = list(self._get_rows() if self._get_rows else [])
        if self._busy or not self.can_autosave or not rows:
            return False
        workflow = self._workflow()
        self._busy = True
        try:
            name = await self._overwrite(rows, workflow)
            self._set_status(f"Autosaved {name}.")
            return True
        except Exception as error:
            self._set_status(f"Autosave failed: {error}", True)
            return False
        finally:
            self._busy = False

    async def _save(self, save_as):
        rows = list(self._get_rows() if self._get_rows else [])
        if not rows:
            self._set_status("Nothing to save — the spreadsheet is empty.", True)
            return
        try:
            self._drive._require_drive()
        except Exception as error:
            self._set_status(str(error), True)
            return
        if self._busy:
            return

        client = self._drive.client
        workflow = self._workflow()
        overwrite = bool(self.file_id) and not save_as

        if overwrite:
            self._busy = True
            self._set_status(f"Saving {project_filename(self.name)}…")
            try:
                name = await self._overwrite(rows, workflow)
            except Exception as error:
                self._set_status(f"Could not save: {error}", True)
                return
            finally:
                self._busy = False
            self._set_status(f"Saved {name} ({_steps(workflow)}).")
            return

        # Asking for a name and folder opens another dialog; this one steps
        # aside so the two are never stacked, and comes back with the result.
        self._menu.close()
        status, is_error = "", False
        self._busy = True
        try:
            if self._save_dialog is None:
                self._save_dialog = SaveDialog(
                    self._drive.session, title="Save project to Google Drive")
            choice = await self._save_dialog.ask(
                project_filename(self.name or DEFAULT_NAME))
            if choice is None:
                return
            name = project_filename(choice["name"])
            result = await client.upload(
                name, dump_project(_stem(name), rows, workflow=workflow),
                mime_type=MIME_TYPE, folder_id=choice["folder_id"])
            self.file_id = result.get("id")
            self.name = _stem(result.get("name", name))
            self._fire_event('saved', rows, workflow)
            status = (f"Saved {result.get('name', name)} to "
                      f"{choice['folder_name']} ({_steps(workflow)}).")
        except Exception as error:
            status, is_error = f"Could not save: {error}", True
            self._fire_event('error', str(error))
        finally:
            self._busy = False
            self._show_menu(status, is_error)


def _steps(workflow):
    """'3 steps' for a status line."""
    count = len((workflow or {}).get("steps") or [])
    return f"{count} step{'s' if count != 1 else ''}"


def _stem(filename):
    """A file name without the project extension."""
    filename = str(filename)
    return filename[:-len(EXTENSION)] if filename.lower().endswith(EXTENSION) else filename


def _when(timestamp):
    """Drive's RFC 3339 time as 'YYYY-MM-DD HH:MM UTC', or blank."""
    text = str(timestamp or "")
    return f"{text[:10]} {text[11:16]} UTC" if len(text) >= 16 else ""
