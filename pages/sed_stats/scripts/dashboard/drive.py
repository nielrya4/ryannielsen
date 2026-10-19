"""
Sign in with Google, and move spreadsheets between Drive and the grid.

The panel hides itself entirely when no Cloud project is configured (see
GOOGLE_CLIENT_ID and friends in `config`), so a copy of the app without
credentials has no Google features rather than buttons that cannot work.
"""
import asyncio

from antioch.elements import Button, Div, Span
from antioch.event import when
from antioch.macros.base import Macro
from component_lib.button import ButtonSecondary

from drive_lib import DriveClient, GoogleSession, PICKABLE
from spreadsheet_lib import parse_file, rows_to_csv

from .config import GOOGLE_API_KEY, GOOGLE_APP_ID, GOOGLE_CLIENT_ID
from .save_dialog import SaveDialog

STATUS_STYLE = {"margin-left": "10px", "font-size": "13px", "color": "#555"}
ERROR_COLOR = "#b00020"
DEFAULT_SAVE_NAME = "sed-stats-data.csv"

# Shown when sign-in succeeded but the Drive checkbox was left unticked on
# Google's consent screen — a valid token that 403s on every file call.
NO_DRIVE_MESSAGE = ("Signed in, but Drive access was not granted. "
                    "Click Sign out, then sign in again and tick the Google "
                    "Drive permission.")

# The account control sits in the dark header bar, so it is styled against that
# rather than reusing the page's buttons, which assume a light background.
ACCOUNT_STYLE = {
    "display": "flex", "align-items": "center", "gap": "10px",
    "margin-left": "auto", "flex-shrink": "0",
}
ACCOUNT_LABEL_STYLE = {
    "font-size": "13px", "color": "#cfd8e3",
    "max-width": "220px", "overflow": "hidden",
    "text-overflow": "ellipsis", "white-space": "nowrap",
}
ACCOUNT_BUTTON_STYLE = {
    "background-color": "transparent", "color": "#fff",
    "border": "1px solid rgba(255,255,255,0.4)",
    "padding": "5px 12px", "font-size": "13px", "cursor": "pointer",
    "border-radius": "4px", "white-space": "nowrap",
}
ACCOUNT_BUTTON_HOVER = "rgba(255,255,255,0.15)"


class DrivePanel(Macro):
    """
    Sign-in, "Open from Drive" and "Save to Drive" controls.

    Usage:
        drive = DrivePanel(get_rows=table.get_data)
        DOM.add(drive.element)

        @when(drive.events.data_loaded)
        def on_loaded(sender, rows, filename):
            ...

    Fires `data_loaded(rows, filename)` on a successful open, and
    `error(message)` on any failure.
    """

    def __init__(self, get_rows=None, **kwargs):
        super().__init__(macro_type="drive_panel", **kwargs)

        self._get_rows = get_rows
        self._email = None
        # Built lazily: the modal mounts itself into the page, and an
        # unconfigured app should add nothing.
        self._dialog = None
        self.session = GoogleSession(
            client_id=GOOGLE_CLIENT_ID,
            api_key=GOOGLE_API_KEY,
            app_id=GOOGLE_APP_ID,
        )
        self.client = DriveClient(self.session)

        # Mirrors SpreadsheetUpload so the app can drive one overlay for both.
        self._create_event('load_start')
        self._create_event('data_loaded')
        self._create_event('error')
        self._create_event('sign_in_change')

        self._init_macro()

    @property
    def configured(self):
        return self.session.configured

    @property
    def dialog(self):
        if self._dialog is None:
            self._dialog = SaveDialog(self.session)
        return self._dialog

    # -------------------------------------------------------------- elements

    def _create_elements(self):
        container = self._register_element(
            'container',
            self._create_container({"display": "inline-flex",
                                    "align-items": "center",
                                    "flex-wrap": "wrap", "gap": "8px"}),
        )
        self._register_element('account', self._account_control())

        if not self.configured:
            # Nothing to sign in to. Leave the container empty and hidden so
            # the surrounding layout collapses around it.
            container.style.display = "none"
            return container

        # Created enabled, then disabled: ButtonPrimary wires its click
        # handler only when it renders in an enabled state, and set_disabled
        # never wires it afterwards, so a button born disabled stays dead.
        open_button = self._register_element(
            'open', ButtonSecondary("Open from Drive", size="small"))
        save_button = self._register_element(
            'save', ButtonSecondary("Save to Drive", size="small"))
        open_button.set_disabled(True)
        save_button.set_disabled(True)
        self._register_element('status', Span("", style=STATUS_STYLE))

        @when(open_button.events.click)
        def on_open(sender, *args):
            asyncio.ensure_future(self._open())

        @when(save_button.events.click)
        def on_save(sender, *args):
            asyncio.ensure_future(self._save())

        container.add(open_button, save_button, self._get_element('status'))
        return container

    def _account_control(self):
        """
        The signed-in indicator for the header bar.

        Lives apart from the file controls: whether you are signed in is a
        property of the whole app, so it belongs in the title bar rather than
        buried in whichever tab happens to be open.
        """
        account = Div(style=dict(ACCOUNT_STYLE))
        if not self.configured:
            account.style.display = "none"
            return account

        label = self._register_element(
            'account_label', Span("", style=ACCOUNT_LABEL_STYLE))
        button = self._register_element(
            'account_button',
            Button("Sign in with Google", style=dict(ACCOUNT_BUTTON_STYLE)))

        def hover(active):
            # antioch's style proxy takes underscore names, not CSS hyphens.
            button.style.background_color = (
                ACCOUNT_BUTTON_HOVER if active else "transparent")

        button.on_mouseenter(lambda e: hover(True))
        button.on_mouseleave(lambda e: hover(False))

        @when(button.events.click)
        def on_click(sender, *args):
            asyncio.ensure_future(
                self._sign_out() if self.session.signed_in else self._sign_in())

        account.add(label, button)
        return account

    @property
    def account_element(self):
        """The header-bar control; an empty hidden Div when not configured."""
        return self._get_element('account')

    # ---------------------------------------------------------------- status

    def _set_status(self, message, is_error=False):
        if not self.configured:
            return
        status = self._get_element('status')
        status.set_text(message)
        status.style.color = ERROR_COLOR if is_error else STATUS_STYLE["color"]

    def _fail(self, error):
        self._set_status(f"Error: {error}", is_error=True)
        self._fire_event('error', str(error))

    def _sync_buttons(self):
        signed_in = self.session.signed_in
        # Being signed in is not enough: the Drive scope is granted separately.
        usable = signed_in and self.session.has_drive_access
        self._get_element('account_button').set_text(
            "Sign out" if signed_in else "Sign in with Google")
        self._get_element('account_label').set_text(
            (self._email or "Signed in") if signed_in else "")
        for name in ('open', 'save'):
            self._get_element(name).set_disabled(not usable)
        self._fire_event('sign_in_change', usable)

    # ------------------------------------------------------------------ auth

    async def _sign_in(self):
        button = self._get_element('account_button')
        button.set_text("Signing in…")
        self._get_element('account_label').set_text("")
        try:
            await self.session.sign_in()
            # Display only; a failure here leaves the status reading
            # "Signed in", which is still true.
            self._email = await self.session.account_email()
            self._set_status(
                "" if self.session.has_drive_access else NO_DRIVE_MESSAGE,
                is_error=not self.session.has_drive_access)
        except Exception as error:
            # A cancelled popup is the common case here and is not a fault, so
            # it reads as a plain status rather than an error.
            self._email = None
            self._set_status("Sign-in cancelled."
                             if _was_cancelled(error) else f"Error: {error}")
        finally:
            self._sync_buttons()

    async def _sign_out(self):
        self.session.sign_out()
        self._email = None
        self._set_status("Signed out.")
        self._sync_buttons()

    async def restore(self):
        """
        Re-attach a previous session on page load, without prompting.

        Runs in the background after the app is up: it needs a network round
        trip for Google's script, and nothing else should wait on it.
        """
        if not self.configured:
            return False
        button = self._get_element('account_button')
        button.set_text("Restoring…")
        try:
            if not await self.session.restore():
                return False
            self._email = await self.session.account_email()
            if not self.session.has_drive_access:
                self._set_status(NO_DRIVE_MESSAGE, is_error=True)
            return True
        except Exception:
            # A failed restore is an ordinary outcome, not an error worth
            # showing: the user just sees the sign-in button.
            return False
        finally:
            self._sync_buttons()

    # ------------------------------------------------------------------ open

    async def _open(self):
        button = self._get_element('open')
        button.set_loading(True)
        try:
            self._require_drive()
            # Google's picker renders in its own iframe and can take a few
            # seconds; without this the button just sits there looking stuck.
            self._set_status("Opening Google Drive…")
            picked = await self.session.pick_file(PICKABLE)
            if picked is None:
                self._set_status("")
                return
            # Fired only now: the overlay must not cover Google's picker,
            # which the user is still interacting with until this point.
            self._fire_event('load_start', picked["name"])
            self._set_status(f"Opening {picked['name']}…")
            name, content = await self.client.download(
                picked["id"], picked["mimeType"])
            rows = parse_file(name, content)
            self._set_status(f"Loaded {len(rows)} rows from {name}")
            self._fire_event('data_loaded', rows, name)
        except Exception as error:
            self._fail(error)
        finally:
            button.set_loading(False)

    # ------------------------------------------------------------------ save

    async def _save(self):
        rows = list(self._get_rows() if self._get_rows else [])
        if not rows:
            self._set_status("Nothing to save — the spreadsheet is empty.")
            return

        try:
            self._require_drive()
        except Exception as error:
            self._fail(error)
            return

        choice = await self.dialog.ask(DEFAULT_SAVE_NAME)
        if choice is None:
            return
        name = choice["name"]
        if not name.lower().endswith(".csv"):
            name += ".csv"

        button = self._get_element('save')
        button.set_loading(True)
        self._set_status(f"Saving {name}…")
        try:
            result = await self.client.upload(
                name, rows_to_csv(rows), folder_id=choice["folder_id"])
            self._set_status(
                f"Saved {result.get('name', name)} to {choice['folder_name']}.")
        except Exception as error:
            self._fail(error)
        finally:
            button.set_loading(False)

    # ---------------------------------------------------------- for the plots

    def _require_drive(self):
        """
        Raise before a call that is certain to 403.

        The gallery's save buttons exist as soon as Drive is configured, so
        they can be clicked while signed out or without the Drive scope.
        """
        if not self.session.signed_in:
            raise RuntimeError("Sign in with Google first.")
        if not self.session.has_drive_access:
            raise RuntimeError(NO_DRIVE_MESSAGE)

    async def save_bytes(self, filename, data, mime_type):
        """
        Upload an already-built payload, e.g. a plot's SVG or zip.

        Asks for a name and destination first, exactly as the spreadsheet save
        does, so a graph does not silently land in the root of My Drive.
        """
        self._require_drive()
        choice = await self.dialog.ask(filename)
        if choice is None:
            return None
        result = await self.client.upload(
            choice["name"], data, mime_type=mime_type,
            folder_id=choice["folder_id"])
        self._set_status(
            f"Saved {result.get('name', choice['name'])} "
            f"to {choice['folder_name']}.")
        return result


def _was_cancelled(error):
    text = str(error).lower()
    return "popup" in text or "cancel" in text or "closed" in text

