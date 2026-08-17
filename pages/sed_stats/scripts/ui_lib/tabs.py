"""Tab bar whose panels stay mounted.

Antioch's own Tabs macro swaps content by clearing the container's innerHTML,
which detaches JS-backed widgets (Tabulator, Plotly) and leaves them to
re-render on reattach. Toggling `display` instead keeps every panel in the
DOM, so those widgets only ever need a redraw, never a rebuild.
"""
from antioch.elements import Button, Div
from antioch.macros.base import Macro


class TabItem:
    def __init__(self, title, content):
        self.title = title
        self.content = content
        self.button = None


class TabView(Macro):
    """
    Horizontal tabs.

        view = TabView(tabs=[TabItem("Outputs", outputs_div)])
        DOM.add(view.element)

        @when(view.events.change)
        def on_change(sender, tab, index):
            ...
    """

    def __init__(self, tabs=None, active=0, fill=False, **kwargs):
        """
        Args:
            fill: Stretch to the parent's height with the tab bar pinned and
                  the panel area taking the remaining space. Panels are then
                  responsible for their own scrolling.
        """
        self._fill = fill
        super().__init__(macro_type="tabview", **kwargs)

        self._tabs = []
        self._active_index = -1

        self._create_event('change')
        self._init_macro()

        for tab in (tabs or []):
            self.add_tab(tab)
        if self._tabs:
            self.set_active(active)

    def _create_elements(self):
        container_style = {"width": "100%"}
        content_style = {
            "border": "1px solid #dee2e6", "border-top": "none",
            "border-radius": "0 0 6px 6px", "padding": "16px",
            "background-color": "#fff",
        }
        if self._fill:
            container_style.update({
                "display": "flex", "flex-direction": "column",
                "height": "100%", "min-height": "0",
            })
            # min-height:0 lets this shrink below its content so the panel,
            # not the page, is what scrolls.
            content_style.update({
                "flex": "1", "min-height": "0", "overflow": "hidden",
                "border-radius": "0", "padding": "0",
            })

        container = self._register_element('container', self._create_container(container_style))
        self._register_element('bar', Div(style={
            "display": "flex", "flex-wrap": "wrap", "gap": "2px",
            "border-bottom": "2px solid #dee2e6", "margin-bottom": "0",
            "flex-shrink": "0",
        }))
        self._register_element('content', Div(style=content_style))
        container.add(self._get_element('bar'), self._get_element('content'))
        return container

    def _tab_button(self, tab, index):
        button = Button(tab.title, style={
            "padding": "9px 18px", "border": "none", "cursor": "pointer",
            "font-size": "14px", "background": "transparent", "color": "#495057",
            "border-bottom": "3px solid transparent", "margin-bottom": "-2px",
        })
        button.on_click(lambda e, i=index: self.set_active(i))
        return button

    def add_tab(self, tab):
        index = len(self._tabs)
        tab.button = self._tab_button(tab, index)
        self._get_element('bar').add(tab.button)

        wrapper_style = {"display": "none"}
        if self._fill:
            wrapper_style.update({"height": "100%", "min-height": "0"})
        wrapper = Div(tab.content, style=wrapper_style)
        tab.content = wrapper
        self._get_element('content').add(wrapper)

        self._tabs.append(tab)
        if len(self._tabs) == 1:
            self.set_active(0)
        return self

    def set_active(self, index):
        if not (0 <= index < len(self._tabs)) or index == self._active_index:
            return self
        self._active_index = index

        for i, tab in enumerate(self._tabs):
            active = i == index
            tab.content.style.display = "block" if active else "none"
            if tab.button:
                tab.button.style.color = "#0066cc" if active else "#495057"
                tab.button.style.font_weight = "600" if active else "400"
                tab.button.style.border_bottom = (
                    "3px solid #0066cc" if active else "3px solid transparent"
                )

        self._fire_event('change', self._tabs[index], index)
        return self

    def clear_tabs(self):
        self._get_element('bar')._dom_element.innerHTML = ""
        self._get_element('content')._dom_element.innerHTML = ""
        self._tabs = []
        self._active_index = -1
        return self

    @property
    def tabs(self):
        return list(self._tabs)

    @property
    def active_index(self):
        return self._active_index
