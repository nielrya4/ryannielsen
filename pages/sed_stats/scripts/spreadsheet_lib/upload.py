"""File-picker widget that parses spreadsheet files into row dicts."""
import js

from antioch.elements import Input, Span
from antioch.event import when
from antioch.macros.base import Macro
from component_lib.button import ButtonInfo

from .importers import parse_file, SUPPORTED_EXTENSIONS

STATUS_STYLE = {"margin-left": "10px", "font-size": "13px", "color": "#555"}
ERROR_COLOR = "#b00020"


class SpreadsheetUpload(Macro):
    """
    Button that opens the browser file picker for csv/xls/xlsx files and
    fires a `data_loaded` event with the parsed rows.

    Events: `load_start(filename)`, then either `data_loaded(rows, filename)`
    or `error(message)`.

    Usage:
        upload = SpreadsheetUpload()
        DOM.add(upload.element)

        @when(upload.events.data_loaded)
        def on_loaded(sender, rows, filename):
            ...
    """

    def __init__(self, label="Upload spreadsheet", accept=None, **kwargs):
        super().__init__(macro_type="spreadsheet_upload", **kwargs)

        self._set_state(
            label=label,
            accept=accept or ",".join(SUPPORTED_EXTENSIONS),
        )

        # Fired once a file is actually being read, so the app can put a
        # loading overlay up for the parse, which blocks the UI thread on a
        # large workbook. Always followed by data_loaded or error.
        self._create_event('load_start')
        self._create_event('data_loaded')
        self._create_event('error')

        self._init_macro()

    def _create_elements(self):
        container = self._register_element(
            'container', self._create_container({"display": "inline-block"})
        )

        # The native file input is unstyleable, so it stays hidden and the
        # button forwards clicks to it.
        file_input = self._register_element(
            'file_input', Input('file', style={"display": "none"})
        )
        file_input.set_attribute("accept", self._get_state('accept'))

        button = self._register_element(
            'button', ButtonInfo(self._get_state('label'), size="small")
        )
        self._register_element('status', Span("", style=STATUS_STYLE))

        @when(button.events.click)
        def on_click(sender, *args):
            try:
                file_input._dom_element.click()
            except Exception as error:
                self._fail(error)

        @when(file_input.events.change)
        def on_change(sender, dom_event=None, *args):
            # antioch's Event.fire swallows handler exceptions into a print(),
            # so anything raised here would leave the widget looking inert.
            try:
                self._handle_file_change(dom_event)
            except Exception as error:
                self._fail(error)

        container.add(file_input, button, self._get_element('status'))
        return container

    # ------------------------------------------------------------------ status

    def _set_status(self, message, is_error=False):
        status = self._get_element('status')
        status.set_text(message)
        status.style.color = ERROR_COLOR if is_error else STATUS_STYLE["color"]

    def _fail(self, message):
        self._set_status(f"Error: {message}", is_error=True)
        self._fire_event('error', str(message))

    # ------------------------------------------------------------------ reading

    def _handle_file_change(self, dom_event):
        if dom_event is None:
            self._fail("no file event was delivered")
            return
        target = dom_event.target
        files = target.files
        # Not `is None`: Pyodide represents JS null as a `jsnull` sentinel,
        # which is not Python None.
        if not files or files.length == 0:
            return

        file = files.item(0)
        filename = file.name
        # csv is text; the binary formats have to come across as bytes.
        is_csv = filename.lower().endswith(".csv")
        reader = js.FileReader.new()

        def reset():
            # Clearing the value lets the same file be picked again and still
            # fire `change`.
            target.value = ""

        def handle_load(_evt):
            try:
                if is_csv:
                    content = reader.result
                else:
                    content = bytes(js.Uint8Array.new(reader.result).to_py())
                rows = parse_file(filename, content)
                self._set_status(f"Loaded {len(rows)} rows from {filename}")
                self._fire_event('data_loaded', rows, filename)
            except Exception as e:
                self._fail(e)
            finally:
                reset()

        def handle_error(_evt):
            self._fail(f"could not read {filename}")
            reset()

        reader.onload = self._create_proxy(handle_load)
        reader.onerror = self._create_proxy(handle_error)

        self._set_status(f"Reading {filename}…")
        self._fire_event('load_start', filename)
        if is_csv:
            reader.readAsText(file)
        else:
            reader.readAsArrayBuffer(file)
