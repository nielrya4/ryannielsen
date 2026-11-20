"""
Tools: pre-wired chains of blocks, offered with a short dialog.

A *block* does one thing; a *tool* is a recipe that wires several into a chain
and exposes only the options worth asking for — which samples, which metric —
the way a saved model becomes a tool in a geoprocessing toolbox. Tools are grouped
into toolboxes.

A tool is plain data, so the built-in ones and the ones a user saves are the same
kind of thing and can be stored in a project file:

    steps    the blocks, each with its fixed options, which of its options come
             from the tool's parameters (`expose`), and where its inputs read from
             ("data" is the table the tool is run on, or another step's id; a step
             that has several outputs is read as "id.output")
    params   what the dialog asks. A parameter takes its definition (kind, choices,
             default, hint) from the block option it is `source`d from, or spells
             its own out, and may be shown only `when` other parameters say so
    when     on a step or a parameter: conditions on parameter values. A step
             whose condition fails is left out, and so is any wire to it — one
             tool can hold a univariate and a bivariate chain and run whichever
             the "mode" parameter asks for
    sheet    optionally, a step whose table result is written back to the
             spreadsheet

Everything here is independent of the browser and of what the blocks do.
"""
from dataclasses import dataclass, field

# How a step's wiring refers to the table a tool is run on.
TABLE_INPUT = "data"


class ToolError(ValueError):
    """A tool definition that is malformed, or cannot be used as it stands."""


@dataclass
class ParamSpec:
    """
    One thing the tool's dialog asks.

    Args:
        key: the parameter's name; for parameters that came from an option, also
            the name the saved outputs use for it
        source: "step.option" — take the field's kind, choices and default from
            that block option
        field: or a field spelled out here: {"kind", "choices", "default", ...}
        label, hint: override the source's
        when: {param: value(s)} — show only while these hold (replaces the
            source option's own condition)
        page: "Data" or "Options", where the dialog puts it
        default: the value when none is given (a saved output that predates it)
        dynamic: the choices depend on the other parameters (a metric list that
            differs by analysis); see the dialog
    """
    key: str
    source: str = None
    field: dict = None
    label: str = ""
    hint: str = ""
    when: dict = None
    page: str = None
    default: object = None

    def to_dict(self):
        return {k: v for k, v in {
            "key": self.key, "source": self.source, "field": self.field,
            "label": self.label, "hint": self.hint, "when": self.when,
            "page": self.page, "default": self.default}.items()
            if v not in (None, "")}


@dataclass
class ToolStep:
    """
    One block in the chain.

    Args:
        id: local to the tool
        node: the block's key
        options: fixed options
        expose: {option: parameter} — options taken from the tool's parameters;
            a list means each option takes the parameter of the same name
        inputs: {port: [step id or TABLE_INPUT, ...]}
        when: only when these parameter conditions hold
    """
    id: str
    node: str
    options: dict = field(default_factory=dict)
    expose: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)
    when: dict = None

    def to_dict(self):
        return {k: v for k, v in {
            "id": self.id, "node": self.node, "options": self.options,
            "expose": self.expose, "inputs": self.inputs, "when": self.when}.items()
            if v not in (None, {})}


@dataclass
class ToolDef:
    key: str
    label: str
    toolbox: str
    description: str = ""
    params: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    sheet: dict = None          # {"step": id, "when": {...}} — write its table back
    needs_table: bool = True    # False for a tool that takes no table: its numbers are typed in

    def to_dict(self):
        document = {"key": self.key, "label": self.label, "toolbox": self.toolbox,
                    "description": self.description,
                    "params": [p.to_dict() for p in self.params],
                    "steps": [s.to_dict() for s in self.steps]}
        if self.sheet:
            document["sheet"] = self.sheet
        if not self.needs_table:
            document["needs_table"] = False
        return document

    def step(self, step_id):
        for step in self.steps:
            if step.id == step_id:
                return step
        raise ToolError(f"No step '{step_id}' in tool '{self.key}'.")

    def param(self, key):
        for param in self.params:
            if param.key == key:
                return param
        raise ToolError(f"No parameter '{key}' in tool '{self.key}'.")


# ------------------------------------------------------------------ conditions

def condition_holds(condition, values):
    """
    Whether `{param: expected}` is true of `values`. `expected` may be a value,
    a list of acceptable values, or True / False for a checkbox.
    """
    for key, expected in (condition or {}).items():
        actual = values.get(key)
        if isinstance(expected, bool):
            if bool(actual) != expected:
                return False
        elif isinstance(expected, (list, tuple)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def active_steps(tool, values):
    """The steps that run for these parameter values, in order."""
    return [step for step in tool.steps if condition_holds(step.when, values)]


def resolved_values(tool, values):
    """`values` with each parameter's default filled in where it has none."""
    filled = dict(values)
    for param in tool.params:
        if param.key not in filled and param.default is not None:
            filled[param.key] = param.default
    return filled


@dataclass
class PlannedStep:
    """A step as it will run: options resolved, wiring pruned to what is active."""
    id: str
    node: str
    options: dict
    inputs: dict


def instantiate(tool, values):
    """
    The chain a tool runs for these parameter values.

    Fixed options and exposed parameters are merged into each step's options, and
    wires to steps that are not active are dropped, so what comes back is a
    chain that can be run as it stands.

    Returns:
        [PlannedStep, ...] in order; inputs refer to other planned steps by id, or
        to TABLE_INPUT
    """
    values = resolved_values(tool, values)
    steps = active_steps(tool, values)
    present = {step.id for step in steps}
    planned = []
    for step in steps:
        options = dict(step.options)
        expose = step.expose
        pairs = expose.items() if isinstance(expose, dict) else ((k, k) for k in expose)
        for option, param in pairs:
            if param in values:
                options[option] = values[param]
        inputs = {port: [s for s in sources
                         if s == TABLE_INPUT or s.partition(".")[0] in present]
                  for port, sources in step.inputs.items()}
        planned.append(PlannedStep(step.id, step.node, options, inputs))
    return planned


def sheet_step(tool, values):
    """The id of the step whose table goes back to the spreadsheet, or None."""
    spec = tool.sheet
    if spec and condition_holds(spec.get("when"), resolved_values(tool, values)):
        return spec["step"]
    return None


# ------------------------------------------------------------------ persistence

def tool_from_dict(document):
    """
    Rebuild a tool from `ToolDef.to_dict` output.

    Raises:
        ToolError: for anything that is not a well-formed tool
    """
    if not isinstance(document, dict):
        raise ToolError("A tool is a dictionary.")
    for key in ("key", "label", "toolbox"):
        if not isinstance(document.get(key), str) or not document[key]:
            raise ToolError(f"A tool needs a '{key}'.")
    params, steps = [], []
    for raw in document.get("params", []):
        if not isinstance(raw, dict) or not isinstance(raw.get("key"), str):
            raise ToolError("A parameter needs a key.")
        known = {k: raw[k] for k in ("key", "source", "field", "label", "hint",
                                      "when", "page", "default") if k in raw}
        params.append(ParamSpec(**known))
    for raw in document.get("steps", []):
        if (not isinstance(raw, dict) or not isinstance(raw.get("id"), str)
                or not isinstance(raw.get("node"), str)):
            raise ToolError("A step needs an id and a node.")
        steps.append(ToolStep(
            raw["id"], raw["node"], dict(raw.get("options") or {}),
            raw.get("expose") or {}, {p: list(s) for p, s in (raw.get("inputs") or {}).items()},
            raw.get("when")))
    tool = ToolDef(document["key"], document["label"], document["toolbox"],
                   str(document.get("description") or ""), params, steps,
                   document.get("sheet"), bool(document.get("needs_table", True)))
    check_tool(tool)
    return tool


def check_tool(tool):
    """
    Raise ToolError unless the tool hangs together: unique ids, wires to steps
    that exist and come earlier, parameters that exist.
    """
    ids = [s.id for s in tool.steps]
    if len(set(ids)) != len(ids):
        raise ToolError(f"Tool '{tool.key}' has two steps with the same id.")
    if len({p.key for p in tool.params}) != len(tool.params):
        raise ToolError(f"Tool '{tool.key}' has two parameters with the same key.")
    keys = {p.key for p in tool.params}
    earlier = {TABLE_INPUT}
    for step in tool.steps:
        for port, sources in step.inputs.items():
            for source in sources:
                if source.partition(".")[0] not in earlier:
                    raise ToolError(
                        f"Step '{step.id}' of '{tool.key}' reads '{source}', which "
                        "is not the table or an earlier step.")
        expose = step.expose
        wanted = expose.values() if isinstance(expose, dict) else expose
        for param in wanted:
            if param not in keys:
                raise ToolError(f"Step '{step.id}' of '{tool.key}' exposes "
                                f"'{param}', which is not a parameter.")
        for condition in (step.when,):
            for key in (condition or {}):
                if key not in keys:
                    raise ToolError(f"Step '{step.id}' of '{tool.key}' depends on "
                                    f"'{key}', which is not a parameter.")
        earlier.add(step.id)
    if tool.sheet and tool.sheet.get("step") not in ids:
        raise ToolError(f"Tool '{tool.key}' writes back from a step that does not exist.")
    for param in tool.params:
        for key in (param.when or {}):
            if key not in keys:
                raise ToolError(f"Parameter '{param.key}' depends on '{key}', "
                                "which is not a parameter.")


__all__ = ["TABLE_INPUT", "ParamSpec", "PlannedStep", "ToolDef", "ToolError",
           "ToolStep", "active_steps", "check_tool", "condition_holds",
           "instantiate", "resolved_values", "sheet_step", "tool_from_dict"]
