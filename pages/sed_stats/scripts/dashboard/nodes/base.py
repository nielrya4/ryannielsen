"""
What a node is, in full: its ports, its option fields, and what it does.

`workflow_lib.NodeSpec` carries only what the workflow needs to wire nodes
together. A `Node` adds the rest — the option fields a dialog is built from
and the function that runs — so one definition drives both the form the user
fills in and the work that follows.

A compute node's `run(inputs, opts)` returns `(batch, report)`; a graph's
returns a `StepOutput`. `inputs` maps each port to a list of batches (see
`workflow_lib.engine`), and every node works through its batches item by item,
so "three dimensions" stays three results all the way down a chain.
"""
from collections import namedtuple
from dataclasses import dataclass, field

from workflow_lib import NodeProblem, NodeSpec
from workflow_lib.types import (
    Factors, Lines, Matrix, Points, Polygons, Proportions, Raster, TABLE,
)

from ..dataset import date_columns, detect_columns, numeric_columns, sample_names

# What running a node produces for display, before anything decides where it
# is shown: a title, a body element, the charts in it (for resizing and export)
# and the tab view, if it has one.
# `preview` is (titles, cells) of a few rows of a table, for the block's thumbnail when there is
# no plot to take it from.
StepOutput = namedtuple("StepOutput", "title body charts tabview preview", defaults=(None,))

SELECT = "select"
CHECKBOX = "checkbox"
NUMBER = "number"
TEXT = "text"                  # a short piece of free text
DIMENSIONS = "dimensions"      # several columns of the input table
DIMENSION = "dimension"        # one column
SAMPLES = "samples"            # several samples of the input
SAMPLE = "sample"              # one sample

DATA_PAGE = "Data"
OPTIONS_PAGE = "Options"


@dataclass
class Field:
    """
    One option of a node, described rather than built.

    Args:
        key: its name in the saved options
        kind: SELECT, CHECKBOX, NUMBER, TEXT, DIMENSIONS, DIMENSION, SAMPLES or SAMPLE
        choices: for SELECT, `{value: label}` or `(context) -> {value: label}`
        default: the starting value (a SELECT defaults to its first choice)
        numeric_only: for DIMENSION(S), offer only columns of numbers
        dates: with `numeric_only`, offer columns of dates too, for a block that reads them as a
            position (the block must turn a date into a number itself: see `sed_stats.dates`)
        unchecked: for SAMPLES, start with none ticked (the default ticks all), for a
            list that is optional, such as which samples to compare against
        signed: for a NUMBER, allow zero and negatives (the default takes only
            positive numbers, which is what widths and counts are)
        dynamic: the choices depend on the other options, so `choices` is called
            as `(context, opts)` and again whenever an option changes
        cast: applied to a SELECT's chosen key (`int`, `float`) to get its value
        nth: for a DIMENSION, which of the columns to start on, so three
            apex pickers can open on three different ones
        like: for a DIMENSION, words that a likely column's name contains ("date", "time"):
            the picker opens on the first column that has one, and on `nth` if none does
        when: `(opts) -> bool`; the field is shown only while it holds, so a
            bivariate-only option disappears in univariate mode
        page: DATA_PAGE for choosing what goes in, OPTIONS_PAGE for how
    """
    key: str
    label: str
    kind: str
    hint: str = ""
    choices: object = None
    default: object = None
    numeric_only: bool = False
    dates: bool = False
    cast: object = None
    signed: bool = False
    unchecked: bool = False
    dynamic: bool = False
    nth: int = 0
    like: tuple = ()
    when: object = None
    page: str = OPTIONS_PAGE


@dataclass
class Context:
    """What a dialog knows about the data its first input will deliver."""
    input_type: str = None
    dimensions: list = field(default_factory=list)
    numeric: set = field(default_factory=set)
    samples: list = field(default_factory=list)
    dates: set = field(default_factory=set)


def context_of(data_type, batch):
    """Describe the first item of a source's batch, for filling a dialog's choices."""
    if not batch:
        return Context(data_type)
    item = batch[0]
    if data_type == TABLE:
        rows = item
        sample_col, _, dimensions = detect_columns(rows)
        return Context(TABLE, list(dimensions),
                       set(numeric_columns(rows, dimensions)),
                       sample_names(rows, sample_col),
                       set(date_columns(rows, dimensions)))
    if isinstance(item, Lines):
        return Context(data_type, [], set(), [name for name, _ in item.pdf])
    if isinstance(item, Raster):
        return Context(data_type, [], set(),
                       [name for name, _ in item.density_set.entries])
    if isinstance(item, Points):
        return Context(data_type, [], set(), [g[0] for g in item.groups])
    if isinstance(item, Matrix):
        return Context(data_type, [], set(), list(item.names))
    if isinstance(item, Polygons):
        return Context(data_type, [], set(), [n for n, _ in item.shapes])
    if isinstance(item, Proportions):
        return Context(data_type, [], set(), list(item.names))
    if isinstance(item, Factors):
        return Context(data_type, [], set(), list(item.sample_names))
    return Context(data_type)


def _plain(label):
    """A label in running text: ordinary words lowercased, symbols and acronyms left alone
    (so "Baseline δ¹⁵N (‰)" does not become "δ¹⁵n")."""
    return " ".join(w.lower() if w == w.capitalize() else w for w in label.split())


class Node:
    """
    Args:
        key, label, category, ports, output, extras, output_label: see
            `workflow_lib.NodeSpec`. A node with `extras` returns, in place of a batch,
            a dict of batches: the first output under "" and each extra under its name
        fields: the option Fields, in display order
        run: `(inputs, opts) -> (batch, report)` for a compute node, or
            `-> StepOutput` for a graph
        validate: `(opts, context) -> message or None`, checked before a step
            is added
        description: what the node is for, shown in its dialog
    """

    def __init__(self, key, label, category, ports, output, fields, run,
                 validate=None, description="", extras=(), output_label=""):
        self.spec = NodeSpec(key, label, category, tuple(ports), output, tuple(extras),
                             output_label)
        self.fields = list(fields)
        self.run = run
        self.validate = validate
        self.description = description

    @property
    def key(self):
        return self.spec.key

    @property
    def label(self):
        return self.spec.label

    @property
    def is_graph(self):
        return self.spec.is_graph

    def describe(self, opts):
        """A line saying what a configured step will do, from its options."""
        parts = []
        for f in self.fields:
            value = opts.get(f.key)
            if f.when and not f.when(opts):
                continue
            if f.kind == DIMENSIONS and value:
                parts.append(", ".join(value[:4])
                             + (f" +{len(value) - 4} more" if len(value) > 4 else ""))
            elif f.kind == SAMPLES and value is not None:
                parts.append(f"{len(value)} sample{'s' if len(value) != 1 else ''}")
            elif f.kind in (DIMENSION, SAMPLE) and value:
                parts.append(f"{_plain(f.label)} {value}")
            elif f.kind == SELECT and value not in (None, "") \
                    and isinstance(f.choices, dict):
                key = str(value) if str(value) in f.choices else value
                # The short form of a long label: "Univariate — one dimension…".
                text = str(f.choices.get(key, value)).split(" — ")[0]
                # A bare number says nothing on its own ("5"): say what it is.
                parts.append(f"{_plain(f.label)} {text}" if text.replace(",", "").isdigit()
                             else text)
            elif f.kind in (NUMBER, TEXT) and value not in (None, ""):
                parts.append(f"{_plain(f.label)} {value:g}" if isinstance(value, float)
                             else f"{_plain(f.label)} {value}")
            elif f.kind == CHECKBOX and value:
                parts.append(_plain(f.label))
        return " · ".join(parts) or self.label


# ----------------------------------------------------------------- run helpers

def table_of(inputs, port):
    """(rows, sample column) of the table on `port`."""
    rows = inputs[port][0][0]
    sample_col, _, _ = detect_columns(rows)
    return rows, sample_col


def likely_column(columns, words):
    """The first of `columns` whose name contains one of `words` (any case), or None."""
    for column in columns:
        name = str(column).lower()
        if any(word.lower() in name for word in words):
            return column
    return None


def need_dimensions(opts):
    if not opts.get("dimensions"):
        raise NodeProblem("Select at least one dimension.")
    return list(opts["dimensions"])


def numbered(items, key=None):
    """`items` as {value: label} for a SELECT, from a config dict of dicts."""
    return {k: (v["label"] if isinstance(v, dict) else v) for k, v in items.items()}
