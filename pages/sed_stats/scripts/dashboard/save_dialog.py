"""
The "Save to Drive" dialog: pick a name and a destination folder.

Replaces a bare `js.prompt`, which could only ask for a name and gave the user
no say in where the file landed — everything went to the root of My Drive.

Choosing the folder through Google's own picker is also what makes writing
into it legal under the `drive.file` scope: the app may write where the user
pointed it, and nowhere else.
"""
import asyncio

from antioch.dom import DOM
from antioch.elements import Div, Input, Label, P, Span
from antioch.event import when
from antioch.macros import Modal

from component_lib.button import ButtonSecondary, ButtonSuccess

MODAL_STYLE = {"max-width": "460px", "width": "92vw"}
ROW_STYLE = {"margin-bottom": "14px"}
LABEL_STYLE = {
    "display": "block", "font-size": "13px", "font-weight": "600",
    "margin-bottom": "5px", "color": "#333",
}
INPUT_STYLE = {
    "width": "100%", "box-sizing": "border-box", "padding": "8px 10px",
    "font-size": "14px", "border": "1px solid #ccc", "border-radius": "4px",
}
FOLDER_ROW_STYLE = {
    "display": "flex", "align-items": "center", "gap": "10px",
    "flex-wrap": "wrap",
}
FOLDER_NAME_STYLE = {
    "font-size": "13px", "color": "#333", "flex": "1", "min-width": "0",
    "overflow": "hidden", "text-overflow": "ellipsis", "white-space": "nowrap",
}
ERROR_STYLE = {"font-size": "13px", "color": "#b00020", "margin": "0 0 10px 0"}
ACTIONS_STYLE = {
    "display": "flex", "justify-content": "flex-end", "gap": "8px",
    "margin-top": "18px",
}

MY_DRIVE = "My Drive"


class SaveDialog:
    """
    Asks for a filename and destination, then hands both back.

    Usage:
        dialog = SaveDialog(session)
        choice = await dialog.ask("plot.svg")
        if choice:                      # None when cancelled
            name, folder_id = choice["name"], choice["folder_id"]
    """

    def __init__(self, session, title="Save to Google Drive"):
        self.session = session
        self._future = None
        self._folder_id = None

        self._name = Input("text", style=INPUT_STYLE)
        self._folder_label = Span(MY_DRIVE, style=FOLDER_NAME_STYLE)
        self._error = P("", style=ERROR_STYLE)
        self._error.style.display = "none"

        choose = ButtonSecondary("Choose folder…", size="small")
        reset = ButtonSecondary("My Drive", size="small")
        cancel = ButtonSecondary("Cancel", size="small")
        save = ButtonSuccess("Save", size="small")

        @when(choose.events.click)
        def on_choose(sender, *args):
            asyncio.ensure_future(self._choose_folder())

        @when(reset.events.click)
        def on_reset(sender, *args):
            self._set_folder(None, MY_DRIVE)

        @when(cancel.events.click)
        def on_cancel(sender, *args):
            self.modal.close()

        @when(save.events.click)
        def on_save(sender, *args):
            self._submit()

        # Enter in the name field is the obvious way to accept this dialog.
        self._name.on("keydown", self._on_key)

        body = Div(
            Div(Label("File name", style=LABEL_STYLE), self._name,
                style=ROW_STYLE),
            Div(Label("Destination", style=LABEL_STYLE),
                Div(self._folder_label, choose, reset, style=FOLDER_ROW_STYLE),
                style=ROW_STYLE),
            self._error,
            Div(cancel, save, style=ACTIONS_STYLE),
        )

        self.modal = Modal(title=title, modal_style=MODAL_STYLE)
        self.modal.set_content(body)
        DOM.add(self.modal.element)

        @when(self.modal.events.close)
        def on_close(sender, *args):
            # Covers the backdrop, the X and Escape, all of which bypass the
            # buttons and would otherwise leave the caller awaiting forever.
            self._finish(None)

    # ------------------------------------------------------------------- ask

    async def ask(self, suggested_name):
        """
        Show the dialog and wait for the user.

        Returns {"name", "folder_id", "folder_name"} or None if cancelled.
        """
        self._name.value = suggested_name
        self._show_error("")
        self._future = asyncio.get_event_loop().create_future()
        self.modal.open()
        self._focus_name()
        return await self._future

    def _focus_name(self):
        try:
            self._name.dom_element.focus()
            self._name.dom_element.select()
        except Exception:
            # Focus is a convenience; never let it break the dialog.
            pass

    # --------------------------------------------------------------- internals

    def _on_key(self, dom_event):
        if getattr(dom_event, "key", None) == "Enter":
            dom_event.preventDefault()
            self._submit()

    def _set_folder(self, folder_id, folder_name):
        self._folder_id = folder_id
        self._folder_label.set_text(folder_name)

    def _show_error(self, message):
        self._error.set_text(message)
        self._error.style.display = "block" if message else "none"

    async def _choose_folder(self):
        try:
            picked = await self.session.pick_folder()
        except Exception as error:
            self._show_error(str(error))
            return
        if picked:
            self._set_folder(picked["id"], picked["name"])
            self._show_error("")

    def _submit(self):
        name = str(self._name.value or "").strip()
        if not name:
            self._show_error("Give the file a name.")
            return
        self._finish({
            "name": name,
            "folder_id": self._folder_id,
            "folder_name": self._folder_label.dom_element.textContent,
        })
        # Closing fires the modal's close event, which calls _finish(None);
        # that is harmless because the pending future has already been taken.
        self.modal.close()

    def _finish(self, result):
        """Resolve the waiter exactly once, whichever way the dialog ended."""
        future, self._future = self._future, None
        if future is not None and not future.done():
            future.set_result(result)
