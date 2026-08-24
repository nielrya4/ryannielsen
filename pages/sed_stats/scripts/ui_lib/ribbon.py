"""Toolbar of tool buttons, one per action."""
from antioch.elements import Div
from antioch.event import when
from antioch.macros.base import Macro
from component_lib import ButtonInfo

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
        button = ButtonInfo(label, size="small", active=key == self._active)
        @when(button.events.click)
        def on_click(sender, *args):
            self.select(key)
        self._buttons[key] = button
        self._get_element('container').add(button)
        return self

    def select(self, key):
        """Select a tool, or pass None to clear the selection."""
        self._active = key
        for tool_key, button in self._buttons.items():
            active = tool_key == key
        if key is not None:
            self._fire_event('select', key)
        return self

    @property
    def active(self):
        return self._active
