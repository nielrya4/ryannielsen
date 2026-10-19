"""Stepped options panel that generates output only when asked."""
import js

from antioch.elements import Button, Div, H3, Span
from antioch.macros.base import Macro

_CSS_ID = "ui-lib-wizard-css"

# Inline styles can't express media queries, and a 160px sidebar leaves too
# little room for the form on a phone. Below 640px the nav becomes a
# horizontal strip above the panel instead, as dzToolBox's dialogs do.
_CSS = """
@media (max-width: 640px) {
  .wizard-body { flex-direction: column !important; }
  .wizard-sidebar {
    width: 100% !important;
    display: flex;
    overflow-x: auto;
    border-right: none !important;
    border-bottom: 1px solid #e9ecef;
  }
  .wizard-sidebar button {
    width: auto !important;
    white-space: nowrap;
    border-left: none !important;
    border-bottom: 3px solid transparent;
  }
}
"""


def _ensure_css():
    # Not `is None`: Pyodide represents JS null as a `jsnull` sentinel, so
    # `is None` never matched and this re-injected the style on every call.
    if not js.document.getElementById(_CSS_ID):
        style = js.document.createElement("style")
        style.id = _CSS_ID
        style.textContent = _CSS
        js.document.head.appendChild(style)


class WizardPanel:
    def __init__(self, title, content, description=None):
        self.title = title
        self.content = content
        self.description = description
        self.nav_button = None


class Wizard(Macro):
    """
    Sidebar-stepped form. Panels stay mounted and are shown/hidden, so field
    values survive switching between steps.

    Fires `submit` when the action button is pressed; the handler is
    responsible for reading the panels' fields and doing the work.

        wizard = Wizard(panels=[WizardPanel("Options", options_div)],
                        submit_text="Create graphs")

        @when(wizard.events.submit)
        def on_submit(sender):
            ...
    """

    def __init__(self, panels=None, title=None, submit_text="Create", **kwargs):
        super().__init__(macro_type="wizard", **kwargs)

        self._panels = []
        self._active_index = 0
        self._set_state(title=title, submit_text=submit_text)

        self._create_event('submit')
        self._create_event('panel_change')

        self._init_macro()

        for panel in (panels or []):
            self.add_panel(panel)
        self._show_panel(0)

    def _create_elements(self):
        container = self._register_element('container', self._create_container({
            "border": "1px solid #ddd", "border-radius": "8px",
            "background-color": "#fff", "overflow": "hidden",
            "margin-top": "20px",
        }))

        title = self._get_state('title')
        if title:
            container.add(Div(title, style={
                "padding": "12px 16px", "font-weight": "600",
                "background-color": "#2c3e50", "color": "#fff",
            }))

        _ensure_css()

        sidebar = self._register_element('sidebar', Div(style={
            "width": "160px", "flex-shrink": "0",
            "border-right": "1px solid #e9ecef", "background-color": "#f8f9fa",
            "padding": "8px 0",
        }))
        sidebar.set_attribute("class", "wizard-sidebar")
        content = self._register_element('content', Div(style={
            "flex": "1", "padding": "16px", "min-width": "0",
        }))

        body = Div(sidebar, content, style={
            "display": "flex", "flex-wrap": "wrap", "align-items": "stretch",
        })
        body.set_attribute("class", "wizard-body")

        submit = self._register_element('submit', Button(self._get_state('submit_text'), style={
            "background-color": "#0066cc", "color": "#fff", "border": "none",
            "padding": "8px 18px", "border-radius": "4px", "cursor": "pointer",
            "font-size": "14px",
        }))
        # Element.on() makes its own proxy, so hand it the plain callable.
        submit.on_click(lambda e: self._fire_event('submit'))

        status = self._register_element('status', Span("", style={
            "margin-left": "12px", "font-size": "13px", "color": "#b00020",
        }))

        footer = Div(submit, status, style={
            "padding": "12px 16px", "border-top": "1px solid #e9ecef",
            "background-color": "#f8f9fa", "display": "flex", "align-items": "center",
        })

        container.add(body, footer)
        return container

    def _nav_button(self, panel, index):
        button = Button(panel.title, style={
            "display": "block", "width": "100%", "text-align": "left",
            "padding": "10px 16px", "border": "none", "background": "transparent",
            "cursor": "pointer", "font-size": "14px", "color": "#495057",
            "border-left": "3px solid transparent",
        })
        button.on_click(lambda e, i=index: self._show_panel(i))
        return button

    def _show_panel(self, index):
        if not (0 <= index < len(self._panels)):
            return self
        self._active_index = index

        for i, panel in enumerate(self._panels):
            active = i == index
            panel.content.style.display = "block" if active else "none"
            if panel.nav_button:
                panel.nav_button.style.background_color = "#fff" if active else "transparent"
                panel.nav_button.style.color = "#212529" if active else "#495057"
                panel.nav_button.style.border_left = (
                    "3px solid #0066cc" if active else "3px solid transparent"
                )
                panel.nav_button.style.font_weight = "600" if active else "400"

        self._fire_event('panel_change', self._panels[index])
        return self

    def add_panel(self, panel):
        index = len(self._panels)
        panel.nav_button = self._nav_button(panel, index)
        self._get_element('sidebar').add(panel.nav_button)

        wrapper = Div(style={"display": "none"})
        if panel.description:
            wrapper.add(Div(panel.description, style={
                "color": "#6c757d", "font-size": "13px", "margin-bottom": "14px",
            }))
        wrapper.add(panel.content)

        # _show_panel toggles this wrapper, so keep it as the panel's element
        panel.content = wrapper
        self._get_element('content').add(wrapper)

        self._panels.append(panel)
        return self

    def set_status(self, message, is_error=True):
        status = self._get_element('status')
        status.set_text(message)
        status.style.color = "#b00020" if is_error else "#146c2e"
        return self

    def set_busy(self, busy, busy_text="Working…"):
        submit = self._get_element('submit')
        submit._dom_element.disabled = bool(busy)
        submit.set_text(busy_text if busy else self._get_state('submit_text'))
        return self

    @property
    def panels(self):
        return list(self._panels)
