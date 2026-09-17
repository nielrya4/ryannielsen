"""
The PCA axes tool: reduce many measured variables to PC1 and PC2 per grain.

Writes the scores back into the spreadsheet as columns, so every other tool
picks them up as ordinary dimensions — a PDP of PC1, a top-down unmix along
PC1, a bivariate density over PC1 x PC2.

The fit is global, over every grain of every selected sample at once. That is
what keeps a mixture of populations a convex combination after the transform,
and so what makes unmixing along a derived axis valid.
"""
from antioch.elements import Div, P

from plot_lib import bar_trace
from sed_stats import pca

from .plots import make_plot
from .tables import result_table

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
NOTE_STYLE = {"color": "#6c757d"}

# Column names written back to the sheet. Rerunning overwrites them.
AXIS_COLUMNS = ("PC1", "PC2")


def build_pca_axes(charts, rows, sample_col, dimensions, opts, set_rows=None):
    """
    `dimensions` is the whole list of variables to reduce.

    Unusually for a builder this has a side effect: it rewrites the
    spreadsheet. The gallery entry it returns is the record of what was done —
    which variables went in, and what the axes turned out to mean.
    """
    variables = [d for d in dimensions if d not in AXIS_COLUMNS]
    if len(variables) < 2:
        return P("Choose at least two variables to reduce.", style=NOTE_STYLE)

    selected = opts.get("samples")
    complete, matrix = _complete_rows(rows, sample_col, variables, selected)
    if len(matrix) < 2:
        return P("No grains have a value for every chosen variable.",
                 style=NOTE_STYLE)

    weights = None
    if opts.get("grain_weighting") == "sample":
        weights = _sample_weights([row for row, _ in complete], sample_col)

    result = pca.grain_pca(matrix, variables=variables, n_components=2,
                           weights=weights)

    updated = _write_scores(rows, complete, result)
    if set_rows:
        set_rows(updated)

    scored = len(complete)
    total_rows = len([r for r in rows
                      if selected is None
                      or str(r.get(sample_col, "") or "").strip() in selected])
    wrapper = Div(
        P(f"{scored} of {total_rows} grains scored on "
          f"{len(variables)} standardized variables. "
          f"PC1 explains {result.percent(0):.1f}% and PC2 "
          f"{result.percent(1):.1f}% of the variance between grains.",
          style=CAPTION_STYLE),
        P("PC1 and PC2 are now columns in the spreadsheet — every other tool "
          "will offer them as dimensions.", style=CAPTION_STYLE),
        _loadings_table(result),
    )
    if scored < total_rows:
        wrapper.add(P(f"{total_rows - scored} grains were left blank for "
                      f"missing a value.", style=NOTE_STYLE))
    if opts.get("scree"):
        wrapper.add(*_scree_section(charts, result))
    return wrapper


def _complete_rows(rows, sample_col, variables, selected):
    """
    Rows usable for the fit, paired with their index in the original table.

    A grain missing any one variable has no position in the variable space, so
    it is scored as blank rather than imputed.
    """
    complete = []
    matrix = []
    for index, row in enumerate(rows):
        sample = str(row.get(sample_col, "") or "").strip()
        if selected is not None and sample not in selected:
            continue
        values = []
        for variable in variables:
            raw = row.get(variable, "")
            if raw in ("", None):
                values = None
                break
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                values = None
                break
        if values is None:
            continue
        complete.append((row, index))
        matrix.append(values)
    return complete, matrix


def _sample_weights(rows, sample_col):
    """1/n per grain, so every sample pulls on the axis equally."""
    counts = {}
    for row in rows:
        sample = str(row.get(sample_col, "") or "").strip()
        counts[sample] = counts.get(sample, 0) + 1
    return [1.0 / counts[str(row.get(sample_col, "") or "").strip()]
            for row in rows]


def _write_scores(rows, complete, result):
    """Copy the rows with PC1/PC2 filled in; unscored grains get blanks."""
    updated = [dict(row) for row in rows]
    for row in updated:
        for column in AXIS_COLUMNS:
            row[column] = ""

    for position, (_, index) in enumerate(complete):
        for axis, column in enumerate(AXIS_COLUMNS):
            if axis < result.scores.shape[1]:
                updated[index][column] = f"{float(result.scores[position, axis]):.6g}"
    return updated


def _loadings_table(result):
    """What the axes mean, in terms of the variables that made them."""
    body = []
    # Ordered by influence on PC1, so the axis reads top-down.
    for variable, loading in result.loadings(0):
        column = result.variables.index(variable)
        second = (float(result.components[1, column])
                  if result.components.shape[0] > 1 else 0.0)
        body.append([variable, f"{float(loading):+.3f}", f"{second:+.3f}"])

    return Div(
        P("Loadings — a variable with a large positive weight pushes grains "
          "toward the positive end of that axis; opposite signs mean the axis "
          "is a trade-off between those variables.",
          style={**CAPTION_STYLE, "margin": "16px 0 6px 0"}),
        result_table(
            ["Variable",
             f"PC1 ({result.percent(0):.1f}%)",
             f"PC2 ({result.percent(1):.1f}%)"],
            body,
        ),
    )


def _scree_section(charts, result):
    ratios = [float(r) * 100 for r in result.explained_ratio_all]
    names = [f"PC{i + 1}" for i in range(len(ratios))]
    trace = bar_trace(names, ratios, "Explained variance", color="#3b6fb6")

    caption = P("Scree plot — how much of the grain-to-grain variance each "
                "component carries. A steep drop after PC1 means one axis "
                "captures most of it; a shallow one means reducing to two "
                "axes throws real information away.",
                style={**CAPTION_STYLE, "margin": "16px 0 6px 0"})
    plot = Div(make_plot(
        charts, [trace], "PCA axes — scree", "Component", "% variance",
        height=320, show_legend=False, filename="pca_axes_scree",
        extra_layout={"xaxis": {"title": {"text": "Component"}, "type": "category"}},
    ).element)
    return caption, plot
