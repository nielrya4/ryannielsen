"""Tabulator-backed spreadsheet macro."""
import js

from antioch.elements import Div
from antioch.macros.js_library import JSLibraryMacro


class TabulatorSheet(JSLibraryMacro):
    """
    Editable spreadsheet backed by the Tabulator JS library.

    Usage:
        sheet = TabulatorSheet(data=[{"a": 1, "b": 2}], height="400px")
        DOM.add(sheet.element)

        @when(sheet.events.data_change)
        def on_change(sender, data):
            ...
    """

    def __init__(self, data=None, columns=None, height="400px", options=None, **kwargs):
        """
        Args:
            data: List of row dicts
            columns: Tabulator column definitions; if None, columns are
                     auto-generated from the data (and regenerate on set_data)
            height: CSS height of the table
            options: Extra Tabulator options merged over the defaults
        """
        super().__init__(macro_type="tabulator_sheet", **kwargs)

        self._set_state(
            data=data or [],
            columns=columns,
            height=height,
            options=options or {},
        )

        self._create_event('data_change')

        self._init_macro()

    def _get_library_dependencies(self):
        return {
            'scripts': ['antioch/lib/vendor/tabulator.min.js'],
            'stylesheets': ['antioch/lib/vendor/tabulator.min.css'],
        }

    def _get_library_global_name(self):
        return 'Tabulator'

    def _create_elements(self):
        container = self._register_element(
            'container', self._create_container({"width": "100%"})
        )
        holder = self._register_element('holder', Div())
        holder.set_attribute("id", f"tabulator_{self._id}")
        container.add(holder)
        return container

    def _column_definitions(self):
        columns = self._get_state('columns')
        if columns:
            return columns
        fields = []
        for row in self._get_state('data'):
            for key in row:
                if key not in fields:
                    fields.append(key)
        return [{'title': field, 'field': field, 'editor': 'input'} for field in fields]

    def _build_options(self):
        options = {
            'data': self._get_state('data'),
            'height': self._get_state('height'),
            'layout': 'fitColumns',
            'columns': self._column_definitions(),
        }
        options.update(self._get_state('options'))
        return options

    def _create_js_instance(self):
        holder = self._get_element('holder')
        table = js.Tabulator.new(holder._dom_element, self._to_js(self._build_options()))
        # dataChanged passes the plain data array; Tabulator components (cell,
        # row) must never cross into Python — Pyodide's capability probes
        # trigger Tabulator's unknown-property warnings.
        table.on('dataChanged', self._create_proxy(self._handle_data_changed))
        return table

    def _handle_data_changed(self, data):
        rows = data.to_py()
        self._set_state(data=rows)
        self._fire_event('data_change', rows)

    # ========== Public API ==========

    def get_data(self):
        """Current table contents as a list of row dicts."""
        if not self.is_initialized:
            return list(self._get_state('data'))
        return self.js_instance.getData().to_py()

    def set_data(self, data):
        """Replace table contents, regenerating auto columns from the new data."""
        self._set_state(data=data)
        if self.is_initialized:
            if not self._get_state('columns'):
                self.js_instance.setColumns(self._to_js(self._column_definitions()))
            self.js_instance.setData(self._to_js(data))
        self._fire_event('data_change', data)
        return self

    def redraw(self):
        """Recompute layout. Needed after the table becomes visible again:
        Tabulator sizes itself on render and measures zero while hidden."""
        if self.is_initialized:
            self.js_instance.redraw(True)
        return self

    @property
    def is_ready(self):
        return self.is_initialized