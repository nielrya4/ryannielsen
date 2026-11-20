"""
An in-page yes/no dialog, in place of the browser's `window.confirm`.

The native dialog is the wrong tool here for three reasons. Browsers may
suppress it (Firefox's "prevent this page from creating dialogs", a
background tab in Chrome), and a suppressed one answers "cancel" instantly —
which, for a prompt that offers to restore saved work, means silently
discarding it. It also blocks the whole page, including Python, while it is
up. And it cannot say what its buttons do.

This one is an ordinary modal. It answers True or False only when a button is
clicked. If it is not dismissible, closing it any other way (Escape, the
backdrop, the X) is not an answer at all: the dialog stays up.
"""
import asyncio

from antioch.dom import DOM
from antioch.elements import Div, P
from antioch.event import when
from antioch.macros import Modal
from component_lib.button import ButtonSecondary, ButtonSuccess

MODAL_STYLE = {"max-width": "460px", "width": "92vw"}
MESSAGE_STYLE = {"font-size": "14px", "color": "#333", "margin": "0 0 16px 0",
                 "white-space": "pre-line"}
ACTIONS_STYLE = {"display": "flex", "justify-content": "flex-end", "gap": "8px"}


class ConfirmDialog:
    """
    Usage:
        dialog = ConfirmDialog("Unsaved changes")
        answer = await dialog.ask("Discard them?", "Discard", "Keep editing")
        # True, False, or None if a dismissible dialog was closed unanswered
    """

    def __init__(self, title):
        self._future = None
        self._dismissible = True
        self._message = P("", style=dict(MESSAGE_STYLE))
        self._yes = ButtonSuccess("OK", size="small")
        self._no = ButtonSecondary("Cancel", size="small")

        @when(self._yes.events.click)
        def on_yes(sender, *args):
            self._answer(True)

        @when(self._no.events.click)
        def on_no(sender, *args):
            self._answer(False)

        body = Div(self._message, Div(self._no, self._yes, style=dict(ACTIONS_STYLE)))
        # Dismissal is decided per ask(), so the modal allows it and the close
        # event decides whether it counts.
        self.modal = Modal(title=title, modal_style=MODAL_STYLE)
        self.modal.set_content(body)
        DOM.add(self.modal.element)

        @when(self.modal.events.close)
        def on_close(sender, *args):
            if self._future is None:
                return  # closed by a button, which already answered
            if self._dismissible:
                self._answer(None)
            else:
                # Not an answer. Put it back on the next turn rather than
                # inside the close handler, which is still unwinding.
                asyncio.get_event_loop().call_later(0.05, self._reopen)

    async def ask(self, message, yes_text="OK", no_text="Cancel", dismissible=True):
        # One question at a time; a second caller is told "no answer".
        if self._future is not None:
            return None
        self._message.set_text(message)
        self._yes.set_text(yes_text)
        self._no.set_text(no_text)
        self._dismissible = dismissible
        self._future = asyncio.get_event_loop().create_future()
        self.modal.open()
        return await self._future

    def _reopen(self):
        if self._future is not None:
            self.modal.open()

    def _answer(self, value):
        future, self._future = self._future, None
        if future is not None and not future.done():
            future.set_result(value)
        self.modal.close()


class MessageDialog:
    """
    A modal that shows a long text in full — an error that does not fit on a block — which can be
    selected, and copied with one button.

    Usage:
        dialog = MessageDialog()
        dialog.show("Step 2: Scatterplot", "A scatterplot needs at least one set of points.")
    """

    TEXT_STYLE = {"font-size": "14px", "color": "#333", "margin": "0 0 16px 0",
                  "white-space": "pre-wrap", "word-break": "break-word", "user-select": "text",
                  "max-height": "50vh", "overflow-y": "auto", "background": "#f8f9fa",
                  "border": "1px solid #e9ecef", "border-radius": "4px", "padding": "10px"}

    def __init__(self):
        self._text = P("", style=dict(self.TEXT_STYLE))
        self._copy = ButtonSecondary("Copy", size="small")
        close = ButtonSuccess("Close", size="small")

        @when(self._copy.events.click)
        def on_copy(sender, *args):
            import js
            try:
                js.navigator.clipboard.writeText(self._plain)
                self._copy.set_text("Copied")
            except Exception:
                self._copy.set_text("Select the text and copy it")

        @when(close.events.click)
        def on_close(sender, *args):
            self.modal.close()

        self._plain = ""
        self.modal = Modal(title="Message", modal_style={"max-width": "640px", "width": "92vw"})
        self.modal.set_content(Div(self._text, Div(self._copy, close, style=dict(ACTIONS_STYLE))))
        DOM.add(self.modal.element)

    def show(self, title, message):
        self._plain = str(message)
        self._text.set_text(self._plain)
        self._copy.set_text("Copy")
        self.modal.set_title(title)
        self.modal.open()
