"""
Toolboxes: tools grouped for the menus, and what a tool needs to be a dialog.

`ToolRegistry` holds every tool — the built-in ones and any the user has saved —
and lists them by toolbox. `ToolNode` dresses a tool as a block for the dialog:
the dialog is built from a node's ports and option fields, and a tool's fields are
its parameters, each taken from the option of the block it controls, so a tool's
dialog says exactly what that block's own dialog would.
"""
from dataclasses import replace

from workflow_lib import NodeSpec, Port, TABLE, ToolError
from workflow_lib.tools import condition_holds, instantiate, resolved_values

from .builtin_tools import BUILTIN_TOOLS, HIDDEN_TOOLS, MENU_ORDER, TOOLBOX_ORDER
from .nodes import (
    CHECKBOX, DIMENSION, DIMENSIONS, Field, NODES, NUMBER, OPTIONS_PAGE,
    SAMPLE, SAMPLES, SELECT, TEXT,
)

FIELD_KINDS = {"select": SELECT, "checkbox": CHECKBOX, "number": NUMBER, "text": TEXT,
               "dimensions": DIMENSIONS, "dimension": DIMENSION,
               "samples": SAMPLES, "sample": SAMPLE}


def _when(condition):
    return (lambda opts: condition_holds(condition, opts)) if condition else None


def build_field(tool, param):
    """The dialog Field for one parameter of `tool`."""
    if param.source:
        step_id, _, option = param.source.partition(".")
        node = NODES[tool.step(step_id).node]
        base = next((f for f in node.fields if f.key == option), None)
        if base is None:
            raise ToolError(f"Block '{node.key}' has no option '{option}' "
                            f"(parameter '{param.key}' of '{tool.key}').")
        # The block's own condition is written in terms of its own option
        # names, so it only carries over while the parameter keeps the name.
        keep_when = base.when if param.key == option else None
        return replace(
            base, key=param.key, label=param.label or base.label,
            hint=param.hint or base.hint, page=param.page or base.page,
            default=param.default if param.default is not None else base.default,
            # `when={}` says "always shown"; leaving it out keeps the block's own.
            when=_when(param.when) if param.when is not None else keep_when)
    spec = param.field or {}
    kind = FIELD_KINDS.get(spec.get("kind", "select"))
    if kind is None:
        raise ToolError(f"Parameter '{param.key}' has an unknown kind '{spec.get('kind')}'.")
    return Field(param.key, param.label or spec.get("label", param.key), kind,
                 hint=param.hint or spec.get("hint", ""), choices=spec.get("choices"),
                 default=spec.get("default", param.default),
                 numeric_only=spec.get("numeric_only", False),
                 signed=spec.get("signed", False),
                 unchecked=spec.get("unchecked", False),
                 page=param.page or spec.get("page", OPTIONS_PAGE),
                 when=_when(param.when))


class ToolNode:
    """A tool, shaped like a block so the same dialog can collect its parameters."""

    is_tool = True

    def __init__(self, tool):
        self.tool = tool
        self.key = tool.key
        self.label = tool.label
        self.description = tool.description
        self.fields = [build_field(tool, p) for p in tool.params]
        # A tool is run on a table; the dialog asks which when it is added to a workflow.
        self.spec = NodeSpec(tool.key, tool.label, tool.toolbox,
                             (Port("table", (TABLE,), "Table"),) if tool.needs_table else (), None)

    def validate(self, opts, context):
        """
        The first problem any block in the chain would raise for these choices,
        then the tool's own check.
        """
        for planned in instantiate(self.tool, opts):
            node = NODES[planned.node]
            if node.validate:
                try:
                    problem = node.validate(planned.options, context)
                except KeyError:
                    continue            # an option no parameter supplies yet
                if problem:
                    return problem
        check = TOOL_CHECKS.get(self.tool.key)
        return check(resolved_values(self.tool, opts)) if check else None


def _at_least(count, what):
    def check(values):
        chosen = len(values.get("samples") or [])
        if chosen < count:
            return f"{what} needs at least {count} samples; {chosen} selected."
        return None
    return check


def _sink_among_samples(values):
    samples = values.get("samples") or []
    if values.get("sink") not in samples:
        return f"The sink '{values.get('sink')}' is not among the selected samples."
    if len(samples) < 3:
        return "Select the sink plus at least two source samples."
    return None


# What a tool's blocks cannot check alone: how many samples it needs of the ones chosen.
TOOL_CHECKS = {
    "matrix": _at_least(2, "A comparison"),
    "mds": _at_least(3, "MDS"),
    "mixture": _sink_among_samples,
    "unmix_pc1": _sink_among_samples,
}


class ToolRegistry:
    """Every tool available, by key, and the toolboxes they are listed under."""

    def __init__(self, tools=()):
        self.tools = {}
        self._nodes = {}
        self._builtin = set()
        self.on_change = None       # called after tools are added or removed
        for tool in tools:
            self.add(tool)
        self._builtin = set(self.tools)

    def add(self, tool):
        build = ToolNode(tool)      # fails now, not at the first click, if it is unusable
        self.tools[tool.key] = tool
        self._nodes[tool.key] = build
        self._changed()
        return build

    def remove(self, key):
        """Remove one of the user's tools; the built-in ones stay."""
        if key in self._builtin:
            raise ToolError("The built-in tools cannot be removed.")
        self.tools.pop(key, None)
        self._nodes.pop(key, None)
        self._changed()

    def _changed(self):
        if self.on_change:
            self.on_change()

    def user_tools(self):
        """The tools the user made, as documents for the project file."""
        return [tool.to_dict() for key, tool in self.tools.items()
                if key not in self._builtin]

    def load_user_tools(self, documents):
        """
        Replace the user's tools with these (from a project file). One that cannot
        be used — a block it needs is gone — is skipped rather than failing the rest.

        Returns:
            the labels of those skipped
        """
        from workflow_lib import tool_from_dict
        callback, self.on_change = self.on_change, None
        for key in [k for k in self.tools if k not in self._builtin]:
            self.remove(key)
        skipped = []
        for document in documents or []:
            try:
                tool = tool_from_dict(document)
                if tool.key in self._builtin:
                    raise ToolError("A built-in tool has that key.")
                self.add(tool)
            except (ToolError, KeyError, TypeError, StopIteration):
                skipped.append(str(document.get("label", "?")) if isinstance(document, dict) else "?")
        self.on_change = callback
        self._changed()
        return skipped

    def is_builtin(self, key):
        return key in self._builtin

    def node(self, key):
        return self._nodes[key]

    def get(self, key):
        return self.tools.get(key)

    def toolboxes(self):
        """{toolbox: [tool keys]} in menu order: built-in boxes first, then the rest."""
        found = {}
        for tool in self.tools.values():
            if tool.key in HIDDEN_TOOLS:          # still there for saved work, not offered in the menus
                continue
            found.setdefault(tool.toolbox, []).append(tool.key)
        for keys in found.values():           # stable: tools not named in MENU_ORDER keep their order, after
            keys.sort(key=lambda k: MENU_ORDER.index(k) if k in MENU_ORDER else len(MENU_ORDER))
        ordered = {name: found.pop(name) for name in TOOLBOX_ORDER if name in found}
        ordered.update(dict(sorted(found.items())))
        return ordered


def builtin_registry():
    return ToolRegistry(BUILTIN_TOOLS)
