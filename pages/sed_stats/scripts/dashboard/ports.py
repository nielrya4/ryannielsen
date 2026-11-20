"""
Choosing what a node's input port reads.

A port reads one source, or — for a graph that can draw several series — as
many as the user adds with "+ Add input". The same editor sits in the dialog
that adds a step and on the step's row afterwards, so wiring is changed the
way it was made.
"""
from antioch.elements import Button, Div, Option, Select, Span
from antioch.event import when

ROW_STYLE = {"display": "flex", "align-items": "center", "gap": "6px",
             "margin-bottom": "4px"}
ADD_STYLE = {
    "background-color": "#eef1f4", "color": "#333", "border": "1px solid #cfd6dd",
    "padding": "2px 9px", "cursor": "pointer", "font-size": "12px",
    "border-radius": "3px",
}
MUTED = {"color": "#6c757d", "font-size": "12px"}


class PortEditor:
    """
    A list of source pickers for one port.

    Args:
        port: the `workflow_lib.Port` being wired
        choices: `[(source id, label), ...]` the port could read
        chosen: the source ids it reads now
        on_change: called with the new list of ids whenever it changes
        empty_text: what to say when there is nothing to connect

    A port that takes one source shows one picker. A `multiple` port shows
    one per source, each removable, with "+ Add input" below; an `optional`
    one may have none.
    """

    def __init__(self, port, choices, chosen=None, on_change=None,
                 empty_text="Nothing to connect yet."):
        self.port = port
        self._choices = list(choices)
        self._chosen = list(chosen) if chosen is not None else self._default()
        self._on_change = on_change
        self._empty_text = empty_text
        self.element = Div()
        self._build()

    # ------------------------------------------------------------------ state

    def sources(self):
        """The ids this port reads, in the order they were added."""
        return list(self._chosen)

    def set_choices(self, choices):
        """Offer different sources, keeping the ones that are still on offer."""
        self._choices = list(choices)
        offered = {value for value, _ in self._choices}
        kept = [value for value in self._chosen if value in offered]
        self._chosen = kept or (self._default() if not self.port.optional else [])
        self._build()

    def _default(self):
        """
        A single source to start from: the latest step that fits, so a new step
        reads what was just made — except a table, where the spreadsheet is the
        safer start.
        """
        if not self._choices or self.port.optional:
            return []
        wants_table = "table" in self.port.types
        return [self._choices[0 if wants_table else -1][0]]

    def _notify(self):
        if self._on_change:
            self._on_change(self.sources())

    # ---------------------------------------------------------------- display

    def _build(self):
        box = self.element
        box._dom_element.innerHTML = ""
        if not self._choices:
            box.add(Span(self._empty_text, style=dict(MUTED)))
            return
        for index, value in enumerate(self._chosen):
            box.add(self._row(index, value))
        if self.port.multiple:
            if self._unused() or not self._chosen:
                add = Button("+ Add input", style=dict(ADD_STYLE))

                @when(add.events.click)
                def on_add(sender, *args):
                    self._add()
                box.add(add)
            else:
                # Nothing left to add; say so rather than leave the user
                # looking for a button that is not there.
                box.add(Span("That is every step that fits. Add more steps to "
                             "draw them together.", style=dict(MUTED)))

    def _row(self, index, value):
        select = Select()
        for source_id, label in self._choices:
            select.add(Option(label, value=source_id))
        select.value = value
        select.on('change', lambda e, i=index, s=select: self._pick(i, s.value))
        row = Div(select, style=dict(ROW_STYLE))
        if self.port.multiple and (len(self._chosen) > 1 or self.port.optional):
            remove = Button("×", style=dict(ADD_STYLE))

            @when(remove.events.click)
            def on_remove(sender, *args):
                self._remove(index)
            row.add(remove)
        return row

    def _unused(self):
        return [value for value, _ in self._choices if value not in self._chosen]

    def _pick(self, index, value):
        self._chosen[index] = value
        self._notify()

    def _add(self):
        spare = self._unused()
        self._chosen.append(spare[-1] if spare else self._choices[-1][0])
        self._build()
        self._notify()

    def _remove(self, index):
        del self._chosen[index]
        self._build()
        self._notify()
