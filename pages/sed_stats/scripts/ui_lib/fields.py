"""Form field groups used to build wizard panels."""
from antioch.elements import Div, Input, Label, Span


class CheckboxGroup:
    """
    A scrollable list of checkboxes with select-all / select-none shortcuts.

    Options can be replaced at runtime; previously checked values stay checked
    if they still exist, so refreshing the spreadsheet doesn't reset choices.
    """

    def __init__(self, options=None, all_checked=True, height="150px", empty_text="Nothing to choose"):
        self._all_checked = all_checked
        self._empty_text = empty_text
        self._boxes = {}

        self._list = Div(style={
            "max-height": height, "overflow-y": "auto",
            "border": "1px solid #ddd", "border-radius": "4px",
            "padding": "6px", "background-color": "#fff",
        })

        self._select_all = Span("select all", style={
            "cursor": "pointer", "color": "#0066cc", "font-size": "12px",
            "text-decoration": "underline",
        })
        self._select_none = Span("select none", style={
            "cursor": "pointer", "color": "#0066cc", "font-size": "12px",
            "margin-left": "12px", "text-decoration": "underline",
        })
        self._select_all.on_click(lambda e: self.set_all(True))
        self._select_none.on_click(lambda e: self.set_all(False))

        self.element = Div(
            Div(self._select_all, self._select_none, style={"margin-bottom": "4px"}),
            self._list,
        )

        self.set_options(options or [])

    def set_options(self, options):
        previous = {value: box._dom_element.checked for value, box in self._boxes.items()}
        self._boxes = {}
        self._list._dom_element.innerHTML = ""

        if not options:
            self._list.add(Span(self._empty_text, style={"color": "#888", "font-size": "13px"}))
            return

        for value in options:
            box = Input("checkbox", style={"margin-right": "8px"})
            box._dom_element.checked = previous.get(value, self._all_checked)
            self._boxes[value] = box
            self._list.add(Div(
                Label(box, Span(str(value)), style={
                    "display": "flex", "align-items": "center",
                    "font-size": "13px", "padding": "2px 0", "cursor": "pointer",
                }),
            ))

    def set_all(self, checked):
        for box in self._boxes.values():
            box._dom_element.checked = checked

    def values(self):
        return [value for value, box in self._boxes.items() if box._dom_element.checked]

    @property
    def options(self):
        return list(self._boxes.keys())


def labeled(label_text, control, hint=None):
    """A wizard form row: bold label, control, optional hint line."""
    children = [
        Label(label_text, style={
            "display": "block", "font-weight": "500",
            "margin-bottom": "4px", "font-size": "14px",
        }),
        control,
    ]
    if hint:
        children.append(Div(hint, style={
            "color": "#6c757d", "font-size": "12px", "margin-top": "3px",
        }))
    return Div(*children, style={"margin-bottom": "16px"})
