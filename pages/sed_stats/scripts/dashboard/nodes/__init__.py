"""
Every node a workflow can use, and the menu that lists them.

Nodes come in two kinds: compute nodes (`compute`) that turn one type of data
into another, and graphs (`graphs`) that end a chain by drawing it.
"""
from .base import (
    CHECKBOX, Context, DATA_PAGE, DIMENSION, DIMENSIONS, Field, NUMBER, Node,
    OPTIONS_PAGE, SAMPLE, SAMPLES, SELECT, StepOutput, TEXT, context_of, likely_column,
)
from .compute import COMPUTE_NODES
from .graphs import GRAPH_NODES
from .groundwater import GROUNDWATER_NODES
from .hydro import HYDRO_NODES
from .isotope import ISOTOPE_NODES
from .isotope_plots import ISOTOPE_PLOT_NODES
from .maps import MAP_NODES
from .outlines import table_outlines
from .tablework import TABLE_NODES

NODES = {node.key: node for node in COMPUTE_NODES + [table_outlines] + TABLE_NODES + ISOTOPE_NODES + ISOTOPE_PLOT_NODES + HYDRO_NODES + GROUNDWATER_NODES + MAP_NODES + GRAPH_NODES}

# Menu order: the categories a node can name, and what each is for.
CATEGORIES = ("Describe", "Transform", "Compare", "Model", "Groundwater", "Map", "Graph")


def specs():
    """{key: NodeSpec} for the workflow engine."""
    return {key: node.spec for key, node in NODES.items()}


def compute(step, inputs):
    """The engine's compute callback: run a compute step's node."""
    return NODES[step.tool].run(inputs, step.options)


def render(step, inputs):
    """The engine's render callback: run a graph step's node."""
    return NODES[step.tool].run(inputs, step.options)


def menu():
    """{category: [node keys]} in menu order, skipping empty categories."""
    found = {}
    for category in CATEGORIES:
        keys = [n.key for n in NODES.values()
                if n.spec.category == category and getattr(n, "listed", True)]
        if keys:
            found[category] = keys
    return found


__all__ = ["CHECKBOX", "CATEGORIES", "Context", "DATA_PAGE", "DIMENSION",
           "DIMENSIONS", "Field", "NODES", "NUMBER", "Node", "OPTIONS_PAGE",
           "SAMPLE", "SAMPLES", "SELECT", "StepOutput", "TEXT", "compute",
           "context_of", "likely_column", "menu", "render", "specs"]
