"""
An in-page dialog that asks for one line of text, in place of the browser's `window.prompt`.

For the same reasons as the confirm dialog: the native one can be suppressed (and then answers
"cancel" at once), blocks the page, and cannot validate or say what it is for.
"""
import asyncio

from antioch.dom import DOM
from antioch.elements import Div, Input, Label, P
from antioch.event import when
from antioch.macros import Modal
from component_lib.button import ButtonSecondary, ButtonSuccess

MODAL_STYLE = {"max-width": "420px", "width": "92vw"}
LABEL_STYLE = {"font-size": "13px", "color": "#333", "display": "block", "margin": "0 0 6px 0"}
INPUT_STYLE = {"width": "100%", "box-sizing": "border-box", "padding": "7px 9px", "font-size": "14px",
               "border": "1px solid #cfd6dd", "border-radius": "4px"}
ACTIONS_STYLE = {"display": "flex", "justify-content": "flex-end", "gap": "8px", "margin-top": "14px"}


class PromptDialog:
    """
    Usage:
        dialog = PromptDialog()
        name = await dialog.ask("Rename column", "Column name", "age_Ma")
        # the text, or None if it was cancelled or closed
    """

    def __init__(self):
        self._future = None
        self._label = Label("", style=dict(LABEL_STYLE))
        self._input = Input("text", style=dict(INPUT_STYLE))
        self._ok = ButtonSuccess("OK", size="small")
        self._cancel = ButtonSecondary("Cancel", size="small")

        @when(self._ok.events.click)
        def on_ok(sender, *args):
            self._answer(str(self._input._dom_element.value))

        @when(self._cancel.events.click)
        def on_cancel(sender, *args):
            self._answer(None)

        # Enter accepts, as in any single-line form.
        self._input.on("keydown", lambda e: self._answer(str(self._input._dom_element.value))
                       if e.key == "Enter" else None)

        self.modal = Modal(title="", modal_style=dict(MODAL_STYLE))
        self.modal.set_content(Div(self._label, self._input,
                                   Div(self._cancel, self._ok, style=dict(ACTIONS_STYLE))))
        DOM.add(self.modal.element)

        @when(self.modal.events.close)
        def on_close(sender, *args):
            self._answer(None)

    async def ask(self, title, label, value=""):
        if self._future is not None:
            return None                 # one question at a time
        self.modal.set_title(title)
        self._label.set_text(label)
        self._input._dom_element.value = value or ""
        self._future = asyncio.get_event_loop().create_future()
        self.modal.open()
        # The field is not focusable until the modal is shown.
        asyncio.get_event_loop().call_later(0.05, self._focus)
        return await self._future

    def _focus(self):
        try:
            self._input._dom_element.focus()
            self._input._dom_element.select()
        except Exception:
            pass

    def _answer(self, value):
        future, self._future = self._future, None
        if future is None or future.done():
            return
        self.modal.close()
        future.set_result(value)
