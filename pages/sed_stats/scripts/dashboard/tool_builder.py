"""
Turning steps into a tool: "Save as tool".

The steps the user has wired up become a recipe. Each step's options are kept as
they are now, except the ones the user chooses to *expose*, which become the
tool's parameters (with today's value as the default), so the tool asks for them
each time it is run. Everything else is fixed.

The spreadsheet, or any table the steps read from outside the chosen ones,
becomes the tool's single table input.
"""
import re
from dataclasses import dataclass

from workflow_lib import DATA, TABLE, ParamSpec, ToolDef, ToolError, ToolStep
from workflow_lib.tools import TABLE_INPUT, check_tool
from workflow_lib.workflow import source_ref, split_source, step_of

from .nodes import DIMENSION, DIMENSIONS, NODES, SAMPLE, SAMPLES

# What a tool's dialog should offer to ask about unless told otherwise: which
# data to look at. The rest — metrics, grids, bandwidths — stay as they were.
DATA_KINDS = (SAMPLES, DIMENSIONS, DIMENSION, SAMPLE)


@dataclass
class Candidate:
    """One option of one step that could become a parameter."""
    step_id: str
    option: str
    label: str
    kind: str
    exposed_by_default: bool


def candidates(workflow, step_ids):
    """The options of these steps that can be exposed, in step order."""
    found = []
    for step_id in step_ids:
        step = workflow.get(step_id)
        node = NODES.get(step.tool)
        if node is None:
            continue
        for field in node.fields:
            if field.key in step.options:
                found.append(Candidate(step_id, field.key, field.label, field.kind,
                                       field.kind in DATA_KINDS))
    return found


def option_label(workflow, candidate):
    """
    How the Save as tool dialog names an option: the step as it is numbered on the canvas (1,
    1.1, 2…), the block, and the option — "Step 1.1 · Comparison · Comparison metric".
    """
    step = workflow.get(candidate.step_id)
    number = workflow.numbers().get(candidate.step_id, "?")
    node = NODES.get(step.tool)
    return f"Step {number} · {node.label if node else step.tool} · {candidate.label}"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "tool"


def build_tool(workflow, specs, step_ids, name, toolbox, description="",
               exposed=None, taken=()):
    """
    Make a ToolDef from some of a workflow's steps.

    Args:
        workflow: the Workflow
        specs: {block key: NodeSpec}, to tell a table from other data
        step_ids: the steps to include, which must be closed over what they read
            from each other (a step reading one left out must read a table)
        exposed: {(step id, option)} to turn into parameters; by default the data
            choices (samples, dimensions)
        taken: tool keys already in use, which the new key must avoid

    Raises:
        ToolError: for no steps, no name, or a step that reads something that is
            neither in the tool nor a table
    """
    if not name.strip():
        raise ToolError("Give the tool a name.")
    chosen = [s.id for s in workflow.steps if s.id in set(step_ids)]
    if not chosen:
        raise ToolError("Choose at least one step.")
    if exposed is None:
        exposed = {(c.step_id, c.option) for c in candidates(workflow, chosen)
                   if c.exposed_by_default}

    local = {step_id: f"s{i + 1}" for i, step_id in enumerate(chosen)}
    steps, params, by_option = [], [], {}
    for step_id in chosen:
        step = workflow.get(step_id)
        node = NODES[step.tool]
        fixed = {k: v for k, v in step.options.items() if k != "title"}
        expose = {}
        for field in node.fields:
            if (step_id, field.key) not in exposed or field.key not in step.options:
                continue
            # Two steps asking for the same option of the same block share one
            # parameter (the samples to use); anything else gets a key of its own.
            shared = by_option.get((step.tool, field.key))
            if shared is None:
                key = field.key if field.key not in {p.key for p in params} \
                    else f"{field.key}_{local[step_id]}"
                by_option[(step.tool, field.key)] = key
                params.append(ParamSpec(
                    key, source=f"{local[step_id]}.{field.key}",
                    default=_plain(step.options[field.key]),
                    label=field.label if key == field.key else
                    f"{field.label} ({node.label.lower()})"))
                shared = key
            expose[field.key] = shared
            fixed.pop(field.key, None)
        steps.append(ToolStep(local[step_id], step.tool, _plain(fixed), expose,
                              _wiring(workflow, specs, step, local)))

    base = slug(name)
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    tool = ToolDef(key, name.strip(), toolbox.strip() or "My tools",
                   description.strip(), params, steps)
    check_tool(tool)
    return tool


def _wiring(workflow, specs, step, local):
    inputs = {}
    for port, sources in step.inputs.items():
        mapped = []
        for source in sources:
            if step_of(source) in local:
                mapped.append(source_ref(local[step_of(source)], split_source(source)[1]))
            elif source == DATA or workflow.type_of(source, specs) == TABLE:
                if TABLE_INPUT not in mapped:
                    mapped.append(TABLE_INPUT)
            else:
                number = workflow.numbers().get(step_of(source), source)   # as the block is numbered on the canvas
                raise ToolError(
                    f"{NODES[step.tool].label} reads step {number}, which is not "
                    "part of the tool and does not make a table. Include it, or "
                    "leave this step out.")
        inputs[port] = mapped
    return inputs


def _plain(value):
    """Options as plain JSON-able data: tuples and sets become lists."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    return value
