"""
The dialog that adds a node to the workflow, or edits one already there.

Nothing in it is specific to a node: it is built from the node's ports and
option `Field`s. The inputs panel wires each port to a source; the data and
option panels follow, and their choices — which columns, which samples — are
drawn from whatever the first input will deliver, so a step after a Grain PCA
offers PC1 and PC2 and a Mixture offers the samples its Distribution kept.
"""
from antioch.dom import DOM
from antioch.elements import Div, Input, Option, P, Select
from antioch.event import when
from antioch.macros import Modal

from ui_lib import CheckboxGroup, Wizard, WizardPanel, labeled

from .nodes import (
    CHECKBOX, DATA_PAGE, DIMENSION, DIMENSIONS, NUMBER, OPTIONS_PAGE, SAMPLE,
    SAMPLES, SELECT, TEXT, Context, context_of, likely_column,
)
from .combine import unique_names
from .ports import PortEditor

MODAL_STYLE = {"max-width": "760px", "width": "92vw", "min-width": "0"}
NOTE_STYLE = {"color": "#555", "font-size": "13px", "margin": "0 0 14px 0"}


class NodeDialog:
    """
    Usage:
        dialog = NodeDialog(node)
        dialog.open(context)                 # add a step
        dialog.open(context, step=step)      # edit one

    `context` supplies what the dialog cannot know:
        choices(node, port, before)  -> [(source id, label)] the port could read
        batch(source id)             -> the batch it would receive
        type_of(source id)           -> its data type
        submit(node key, opts, inputs, step id or None)
    """

    def __init__(self, node):
        self.node = node
        self._context = None
        self._data = Context()
        self._step = None
        self._widgets = {}      # field key -> (row, control, field)
        self._ports = {}        # port name -> PortEditor
        self._port_rows = {}
        self._port_labeled = {}
        self._title = Input("text", placeholder=f"e.g. {node.label} of …",
                            style={"width": "260px"})

        panels = self._build_panels()
        self.wizard = Wizard(submit_text="Add to workflow", panels=panels)
        self.wizard.element.style.update({
            "margin-top": "0", "border": "none", "border-radius": "0"})

        @when(self.wizard.events.submit)
        def on_submit(sender, *args):
            self._submit()

        self.modal = Modal(title=node.label, modal_style=MODAL_STYLE)
        self.modal.set_content(self.wizard.element)
        DOM.add(self.modal.element)

    # ------------------------------------------------------------ construction

    def _build_panels(self):
        node = self.node
        inputs = Div()
        if node.description:
            inputs.add(P(node.description, style=dict(NOTE_STYLE)))
        for port in node.spec.ports:
            holder = Div()
            self._port_rows[port.name] = holder
            row = labeled(port.label or port.name, holder, port.hint or None)
            self._port_labeled[port.name] = row
            inputs.add(row)
        inputs.add(labeled("Title", self._title,
                           "Optional; names the step and its card"))

        pages = {DATA_PAGE: [], OPTIONS_PAGE: []}
        for f in node.fields:
            control = self._control(f)
            row = labeled(f.label, control.element if hasattr(control, "element")
                          else control, f.hint or None)
            self._widgets[f.key] = (row, control, f)
            pages[f.page].append(row)

        panels = [WizardPanel("Inputs", inputs,
                              f"Choose what the {node.label.lower()} reads.")]
        if pages[DATA_PAGE]:
            panels.append(WizardPanel(
                "Data", Div(*pages[DATA_PAGE]),
                "Choose which of the input's samples and dimensions to use."))
        if pages[OPTIONS_PAGE]:
            panels.append(WizardPanel("Options", Div(*pages[OPTIONS_PAGE]),
                                      "Configure how it runs."))
        return panels

    def _control(self, f):
        if f.kind == SELECT:
            select = Select()
            select.on('change', lambda e: self._refresh_visibility())
            return select
        if f.kind in (DIMENSION, SAMPLE):
            return Select()
        if f.kind == CHECKBOX:
            box = Input("checkbox")
            box._dom_element.checked = bool(f.default)
            box.on('change', lambda e: self._refresh_visibility())
            return box
        if f.kind == NUMBER:
            return Input("number", placeholder="auto", style={"width": "90px"},
                         **({"step": "any"} if f.signed else {}))
        if f.kind == TEXT:
            return Input("text", style={"width": "320px"})
        if f.kind == DIMENSIONS:
            return CheckboxGroup(all_checked=False,
                                 empty_text="No dimensions in this input",
                                 on_change=lambda values: self._refresh_visibility())
        if f.kind == SAMPLES:
            return CheckboxGroup(all_checked=not f.unchecked,
                                 empty_text="No samples in this input",
                                 on_change=lambda values: self._refresh_visibility())
        raise ValueError(f"Unknown field kind '{f.kind}'")

    # --------------------------------------------------------------- opening

    def open(self, context, step=None, preset=None):
        """
        Show the dialog to add a step, or to edit `step`.

        `preset` is a source id to start the first port that can read it on,
        instead of the usual default.
        """
        self._context = context
        self._step = step
        self.wizard.set_status("")
        self.wizard.set_submit_text(
            "Save changes" if step else getattr(context, "submit_label", "Add to workflow"))
        # Run on the spreadsheet alone, there is nothing to choose to read.
        hide = getattr(context, "single_input", False)
        for row in self._port_labeled.values():
            row.style.display = "none" if hide else "block"
        self._title.value = (step.options.get("title", "") if step else "")

        before = step.id if step else None
        preset_kind = context.type_of(preset) if preset else None
        for port in self.node.spec.ports:
            choices = context.choices(self.node, port, before)
            chosen = step.inputs.get(port.name) if step else None
            if (preset and not step and port.accepts(preset_kind)
                    and preset in [source for source, _ in choices]):
                chosen, preset = [preset], None       # used: later ports take their defaults
            editor = PortEditor(
                port, choices, chosen, on_change=lambda ids: self._rewired(),
                empty_text=self._nothing_to_read(port))
            self._ports[port.name] = editor
            holder = self._port_rows[port.name]
            holder._dom_element.innerHTML = ""
            holder.add(editor.element)

        # A new block starts clean — it is a fresh piece, not the last one
        # reused — while editing shows the step's own values.
        self._reset()
        self._refresh_data()
        if step:
            self._write(step.options)
        self._refresh_visibility()
        self.modal.open()
        return self

    def _reset(self):
        """Put every control back to its starting state."""
        for _, control, f in self._widgets.values():
            if f.kind == SAMPLES:
                control.set_all(not f.unchecked)
            elif f.kind == DIMENSIONS:
                control.set_all(False)
            elif f.kind == CHECKBOX:
                control._dom_element.checked = bool(f.default)
            elif f.kind in (NUMBER, TEXT):
                # A field's default is shown, so the dialog says what will be used (and a block
                # with typed-in numbers, like the Thiem drawdown, opens ready to run)
                control.value = _shown(f.default)
            else:
                control.clear()      # refilled, on its default, with the data

    @staticmethod
    def _nothing_to_read(port):
        from workflow_lib import TYPE_LABELS
        kinds = " or ".join(TYPE_LABELS[t].lower() for t in port.types)
        return f"Nothing to connect: add a step that produces {kinds} first."

    # ------------------------------------------------------------- the data

    def _rewired(self):
        self._refresh_data()
        self._refresh_visibility()

    def _first_port_with_sources(self):
        for port in self.node.spec.ports:
            editor = self._ports.get(port.name)
            if editor and editor.sources():
                return port, editor.sources()
        return None, []

    def _describe_inputs(self):
        """
        What the first input delivers. A port wired to several sources offers the
        samples of all of them, named as `combine` will name them.
        """
        _, sources = self._first_port_with_sources()
        if not sources:
            return Context()
        parts = [context_of(self._context.type_of(s), self._context.batch(s))
                 for s in sources]
        merged = parts[0]
        if len(parts) > 1:
            merged.samples = [name for names in unique_names([p.samples for p in parts])
                              for name in names]
        return merged

    def _refresh_data(self):
        """Offer the columns and samples of whatever the first input delivers."""
        self.wizard.set_status("")
        try:
            self._data = self._describe_inputs()
        except Exception as error:
            self._data = Context()
            self.wizard.set_status(f"Could not prepare that input: {error}")

        data = self._data
        for _, control, f in self._widgets.values():
            if f.kind == SAMPLES:
                control.set_options(list(data.samples))
            elif f.kind in (DIMENSIONS, DIMENSION):
                usable = [d for d in data.dimensions
                          if not f.numeric_only or d in data.numeric
                          or (f.dates and d in data.dates)]
                if f.kind == DIMENSIONS:
                    control.set_options(usable)
                else:
                    _fill(control, {d: d for d in usable}, nth=f.nth,
                          default=likely_column(usable, f.like) if f.like else None,
                          empty="No dimensions in this input")
            elif f.kind == SAMPLE:
                _fill(control, {s: s for s in data.samples},
                      empty="No samples in this input")
            elif f.kind == SELECT:
                self._fill_select(control, f, data)

    def _fill_select(self, control, f, data):
        """Fill a SELECT from its field; a `dynamic` one sees the current options."""
        if callable(f.choices):
            choices = f.choices(data, self.read()) if f.dynamic else f.choices(data)
        else:
            choices = f.choices
        _fill(control, {str(k): v for k, v in choices.items()},
              default=None if f.default is None else str(f.default))

    # ------------------------------------------------------------ the values

    def read(self):
        """The options as the dialog stands, keyed like a step's saved options."""
        opts = {"title": self._title.value.strip()}
        for key, (_, control, f) in self._widgets.items():
            if f.kind in (SAMPLES, DIMENSIONS):
                opts[key] = control.values()
            elif f.kind == CHECKBOX:
                opts[key] = bool(control._dom_element.checked)
            elif f.kind == NUMBER:
                opts[key] = _number(control.value) if f.signed else _positive(control.value)
            elif f.kind == TEXT:
                opts[key] = control.value.strip() or None
            else:
                value = control.value or None
                opts[key] = f.cast(value) if (f.cast and value is not None) else value
        return opts

    def _write(self, opts):
        """Put saved options back into the controls, for editing."""
        for key, (_, control, f) in self._widgets.items():
            if key not in opts:
                continue
            value = opts[key]
            if f.kind in (SAMPLES, DIMENSIONS):
                _check_only(control, value)
            elif f.kind == CHECKBOX:
                control._dom_element.checked = bool(value)
            elif f.kind in (NUMBER, TEXT):
                control.value = "" if value is None else str(value)
            elif value is not None:
                control.value = str(value)

    def _refresh_visibility(self):
        """Show a field only while its `when` holds for the options chosen."""
        opts = self.read()
        for _, (row, control, f) in self._widgets.items():
            row.style.display = "block" if (not f.when or f.when(opts)) else "none"
            if f.dynamic and f.kind == SELECT:
                self._fill_select(control, f, self._data)

    # ---------------------------------------------------------------- submit

    def _submit(self):
        node = self.node
        inputs = {}
        for port in node.spec.ports:
            ids = self._ports[port.name].sources()
            if not ids and not port.optional:
                self.wizard.set_status(
                    f"'{port.label or port.name}' has nothing connected.")
                return
            inputs[port.name] = ids
        opts = self.read()
        problem = node.validate(opts, self._data) if node.validate else None
        if problem:
            self.wizard.set_status(problem)
            return
        step = self._step
        self.wizard.set_status("")
        self.modal.close()
        self._context.submit(node.key, opts, inputs, step.id if step else None)


def _shown(default):
    """A field's default as the text of its box: "" for none, 60 not 60.0."""
    if default is None:
        return ""
    if isinstance(default, float) and default == int(default) and abs(default) < 1e15:
        return str(int(default))
    return str(default)


def _fill(select, choices, nth=0, default=None, empty="Nothing to choose"):
    """
    Replace a Select's options with `{value: label}`, keeping the current choice
    if it is still on offer; otherwise `default`, else the `nth` option.
    """
    previous = select.value
    select.clear()
    if not choices:
        select.add(Option(empty, value=""))
        return
    for value, label in choices.items():
        select.add(Option(str(label), value=value))
    keys = list(choices)
    if previous in keys:
        select.value = previous
    elif default is not None and default in keys:
        select.value = default
    else:
        select.value = keys[min(nth, len(keys) - 1)]


def _check_only(group, values):
    """Check exactly `values` in a CheckboxGroup."""
    wanted = set(values or [])
    group.set_all(False)
    for value, box in group._boxes.items():
        box._dom_element.checked = value in wanted
    group._changed()


def _number(value):
    """A float from a number input, or None when blank or invalid."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive(value):
    """A positive float from a number input, or None when blank or invalid."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
