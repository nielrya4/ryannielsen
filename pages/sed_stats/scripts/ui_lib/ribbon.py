"""Toolbar of tool buttons, one per action."""
from antioch.elements import Button, Div
from antioch.macros.base import Macro


class Ribbon(Macro):
    """
    Horizontal button bar. Each tool is (key, label); pressing one fires
    `select` with that key, and the pressed tool renders as active.

        ribbon = Ribbon(tools=[("mds", "MDS")])

        @when(ribbon.events.select)
        def on_select(sender, key):
            ...
    """

    def __init__(self, tools=None, **kwargs):
        super().__init__(macro_type="ribbon", **kwargs)

        self._buttons = {}
        self._active = None

        self._create_event('select')
        self._init_macro()

        for key, label in (tools or []):
            self.add_tool(key, label)

    def _create_elements(self):
        return self._register_element('container', self._create_container({
            "display": "flex", "flex-wrap": "wrap", "gap": "8px",
            "padding": "10px", "background-color": "#f8f9fa",
            "border": "1px solid #dee2e6", "border-radius": "6px",
            "margin-bottom": "16px",
        }))

    def add_tool(self, key, label):
        button = Button(label, style={
            "padding": "8px 16px", "border": "1px solid #ced4da",
            "border-radius": "4px", "cursor": "pointer", "font-size": "14px",
            "background-color": "#fff", "color": "#212529",
        })
        button.on_click(lambda e, k=key: self.select(k))
        self._buttons[key] = button
        self._get_element('container').add(button)
        return self

    def select(self, key):
        """Select a tool, or pass None to clear the selection."""
        self._active = key
        for tool_key, button in self._buttons.items():
            active = tool_key == key
            button.style.background_color = "#0066cc" if active else "#fff"
            button.style.color = "#fff" if active else "#212529"
            button.style.border_color = "#0066cc" if active else "#ced4da"
        if key is not None:
            self._fire_event('select', key)
        return self

    @property
    def active(self):
        return self._active
