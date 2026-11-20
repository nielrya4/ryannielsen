"""
Outlines from a table: polygons (or lines) whose vertices are rows of the spreadsheet.

    Outlines from a table   Table -> Polygon   each chosen sample is one outline, its rows the
                                               vertices in the order they are listed

This is how a reference diagram — the fields of a Hjulström diagram, a ternary classification, a
published envelope — goes in as data: type or paste its corners as rows, one sample per outline,
beside the samples you measured (the spreadsheet is one table, so a sample's name says which rows
are outlines and which are data). Draw the outlines with a Scatterplot, under or over Points.
"""
from workflow_lib import NodeProblem, POLYGON, Port, TABLE
from workflow_lib.types import Polygons

from ..dataset import sample_names
from ..table_ops import number_of
from .base import (
    CHECKBOX, DATA_PAGE, DIMENSION, Field, Node, OPTIONS_PAGE, SAMPLES, SELECT, table_of,
)

SHAPES = {"closed": "Closed outlines — the last row joins back to the first",
          "open": "Open lines — the rows are only joined in order"}


def read_outlines(rows, sample_col, x_col, y_col, samples):
    """
    {sample: [(x, y), ...]} for the chosen samples, vertices in the order the rows are listed,
    and how many rows were left out for lacking a number in either column.
    """
    chosen = list(samples)
    found = {name: [] for name in chosen}
    skipped = 0
    for row in rows:
        name = str(row.get(sample_col, "") or "").strip()
        if name not in found:
            continue
        x, y = number_of(row.get(x_col)), number_of(row.get(y_col))
        if x is None or y is None:
            skipped += 1
            continue
        found[name].append((x, y))
    return found, skipped


def _run_outlines(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    closed = opts.get("shape", "closed") == "closed"
    found, skipped = read_outlines(rows, sample_col, opts["x_dimension"], opts["y_dimension"],
                                   opts["samples"])
    need = 3 if closed else 2
    for name, vertices in found.items():
        if len(vertices) < need:
            raise NodeProblem(
                f"'{name}' has {len(vertices)} usable row{'s' if len(vertices) != 1 else ''}; "
                f"{'an outline needs at least three corners' if closed else 'a line needs at least two points'}.")
    note = (f"{len(found)} {'outline' if closed else 'line'}{'s' if len(found) != 1 else ''}: "
            + ", ".join(f"{name} ({len(v)} vertices)" for name, v in found.items()) + "."
            + (f" {skipped} row{'s' if skipped != 1 else ''} had no number in "
               f"'{opts['x_dimension']}' or '{opts['y_dimension']}' and "
               f"{'was' if skipped == 1 else 'were'} left out." if skipped else ""))
    return [Polygons(opts["x_dimension"], opts["y_dimension"], list(found.items()), note=note,
                     name="Outlines", open=not closed,
                     fill=bool(opts.get("fill")) and closed)], None


def _validate_outlines(opts, context):
    if not opts.get("samples"):
        return "Choose the samples whose rows are the outlines."
    if not opts.get("x_dimension") or not opts.get("y_dimension"):
        return "Choose the x and y columns."
    if opts["x_dimension"] == opts["y_dimension"]:
        return "The x and y columns must be different."
    return None


table_outlines = Node(
    "table_outlines", "Outlines from a table", "Describe",
    [Port("table", (TABLE,), "Table")], POLYGON,
    [
        Field("samples", "Samples that are outlines", SAMPLES, unchecked=True, page=DATA_PAGE,
              hint="Each chosen sample is one outline, its rows the vertices in the order listed"),
        Field("x_dimension", "X column", DIMENSION, numeric_only=True, page=DATA_PAGE,
              like=("size", "x")),
        Field("y_dimension", "Y column", DIMENSION, numeric_only=True, nth=1, page=DATA_PAGE,
              like=("velocity", "y")),
        Field("shape", "Shape", SELECT, choices=SHAPES, default="closed", page=OPTIONS_PAGE),
        Field("fill", "Shade the inside", CHECKBOX, default=True, page=OPTIONS_PAGE,
              when=lambda o: o.get("shape", "closed") == "closed",
              hint="A faint fill in each outline's colour, beneath any points"),
    ],
    _run_outlines, _validate_outlines,
    description="Builds polygons from rows of the spreadsheet — a reference diagram's fields typed in "
                "as corners, one sample per outline. Draw them under your own points with a "
                "Scatterplot (log axes suit a Hjulström diagram).")
