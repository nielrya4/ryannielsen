"""File-picker widget that parses spreadsheet files into row dicts."""
import js

from antioch.elements import Button, Input, Span
from antioch.macros.base import Macro

from .importers import parse_file, SUPPORTED_EXTENSIONS


class SpreadsheetUpload(Macro):
    """
    Button that opens the browser file picker for csv/xls/xlsx files and
    fires a `data_loaded` event with the parsed rows.

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

        self._create_event('data_loaded')
        self._create_event('error')

        self._init_macro()

    def _create_elements(self):
        container = self._create_container({"display": "inline-block"})

        file_input = self._register_element(
            'file_input', Input('file', style={"display": "none"})
        )
        file_input.set_attribute("accept", self._get_state('accept'))

        button = self._register_element('button', Button(self._get_state('label')))
        status = self._register_element('status', Span("", style={"margin-left": "10px"}))

        button._dom_element.addEventListener(
            'click', self._create_proxy(lambda e: file_input._dom_element.click())
        )
        file_input._dom_element.addEventListener(
            'change', self._create_proxy(self._handle_file_change)
        )

        container.add(file_input, button, status)
        return container

    def _handle_file_change(self, event):
        files = event.target.files
        if files.length == 0:
            return
        file = files.item(0)
        filename = file.name
        is_csv = filename.lower().endswith(".csv")
        reader = js.FileReader.new()

        def handle_load(_evt):
            try:
                if is_csv:
                    content = reader.result
                else:
                    content = bytes(js.Uint8Array.new(reader.result).to_py())
                rows = parse_file(filename, content)
                self._get_element('status').set_text(f"Loaded {len(rows)} rows from {filename}")
                self._fire_event('data_loaded', rows, filename)
            except Exception as e:
                self._get_element('status').set_text(f"Error: {e}")
                self._fire_event('error', str(e))
            # Reset so re-selecting the same file fires change again
            event.target.value = ""

        reader.onload = self._create_proxy(handle_load)
        if is_csv:
            reader.readAsText(file)
        else:
            reader.readAsArrayBuffer(file)