"""
The blocks that turn a table into another table, for cleaning data before analysis.

    Filter grains      keep some samples, or the grains whose value is in a range,
                       one of some values, or present
    Transform column   add a log, square root, reciprocal or z-score of a column
    Ratio column       add one column divided by another (Th/U, say)

None of them changes the spreadsheet; each returns a copy, which a later step reads.
A tool made from one can write the result back if asked.
"""
from antioch.elements import Div, P

from workflow_lib import NodeProblem, Port, TABLE

from ..table_ops import (
    CARBONATE_EQUATIONS, DATE_PARTS, FILTER_HOW, TRANSFORM_LABELS, convert_scale,
    date_part_column, difference_column, filter_rows, lipid_column, ratio_column,
    regroup_samples, sample_summary, temperature_column, transform_column, trophic_column,
)
from ..tables import result_table
from .base import (
    CHECKBOX, DATA_PAGE, DIMENSION, DIMENSIONS, Field, NUMBER, Node, OPTIONS_PAGE, SAMPLE,
    SAMPLES, SELECT,
    StepOutput, TEXT, table_of,
)

NOTE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}


def _card(opts, label, summary, extra=None):
    body = Div(P(summary, style=NOTE))
    if extra is not None:
        body.add(extra)
    return StepOutput(opts.get("title") or label, body, [], None)


# ---------------------------------------------------------------------- filter

def _run_filter(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    result = filter_rows(rows, sample_col, opts.get("samples"), opts.get("how", "samples"),
                         opts.get("column"), opts.get("minimum"), opts.get("maximum"),
                         opts.get("values"))
    lines = [[sample, str(result.before[sample]), str(result.after.get(sample, 0)),
              str(result.before[sample] - result.after.get(sample, 0))]
             for sample in result.before]
    table = result_table(["Sample", "Grains in", "Kept", "Dropped"], lines)
    return [result.rows], _card(opts, "Filter grains", result.summary, table)


def _validate_filter(opts, context):
    if not opts.get("samples"):
        return "Select at least one sample."
    how = opts.get("how", "samples")
    if how != "samples" and not opts.get("column"):
        return "Choose the column to filter on."
    if how == "range" and opts.get("minimum") is None and opts.get("maximum") is None:
        return "Give a minimum, a maximum, or both."
    if how == "values" and not opts.get("values"):
        return "List the values to keep, separated by commas."
    return None


def _filtering(opts):
    return opts.get("how", "samples") != "samples"


filter_grains = Node(
    "filter_grains", "Filter grains", "Transform",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("samples", "Samples", SAMPLES, page=DATA_PAGE,
              hint="Only these samples are kept"),
        Field("how", "Filter", SELECT, choices=FILTER_HOW, default="samples", page=DATA_PAGE),
        Field("column", "Column", DIMENSION, page=DATA_PAGE, when=_filtering,
              hint="The column the filter looks at"),
        Field("minimum", "Minimum", NUMBER, signed=True, page=DATA_PAGE,
              when=lambda o: o.get("how") == "range",
              hint="Blank for no lower limit; the limit itself is kept"),
        Field("maximum", "Maximum", NUMBER, signed=True, page=DATA_PAGE,
              when=lambda o: o.get("how") == "range",
              hint="Blank for no upper limit; the limit itself is kept"),
        Field("values", "Values to keep", TEXT, page=DATA_PAGE,
              when=lambda o: o.get("how") == "values",
              hint="Separated by commas, matched exactly (e.g. rounded, angular)"),
    ],
    _run_filter, _validate_filter,
    description="Keeps some of the grains: only certain samples, or those whose value in a "
                "column is within a range, is one of a list, or is present at all. "
                "Returns a filtered copy of the table; the spreadsheet is not changed.")


# ------------------------------------------------------------------- transform

def _run_transform(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    result = transform_column(rows, sample_col, opts.get("column"),
                              opts.get("function", "log10"), opts.get("name"))
    return [result.rows], _card(opts, "Transform column", result.summary)


def _validate_transform(opts, context):
    return None if opts.get("column") else "Choose the column to transform."


transform = Node(
    "transform_column", "Transform column", "Transform",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("column", "Column", DIMENSION, numeric_only=True, page=DATA_PAGE),
        Field("function", "Transformation", SELECT, choices=TRANSFORM_LABELS,
              default="log10", page=DATA_PAGE,
              hint="Values the function cannot take (the log of zero) are left blank"),
        Field("name", "New column's name", TEXT, page=DATA_PAGE,
              hint="Blank names it after the transformation, e.g. log10(age_Ma). An "
                   "existing column with that name is replaced"),
    ],
    _run_transform, _validate_transform,
    description="Adds a transformed copy of a column — a log, square root, reciprocal or "
                "z-score — beside the original. An uncertainty column is not carried "
                "across, so the new column is smoothed by KDE, not by uncertainties.")


# ----------------------------------------------------------------------- ratio

def _run_ratio(inputs, opts):
    rows, _ = table_of(inputs, "table")
    result = ratio_column(rows, opts.get("numerator"), opts.get("denominator"),
                          opts.get("name"), opts.get("factor") or 1.0)
    return [result.rows], _card(opts, "Ratio column", result.summary)


def _validate_ratio(opts, context):
    if not opts.get("numerator") or not opts.get("denominator"):
        return "Choose both columns."
    if opts["numerator"] == opts["denominator"]:
        return "Choose two different columns."
    return None


ratio = Node(
    "ratio_column", "Ratio column", "Transform",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("numerator", "Top", DIMENSION, numeric_only=True, page=DATA_PAGE),
        Field("denominator", "Bottom", DIMENSION, numeric_only=True, nth=1, page=DATA_PAGE,
              hint="Grains where this is zero or missing are left blank"),
        Field("factor", "Multiply by", NUMBER, default=1, page=DATA_PAGE,
              hint="1 for the plain ratio. 1.1662 (14.007/12.011) turns a weight ratio of "
                   "C to N into an atomic one"),
        Field("name", "New column's name", TEXT, page=DATA_PAGE,
              hint="Blank names it after the ratio, e.g. Th/U"),
    ],
    _run_ratio, _validate_ratio,
    description="Adds one column divided by another — Th/U, Lu/Hf — as a new column, "
                "optionally scaled by a constant.")


# --------------------------------------------------------------------- isotopes
# Each adds one column to a table of stable-isotope measurements. The formulas, and
# where each constant comes from, are in sed_stats.isotopes.

NAME_FIELD = Field("name", "New column's name", TEXT, page=DATA_PAGE,
                   hint="Blank gives it a name that says what it is. An existing column "
                        "with that name is replaced")

SCALE_CONVERSIONS = {
    "vpdb_to_vsmow": "δ¹⁸O  VPDB → VSMOW  (Coplen et al. 1983)",
    "vsmow_to_vpdb": "δ¹⁸O  VSMOW → VPDB  (Coplen et al. 1983)",
    "vpdb_to_vsmow:iupac": "δ¹⁸O  VPDB → VSMOW  (IUPAC values)",
    "vsmow_to_vpdb:iupac": "δ¹⁸O  VSMOW → VPDB  (IUPAC values)",
}


def _need_column(opts, key, label):
    return None if opts.get(key) else f"Choose the {label} column."


def _run_scale(inputs, opts):
    rows, _ = table_of(inputs, "table")
    result = convert_scale(rows, opts.get("column"), opts.get("conversion", "vpdb_to_vsmow"),
                           opts.get("name"))
    return [result.rows], _card(opts, "Convert scale", result.summary)


convert_oxygen = Node(
    "convert_scale", "Convert δ¹⁸O scale", "Transform",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("column", "δ¹⁸O column", DIMENSION, numeric_only=True, page=DATA_PAGE),
        Field("conversion", "Conversion", SELECT, choices=SCALE_CONVERSIONS,
              default="vpdb_to_vsmow", page=DATA_PAGE,
              hint="Carbonates are usually reported against VPDB, waters and phosphates "
                   "against VSMOW"),
        NAME_FIELD,
    ],
    _run_scale, lambda o, c: _need_column(o, "column", "δ¹⁸O"),
    description="Adds δ¹⁸O on the other of the two oxygen scales, VPDB or VSMOW: "
                "δ¹⁸O(VSMOW) = 1.03091 · δ¹⁸O(VPDB) + 30.91 (Coplen, Kendall & Hopple 1983).")


def _run_difference(inputs, opts):
    rows, _ = table_of(inputs, "table")
    result = difference_column(rows, opts.get("first"), opts.get("second"),
                               opts.get("form", "difference"),
                               1.0 if opts.get("factor") is None else opts["factor"],
                               opts.get("name"))
    return [result.rows], _card(opts, "Isotope difference", result.summary)


def _validate_difference(opts, context):
    if not opts.get("first") or not opts.get("second"):
        return "Choose both columns."
    if opts["first"] == opts["second"]:
        return "Choose two different columns."
    return None


difference = Node(
    "isotope_difference", "Isotope difference", "Transform",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("first", "First column", DIMENSION, numeric_only=True, page=DATA_PAGE,
              hint="δ²H for deuterium excess; the heavier phase for a fractionation"),
        Field("second", "Second column", DIMENSION, numeric_only=True, nth=1, page=DATA_PAGE,
              hint="δ¹⁸O for deuterium excess; the lighter phase for a fractionation"),
        Field("form", "Form", SELECT, default="difference", page=DATA_PAGE,
              choices={"difference": "First − factor × second",
                       "ln_alpha": "1000 ln α  (first against second)"}),
        Field("factor", "Factor", NUMBER, signed=True, default=1, page=DATA_PAGE,
              when=lambda o: o.get("form", "difference") == "difference",
              hint="1 for a plain difference Δ; 8 for deuterium excess, d = δ²H − 8·δ¹⁸O"),
        NAME_FIELD,
    ],
    _run_difference, _validate_difference,
    description="Adds the difference between two delta columns (Δ, or deuterium excess "
                "with a factor of 8) or the fractionation 1000 ln α between them, with "
                "α = (1000 + δ first) / (1000 + δ second).")


def _run_lipid(inputs, opts):
    rows, _ = table_of(inputs, "table")
    result = lipid_column(rows, opts.get("d13c"), opts.get("cn"), opts.get("name"))
    return [result.rows], _card(opts, "Lipid-normalise δ¹³C", result.summary)


def _validate_lipid(opts, context):
    return _need_column(opts, "d13c", "δ¹³C") or _need_column(opts, "cn", "C:N")


lipid = Node(
    "lipid_normalise", "Lipid-normalise δ¹³C", "Transform",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("d13c", "δ¹³C column", DIMENSION, numeric_only=True, page=DATA_PAGE),
        Field("cn", "C:N column", DIMENSION, numeric_only=True, nth=1, page=DATA_PAGE,
              hint="Atomic, not by weight"),
        NAME_FIELD,
    ],
    _run_lipid, _validate_lipid,
    description="Corrects δ¹³C of animal tissue for its lipid content, which is depleted in "
                "¹³C, from C:N: δ¹³C − 3.32 + 0.99 · C:N (Post et al. 2007, aquatic animals; "
                "fitted on animals with C:N up to 6.9).")


def _run_trophic(inputs, opts):
    rows, _ = table_of(inputs, "table")
    baseline = opts.get("baseline")
    if opts.get("baseline_from", "value") == "sample":
        values = [v for v in (_number(r.get(opts.get("d15n")))
                              for r in rows if _sample(r, inputs) == opts.get("baseline_sample"))
                  if v is not None]
        if not values:
            raise NodeProblem(f"The baseline sample '{opts.get('baseline_sample')}' has no "
                              "δ¹⁵N values.")
        baseline = sum(values) / len(values)
    result = trophic_column(rows, opts.get("d15n"), baseline,
                            float(opts.get("position") or 2),
                            3.4 if opts.get("enrichment") is None else opts["enrichment"],
                            opts.get("name"))
    return [result.rows], _card(opts, "Trophic position",
                                result.summary + f" Baseline δ¹⁵N {baseline:.2f}‰.")


def _sample(row, inputs):
    _, sample_col = table_of(inputs, "table")
    return str(row.get(sample_col, "") or "").strip()


def _number(value):
    from ..table_ops import number_of
    return number_of(value)


def _validate_trophic(opts, context):
    problem = _need_column(opts, "d15n", "δ¹⁵N")
    if problem:
        return problem
    if opts.get("baseline_from", "value") == "sample":
        return None if opts.get("baseline_sample") else "Choose the baseline sample."
    return None if opts.get("baseline") is not None else "Give the baseline δ¹⁵N."


trophic = Node(
    "trophic_position", "Trophic position", "Transform",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("d15n", "δ¹⁵N column", DIMENSION, numeric_only=True, page=DATA_PAGE),
        Field("baseline_from", "Baseline", SELECT, default="value", page=DATA_PAGE,
              choices={"value": "A δ¹⁵N value", "sample": "The mean of a sample"}),
        Field("baseline", "Baseline δ¹⁵N (‰)", NUMBER, signed=True, page=DATA_PAGE,
              when=lambda o: o.get("baseline_from", "value") == "value"),
        Field("baseline_sample", "Baseline sample", SAMPLE, page=DATA_PAGE,
              when=lambda o: o.get("baseline_from") == "sample",
              hint="An organism at the base of the food web, e.g. mussels or a primary producer"),
        Field("position", "Baseline's trophic position", SELECT, default="2",
              choices={"1": "1 — a primary producer", "2": "2 — a primary consumer"},
              page=OPTIONS_PAGE),
        Field("enrichment", "Enrichment per level (‰)", NUMBER, default=3.4, page=OPTIONS_PAGE,
              hint="3.4‰ is the mean from Post (2002); use a value measured for your system "
                   "if there is one"),
        NAME_FIELD,
    ],
    _run_trophic, _validate_trophic,
    description="Estimates each consumer's trophic level from δ¹⁵N against a baseline "
                "organism: λ + (δ¹⁵N − baseline) / Δn (Post 2002). Choose a baseline that "
                "integrates the same period and place as the consumers.")


def _run_temperature(inputs, opts):
    rows, _ = table_of(inputs, "table")
    custom = (opts.get("a") or 0.0, opts.get("b") or 0.0, opts.get("c") or 0.0)
    result = temperature_column(
        rows, opts.get("calcite"), opts.get("equation", "shackleton"),
        opts.get("scale", "vpdb"), 0.0 if opts.get("water") is None else opts["water"],
        opts.get("water_column") if opts.get("water_from") == "column" else None, custom,
        opts.get("name"))
    return [result.rows], _card(opts, "Carbonate temperature", result.summary)


def _validate_temperature(opts, context):
    problem = _need_column(opts, "calcite", "carbonate δ¹⁸O")
    if problem:
        return problem
    if opts.get("water_from") == "column" and not opts.get("water_column"):
        return "Choose the water δ¹⁸O column."
    if opts.get("equation") == "custom" and not (opts.get("a") is not None
                                                 and opts.get("b") is not None):
        return "Give at least a and b for your own equation."
    return None


temperature = Node(
    "carbonate_temperature", "Carbonate temperature", "Transform",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("calcite", "Carbonate δ¹⁸O column", DIMENSION, numeric_only=True, page=DATA_PAGE),
        Field("scale", "Carbonate reported against", SELECT, default="vpdb", page=DATA_PAGE,
              choices={"vpdb": "VPDB", "vsmow": "VSMOW"}),
        Field("water_from", "Water δ¹⁸O", SELECT, default="value", page=DATA_PAGE,
              choices={"value": "One value for all", "column": "A column"}),
        Field("water", "Water δ¹⁸O (‰ VSMOW)", NUMBER, signed=True, default=0, page=DATA_PAGE,
              when=lambda o: o.get("water_from", "value") == "value",
              hint="0 is mean ocean water; present-day ice-free ocean is near 0, glacial "
                   "ocean about +1"),
        Field("water_column", "Water δ¹⁸O column", DIMENSION, numeric_only=True, nth=1,
              page=DATA_PAGE, when=lambda o: o.get("water_from") == "column"),
        Field("equation", "Equation", SELECT, choices=CARBONATE_EQUATIONS,
              default="shackleton", page=OPTIONS_PAGE,
              hint="Each is calibrated on different material and a different temperature "
                   "range; the choice is yours to justify. x is the calcite minus water "
                   "difference on the VPDB scale (water less 0.27)"),
        Field("a", "a", NUMBER, signed=True, page=OPTIONS_PAGE,
              when=lambda o: o.get("equation") == "custom"),
        Field("b", "b", NUMBER, signed=True, page=OPTIONS_PAGE,
              when=lambda o: o.get("equation") == "custom"),
        Field("c", "c", NUMBER, signed=True, page=OPTIONS_PAGE,
              when=lambda o: o.get("equation") == "custom", hint="Blank for a straight line"),
        NAME_FIELD,
    ],
    _run_temperature, _validate_temperature,
    description="Estimates the temperature a carbonate grew at from its δ¹⁸O and that of "
                "the water: Shackleton (1974), Kim & O'Neil (1997) or a calibration you "
                "give. The water's δ¹⁸O is the largest unknown, and every ‰ of it is "
                "about 4–5 °C.")


# ------------------------------------------------------------------ dates and groups
# Hydrology groups by when a sample was taken — season, water year — and a method such as
# end-member splitting treats each sample as one category. These make the grouping from the
# dates, so the spreadsheet does not have to be labelled by hand.

def _run_date_part(inputs, opts):
    rows, _ = table_of(inputs, "table")
    result = date_part_column(
        rows, opts.get("column"), opts.get("part", "year"), opts.get("name"),
        bool(opts.get("day_first")), int(opts.get("water_year_start") or 10),
        opts.get("hemisphere", "north"), opts.get("season_months") or "",
        opts.get("first_name") or "First season", opts.get("second_name") or "Second season")
    return [result.rows], _card(opts, "Group by date", result.summary)


def _validate_date_part(opts, context):
    if not opts.get("column"):
        return "Choose the date column."
    if opts.get("part") == "two_seasons" and not opts.get("season_months"):
        return "List the months of the first season, e.g. Dec-Mar."
    return None


def _needs(*parts):
    return lambda o: o.get("part", "year") in parts


date_part = Node(
    "date_part", "Group by date", "Transform",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("column", "Date column", DIMENSION, page=DATA_PAGE, like=("date", "time"),
              hint="Dates such as 2021-01-16, 1/16/2021, 16-Jan-2021 or 2021-01; a number is not "
                   "read as a date"),
        Field("part", "Add", SELECT, choices=DATE_PARTS, default="year", page=DATA_PAGE),
        Field("season_months", "Months of the first season", TEXT, page=DATA_PAGE,
              when=_needs("two_seasons"),
              hint="Numbers or names, a range may wrap the year: Dec-Mar, or 4-11"),
        Field("first_name", "First season is called", TEXT, default="Snow", page=DATA_PAGE,
              when=_needs("two_seasons")),
        Field("second_name", "The rest is called", TEXT, default="Warm", page=DATA_PAGE,
              when=_needs("two_seasons")),
        Field("hemisphere", "Hemisphere", SELECT, default="north", page=OPTIONS_PAGE,
              choices={"north": "Northern", "south": "Southern"}, when=_needs("season")),
        Field("water_year_start", "Water year starts in month", NUMBER, default=10,
              page=OPTIONS_PAGE, when=_needs("water_year", "day_of_water_year"),
              hint="10 (October) in the United States; the year is named by the one it ends in"),
        Field("day_first", "Day before month", CHECKBOX, page=OPTIONS_PAGE,
              hint="Read 3/4/2021 as 3 April rather than 4 March"),
        NAME_FIELD,
    ],
    _run_date_part, _validate_date_part,
    description="Adds one part of each row's date as a column: the year, month, water year, "
                "day of the water year, season, or a split of the year into two seasons you "
                "define (snow and warm, say). Follow with Regroup samples to analyse by it.")


def _run_regroup(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    result = regroup_samples(rows, sample_col, opts.get("column"), opts.get("mode", "replace"))
    return [result.rows], _card(opts, "Regroup samples", result.summary)


regroup = Node(
    "regroup", "Regroup samples", "Transform",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("column", "Group by column", DIMENSION, page=DATA_PAGE,
              hint="Its values become the sample names, so every tool then works by that "
                   "grouping (a season, a year, a site)"),
        Field("mode", "Sample becomes", SELECT, default="replace", page=DATA_PAGE,
              choices={"replace": "The column's value",
                       "append": "The old name and the column's value"}),
    ],
    _run_regroup, lambda o, c: _need_column(o, "column", "grouping"),
    description="Renames every row's sample from another column — a season, a year, a site — "
                "so that tools that compare or split by sample work on that grouping instead. "
                "The old names are kept in a column of their own. Each category an analysis "
                "needs (end-member splitting wants one per season) is made this way.")


def _run_summary(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    result = sample_summary(rows, sample_col, list(opts.get("columns") or []),
                            opts.get("weight") if opts.get("use_weight") else None)
    # The table itself is what the step's Show output opens, as it is for every step that makes one.
    return [result.rows], _card(opts, "Sample summary", result.summary)


def _validate_summary(opts, context):
    if not opts.get("columns"):
        return "Choose at least one column."
    if opts.get("use_weight") and not opts.get("weight"):
        return "Choose the weight column."
    return None


summary = Node(
    "sample_summary", "Sample summary", "Describe",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("columns", "Columns", DIMENSIONS, numeric_only=True, page=DATA_PAGE),
        Field("use_weight", "Weight by amount", CHECKBOX, page=DATA_PAGE,
              hint="Weight each value by how much water it represents (precipitation depth, "
                   "discharge): the amount-weighted mean of precipitation isotopes"),
        Field("weight", "Amount column", DIMENSION, numeric_only=True, nth=1, page=DATA_PAGE,
              when=lambda o: bool(o.get("use_weight"))),
    ],
    _run_summary, _validate_summary,
    description="One row per sample: how many values, and for each column the mean, standard "
                "deviation and standard error. With an amount column, also the amount-weighted "
                "mean and its standard error (Kirchner & Allen 2020).")


TABLE_NODES = [filter_grains, transform, ratio, convert_oxygen, difference, lipid, trophic,
               temperature, date_part, regroup, summary]
