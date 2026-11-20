"""
Workflows: analyses chained into a pipeline of typed building blocks.

A workflow is an ordered list of steps. Each step is one node — a computation
or a graph — with the options its dialog collected, and names where each of the
node's input ports reads from: the spreadsheet ("data") or an earlier step.
What flows between steps is typed (`types`): a Distribution turns a Table into
Lines, a Comparison turns Lines into a Matrix, an MDS turns a Matrix into
Points, and a Scatter graph draws Points. Ports only accept the types they
can use, so a chain that is wired up is a chain that makes sense.

Components:
    types           - Table, Line, Raster, Points, Matrix, Polygon, Proportions
    Port, NodeSpec  - what a node reads and produces
    Step, Workflow  - the chain, and how it is edited
    WorkflowEngine  - runs it, caching each compute step's result
    ToolDef         - a pre-wired chain with a short dialog, grouped into toolboxes (`tools`)
    DATA            - the id of the spreadsheet as a step's source
"""
from .nodes import NodeProblem, NodeSpec, Output, Port
from .types import (
    FACTORS, LINE, MATRIX, POINTS, POLYGON, PROPORTIONS, RASTER, TABLE, TYPE_LABELS,
)
from .workflow import DATA, Step, Workflow, WorkflowError
from .engine import StepResult, WorkflowEngine, table_signature
from .tools import ParamSpec, ToolDef, ToolError, ToolStep, instantiate, tool_from_dict

__all__ = [
    'DATA', 'Step', 'Workflow', 'WorkflowError',
    'StepResult', 'WorkflowEngine', 'table_signature',
    'NodeProblem', 'NodeSpec', 'Output', 'Port', 'TYPE_LABELS',
    'ParamSpec', 'ToolDef', 'ToolError', 'ToolStep', 'instantiate', 'tool_from_dict',
    'TABLE', 'LINE', 'RASTER', 'POINTS', 'MATRIX', 'POLYGON', 'PROPORTIONS', 'FACTORS',
]
