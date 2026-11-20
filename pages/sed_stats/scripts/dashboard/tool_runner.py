"""
Running a tool: its chain of blocks, on a table, to one output.

The tool's steps are laid out as a throwaway workflow and run by the same engine
the Workflow tab uses, so a tool and the blocks it is made of cannot disagree.
Whatever the steps draw is gathered into a single output, and a tool that adds
columns to the spreadsheet hands those back.
"""
from dataclasses import dataclass

from antioch.elements import Div

from workflow_lib import DATA, Workflow, WorkflowEngine
from workflow_lib.workflow import source_ref
from workflow_lib.engine import OK
from workflow_lib.tools import TABLE_INPUT, instantiate, sheet_step

from . import nodes
from .nodes import StepOutput


class ToolFailure(Exception):
    """A step of the tool could not run; the message says which and why."""


@dataclass
class ToolResult:
    output: StepOutput
    sheet_rows: list = None     # the table to write back to the spreadsheet, if any


def run_tool(tool, opts, rows):
    """
    Run `tool` with the dialog's `opts` on `rows`.

    Raises:
        ToolFailure: if a step fails; later steps that needed it are not run
    """
    planned = instantiate(tool, opts)
    workflow = Workflow()
    real = {}
    def actual(source):
        """The workflow's own name for a source the tool wired by its local one."""
        if source == TABLE_INPUT:
            return DATA
        local, _, output = source.partition(".")
        return source_ref(real[local], output)

    for step in planned:
        inputs = {port: [actual(s) for s in sources] for port, sources in step.inputs.items()}
        real[step.id] = workflow.add(step.node, step.options, inputs).id
    engine = WorkflowEngine(workflow, lambda: rows, nodes.specs(),
                            nodes.compute, nodes.render)

    outputs = []
    for result in engine.run_all():
        if result.status != OK:
            label = nodes.NODES[workflow.get(result.step_id).tool].label
            raise ToolFailure(f"{label}: {result.message}")
        if isinstance(result.report, StepOutput):
            outputs.append(result.report)

    sheet_rows = None
    target = sheet_step(tool, opts)
    if target is not None:
        sheet_rows = engine.batch_for(real[target])[0]
    return ToolResult(_combine(outputs, opts.get("title") or tool.label), sheet_rows)


def _combine(outputs, title):
    """One output from what the steps drew: as it is for one, stacked for several."""
    if not outputs:
        return StepOutput(title, Div(), [], None)
    if len(outputs) == 1:
        only = outputs[0]
        return StepOutput(title, only.body, only.charts, only.tabview)
    charts = [chart for out in outputs for chart in out.charts]
    return StepOutput(title, Div(*[out.body for out in outputs]), charts, None)
