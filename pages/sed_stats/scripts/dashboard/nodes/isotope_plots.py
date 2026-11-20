"""
Two graphs for isotope records.

    Isotope boxplots by period   Table -> graph   a box for each month, year, season… of a record,
                                                  per sample, to compare the spread of values through time
    Isotope excursions           Table -> graph   a profile against depth, age or year, with its
                                                  baseline and the stretches that depart from it

Dates are read by `sed_stats.dates`, periods by `sed_stats.periods`, excursions by
`sed_stats.excursions`.
"""
from antioch.elements import Div, P

from workflow_lib import NodeProblem, Port, TABLE

from plot_lib import categorical_color, series_symbol

from sed_stats import dates as dt
from sed_stats import excursions as ex
from sed_stats import periods as pr

from ..dataset import sample_names
from ..hydro_plots import _skipped_note, read_series
from ..plots import make_plot
from ..table_ops import number_of
from ..tables import result_table
from .base import (
    CHECKBOX, DATA_PAGE, DIMENSION, DIMENSIONS, Field, NUMBER, Node, OPTIONS_PAGE, SAMPLES,
    SELECT, table_of,
)
from .hydro import DAY_FIRST, WATER_YEAR, _date_field, _finish

NOTE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
FEW = 5                    # a box on fewer values than this says little


# ------------------------------------------------------------------ boxplots by period

def _run_boxplot(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    dimensions = list(opts["dimensions"])
    period = opts.get("period", "month_of_year")
    start = int(opts.get("water_year_start") or 10)
    series, skipped, examples = read_series(rows, sample_col, opts["date"], dimensions,
                                            opts.get("samples"), bool(opts.get("day_first")))
    order = sample_names(rows, sample_col)
    charts, titles, contents = [], [], []
    for dimension in dimensions:
        keyed = {}                       # sort key -> label, over every sample
        by_sample = {}
        for sample, entry in series.items():
            labels, values = [], []
            for when, value in entry[dimension]:
                key, label = pr.period_of(when, period, start)
                keyed[key] = label
                labels.append(label)
                values.append(value)
            if values:
                by_sample[sample] = (labels, values)
        if not by_sample:
            continue
        ordered = [keyed[k] for k in sorted(keyed)]
        traces, thin = [], 0
        for sample, (labels, values) in by_sample.items():
            index = order.index(sample) if sample in order else 0
            color = categorical_color(index)
            traces.append({"type": "box", "x": labels, "y": values, "name": sample,
                           "marker": {"color": color, "size": 4},
                           "line": {"width": 1.5},
                           "boxpoints": "all" if opts.get("show_points") else "outliers",
                           "jitter": 0.5, "pointpos": 0, "boxmean": bool(opts.get("show_mean"))})
            counts = {}
            for label in labels:
                counts[label] = counts.get(label, 0) + 1
            thin += sum(1 for n in counts.values() if n < FEW)
        note = (f"{dimension} by {pr.PERIODS[period].split(' (')[0].lower()}: the box is the middle half of "
                "the values, the line the median, the whiskers the range within 1.5 box-lengths, and dots "
                "beyond them outliers.")
        if thin:
            note += (f" {thin} box{'es' if thin != 1 else ''} rest{'s' if thin == 1 else ''} on fewer than "
                     f"{FEW} values and say little.")
        skip = _skipped_note(skipped, examples)
        wrapper = Div(P(" ".join(filter(None, [note, skip])), style=NOTE))
        wrapper.add(Div(make_plot(
            charts, traces, f"{dimension} by period", pr.PERIODS[period].split(" (")[0], dimension,
            height=480, show_legend=len(by_sample) > 1, filename=f"{dimension}_boxplot",
            extra_layout={"boxmode": "group",
                          "xaxis": {"title": {"text": pr.PERIODS[period].split(" (")[0]}, "type": "category",
                                    "categoryorder": "array", "categoryarray": ordered},
                          "yaxis": {"title": {"text": dimension}, "rangemode": "normal"}}).element))
        contents.append(wrapper)
        titles.append(dimension)
    if not contents:
        raise NodeProblem("None of the chosen samples has a value in the chosen columns.")
    return _finish(opts, "Isotope boxplots", charts, titles, contents)


def _validate_boxplot(opts, context):
    if not opts.get("date"):
        return "Choose the date column."
    if not opts.get("dimensions"):
        return "Choose at least one column to draw."
    return None


period_boxplot = Node(
    "period_boxplot", "Isotope boxplots by period", "Graph",
    [Port("table", (TABLE,), "Table")], None,
    [
        _date_field(),
        Field("dimensions", "Plot", DIMENSIONS, numeric_only=True, page=DATA_PAGE,
              hint="Each becomes its own plot; δ¹⁸O, δ²H, d-excess, anything numeric"),
        Field("samples", "Samples", SAMPLES, page=DATA_PAGE,
              hint="A box of each sample side by side in every period"),
        Field("period", "One box for each", SELECT, choices=pr.PERIODS, default="month_of_year",
              page=OPTIONS_PAGE,
              hint="Month of the year pools every January, every February…, which shows the seasonal "
                   "cycle; Each month keeps the years apart"),
        Field("show_points", "Show every value", CHECKBOX, page=OPTIONS_PAGE,
              hint="Draw each measurement beside its box rather than only the outliers"),
        Field("show_mean", "Mark the mean", CHECKBOX, page=OPTIONS_PAGE),
        DAY_FIRST,
        Field("water_year_start", "Water year starts in month", NUMBER, default=10, page=OPTIONS_PAGE,
              when=lambda o: o.get("period") == "water_year"),
    ],
    _run_boxplot, _validate_boxplot,
    description="A boxplot of any measurement for each month, season, year or water year of a dated "
                "record, with a box per sample in each. Shows the spread as well as the typical "
                "value, so a seasonal swing in δ¹⁸O, or a year that is unlike the others, is plain.")


# ------------------------------------------------------------------ profile and excursions

ORIENTATIONS = {"depth": "Depth down the page (value across)", "across": "Position along the bottom (value up)"}


def _fmt(x):
    return f"{x:,.4g}"


def _when(jd):
    """A Julian date as the text of the date it is: the day, with the time if it has one."""
    moment = dt.from_julian_date(jd)
    if moment.hour or moment.minute or moment.second:
        return moment.strftime("%Y-%m-%d %H:%M")
    return moment.strftime("%Y-%m-%d")


def _profile(charts, sample, dimension, position, found, opts, labels, dated=False):
    """One chart (and a table of the excursions) of a record against its position."""
    depth = opts.get("orientation", "depth") == "depth"
    k = float(opts.get("threshold") or 2)
    val, base, scale = found["value"], found["baseline"], found["scale"]
    # A date is worked on as a Julian date but drawn, and listed, as the date it is
    pos = [_when(p) for p in found["position"]] if dated else found["position"]
    place = _when if dated else _fmt
    upper = [b + k * scale for b in base]
    lower = [b - k * scale for b in base]

    def xy(position_values, values):
        return (values, position_values) if depth else (position_values, values)

    traces = []
    lo_x, lo_y = xy(pos, lower)
    hi_x, hi_y = xy(pos, upper)
    traces.append({"type": "scatter", "mode": "lines", "x": lo_x, "y": lo_y, "line": {"width": 0},
                   "hoverinfo": "skip", "showlegend": False})
    traces.append({"type": "scatter", "mode": "lines", "x": hi_x, "y": hi_y, "line": {"width": 0},
                   "fill": "tonextx" if depth else "tonexty", "fillcolor": "rgba(100,120,140,0.18)",
                   "name": f"Baseline ± {k:g} SD", "hoverinfo": "skip"})
    bx, by = xy(pos, base)
    traces.append({"type": "scatter", "mode": "lines", "x": bx, "y": by, "name": "Baseline",
                   "line": {"color": "#555", "width": 1.5, "dash": "dash"}, "hoverinfo": "skip"})
    sx, sy = xy(pos, val)
    traces.append({"type": "scatter", "mode": "lines+markers", "x": sx, "y": sy, "name": sample,
                   "line": {"color": "#1f6fb2", "width": 1.5},
                   "marker": {"color": "#1f6fb2", "size": 5}})
    flagged = [i for i, f in enumerate(found["flagged"]) if f]
    if flagged:
        fx, fy = xy([pos[i] for i in flagged], [val[i] for i in flagged])
        traces.append({"type": "scatter", "mode": "markers", "x": fx, "y": fy,
                       "name": f"Beyond {k:g} SD",
                       "marker": {"color": "#d93a4f", "size": 9, "symbol": "diamond",
                                  "line": {"color": "#fff", "width": 1}}})
    layout = {"xaxis": {"title": {"text": dimension if depth else position}, "rangemode": "normal"},
              "yaxis": {"title": {"text": position if depth else dimension}, "rangemode": "normal"}}
    if dated:
        layout["yaxis" if depth else "xaxis"]["type"] = "date"
        layout["yaxis" if depth else "xaxis"].pop("rangemode")
    if depth:
        layout["yaxis"]["autorange"] = "reversed"
    title = f"{dimension} against {position}" + (f" — {sample}" if sample else "")
    wrapper = Div()
    runs = found["runs"]
    note = (f"{len(val):,} points; baseline {ex.BASELINES[opts.get('baseline', 'median')].lower()}, scatter "
            f"{_fmt(scale)} (robust standard deviation); {len(flagged)} point{'s' if len(flagged) != 1 else ''} "
            f"beyond {k:g}×.")
    wrapper.add(P(note, style=NOTE))
    wrapper.add(Div(make_plot(charts, traces, title, layout["xaxis"]["title"]["text"],
                              layout["yaxis"]["title"]["text"], height=520,
                              show_legend=True, filename=f"{dimension}_{sample}_profile".replace(" ", "_"),
                              extra_layout=layout).element))
    if runs:
        wrapper.add(result_table(
            [f"From {position}", f"To {position}", "Points", "Direction", f"Peak {dimension}", "Peak (SD from baseline)"],
            [[place(r["start"]), place(r["end"]), str(r["n"]), "below" if r["sign"] < 0 else "above",
              _fmt(r["peak_value"]), f"{r['peak_z']:+.1f}"] for r in runs]))
    else:
        wrapper.add(P("No excursion: no stretch of the record is beyond the threshold"
                      + (f" for at least {int(opts.get('min_run') or 1)} points." if int(opts.get("min_run") or 1) > 1 else "."),
                      style=NOTE))
    return wrapper


def _run_profile(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    position = opts["position"]
    dimensions = list(opts["dimensions"])
    chosen = opts.get("samples")
    order = sample_names(rows, sample_col)
    day_first = bool(opts.get("day_first"))
    # A column that is not numbers is read as dates, as Julian dates, so the records can be ordered and
    # a window counted; a row whose date cannot be read is left out, and counted
    dated = (not any(number_of(r.get(position)) is not None for r in rows)
             and any(str(r.get(position, "") or "").strip() for r in rows))
    unread = []

    def where(raw):
        if not dated:
            return number_of(raw)
        when = dt.parse_date(raw, day_first)
        if when is None:
            if str(raw if raw is not None else "").strip() and str(raw) not in unread:
                unread.append(str(raw))
            return None
        return dt.julian_date(when)

    charts, titles, contents = [], [], []
    short = []
    for sample in (chosen if chosen is not None else order):
        for dimension in dimensions:
            xs, ys = [], []
            for row in rows:
                if str(row.get(sample_col, "") or "").strip() != sample:
                    continue
                p, v = where(row.get(position)), number_of(row.get(dimension))
                if p is not None and v is not None:
                    xs.append(p)
                    ys.append(v)
            if len(xs) < 5:
                short.append(f"{sample} ({len(xs)})")
                continue
            try:
                found = ex.find(xs, ys, k=float(opts.get("threshold") or 2),
                                baseline=opts.get("baseline", "median"),
                                window=int(opts.get("window") or 11), min_run=int(opts.get("min_run") or 1))
            except ValueError as error:
                raise NodeProblem(str(error)) from None
            contents.append(_profile(charts, sample if len(chosen or order) > 1 else "", dimension, position,
                                     found, opts, order, dated))
            titles.append(" · ".join(filter(None, [sample if len(chosen or order) > 1 else "",
                                                   dimension if (len(dimensions) > 1 or len(chosen or order) == 1) else ""]))
                          or dimension)
    if not contents:
        raise NodeProblem("No chosen sample has five or more points with both a position and a value"
                          + (f" (short: {', '.join(short)})" if short else "")
                          + (f"; '{position}' holds values that are not dates, such as '{unread[0]}'" if unread else "")
                          + ".")
    if short:
        contents[0].add(P(f"Left out for having fewer than five points: {', '.join(short)}.", style=NOTE))
    if unread:
        contents[0].add(P(f"{len(unread):,} different value{'s' if len(unread) != 1 else ''} in '{position}' "
                          f"could not be read as {'a date' if len(unread) == 1 else 'dates'} and "
                          f"{'was' if len(unread) == 1 else 'were'} left out (for example '{unread[0]}'); "
                          "the order of day and month can be switched.", style=NOTE))
    return _finish(opts, "Isotope excursions", charts, titles, contents)


def _validate_profile(opts, context):
    if not opts.get("position"):
        return "Choose the depth, age, year or date column."
    if not opts.get("dimensions"):
        return "Choose at least one column to draw."
    if opts["position"] in opts["dimensions"]:
        return "The position column cannot also be plotted."
    if opts.get("threshold") is not None and float(opts["threshold"]) <= 0:
        return "The threshold must be above zero."
    return None


isotope_profile = Node(
    "isotope_profile", "Isotope excursions", "Graph",
    [Port("table", (TABLE,), "Table")], None,
    [
        Field("position", "Depth, age, year or date column", DIMENSION, numeric_only=True, dates=True,
              page=DATA_PAGE, like=("depth", "age", "year", "date", "time"),
              hint="What the record is ordered by: depth in a core, age, year, or a column of dates "
                   "(read as Julian dates, and drawn on a date axis)"),
        Field("dimensions", "Plot", DIMENSIONS, numeric_only=True, nth=1, page=DATA_PAGE,
              hint="Each isotope becomes its own chart"),
        Field("samples", "Samples", SAMPLES, page=DATA_PAGE, hint="A chart for each, with its own baseline"),
        Field("orientation", "Draw", SELECT, choices=ORIENTATIONS, default="depth", page=OPTIONS_PAGE,
              hint="A profile with depth down the page is the usual figure for a core; along the bottom "
                   "suits a record through time"),
        Field("baseline", "Baseline", SELECT, choices=ex.BASELINES, default="median", page=OPTIONS_PAGE,
              hint="The level the record is judged against. A running median follows a drift; a "
                   "whole-record baseline treats any trend as scatter and then finds nothing"),
        Field("window", "Running median over (points)", NUMBER, default=11, page=OPTIONS_PAGE,
              when=lambda o: o.get("baseline") == "rolling",
              hint="Longer than an excursion is thick, or the baseline follows it"),
        Field("threshold", "Excursion beyond (SD)", NUMBER, default=2, page=OPTIONS_PAGE,
              hint="How many robust standard deviations from the baseline: 2 flags about one point in "
                   "twenty of pure noise, 3 about one in 370"),
        Field("min_run", "Fewest points in an excursion", NUMBER, default=1, page=OPTIONS_PAGE,
              hint="Consecutive points on the same side of the baseline; 3 or more ignores single spikes"),
        DAY_FIRST,
    ],
    _run_profile, _validate_profile,
    description="Plots an isotope record against depth, age or year with its baseline and a band of "
                "the chosen width about it, marks the points beyond the band, and lists each "
                "excursion — a stretch of consecutive points on one side — with where it starts, "
                "ends and peaks. The baseline is the whole record's median or mean, or a running "
                "median for a record that drifts; the scatter is a robust standard deviation.")


ISOTOPE_PLOT_NODES = [period_boxplot, isotope_profile]
