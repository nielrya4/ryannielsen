"""
Blocks for hydrology that draw or solve through time.

    Time series          Table -> graph       any measurement by date, by sample, with error bars
    Hydrograph           Table -> graph       discharge, with precipitation hanging from the top
    Hydrograph separation Table -> Table      each stream sample split among end members, by date

Dates are read by `sed_stats.dates`; the hydrograph's averaging by `sed_stats.hydro`.
"""
import numpy as np

from workflow_lib import NodeProblem, Port, TABLE

from sed_stats import dates as dt
from sed_stats import emma

from ..hydro_plots import _skipped_note, draw_hydrograph, draw_time_series, read_series
from ..outputs import tabbed
from ..table_ops import number_of
from ..tables import result_table
from .base import (
    CHECKBOX, DATA_PAGE, DIMENSION, DIMENSIONS, Field, NUMBER, Node, OPTIONS_PAGE, SAMPLES, SELECT,
    StepOutput, TEXT, table_of,
)
from ..dataset import sample_names

from antioch.elements import Div, P

NOTE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}

def _date_field():
    return Field("date", "Date column", DIMENSION, page=DATA_PAGE, like=("date", "time"),
                 hint="Dates such as 2021-01-16, 1/16/2021 or 16-Jan-2021; a number is not read as a date")


DAY_FIRST = Field("day_first", "Day before month", CHECKBOX, page=OPTIONS_PAGE,
                  hint="Read 3/4/2021 as 3 April rather than 4 March")
WATER_YEAR = Field("water_year_start", "Water year starts in month", NUMBER, default=10, page=OPTIONS_PAGE,
                   hint="10 (October) in the United States")


def _finish(opts, label, charts, titles, contents):
    body, tabview = tabbed(charts, titles, contents)
    return StepOutput(opts.get("title") or label, body, charts, tabview)


# ----------------------------------------------------------------- time series

TIME_VIEWS = {"date": "By date", "annual": "By day of the water year, each year its own line"}


def _run_time_series(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    dimensions = list(opts["dimensions"])
    error = opts.get("error") if opts.get("use_error") else None
    columns = dimensions + ([error] if error else [])
    series, skipped, examples = read_series(rows, sample_col, opts["date"], columns, opts.get("samples"),
                                            bool(opts.get("day_first")))
    order = sample_names(rows, sample_col)
    charts, titles, contents = [], [], []
    for dimension in dimensions:
        # Points are paired with their error by walking the rows again, so one lacking either is dropped together.
        values, errors = {}, {}
        for sample, entry in series.items():
            if error:
                paired = _pair(rows, sample_col, opts["date"], dimension, error, sample, bool(opts.get("day_first")))
                values[sample] = [(w, v) for w, v, _ in paired]
                errors[sample] = [abs(e) for _, _, e in paired]
            else:
                values[sample] = entry[dimension]
        values = {s: p for s, p in values.items() if p}
        if not values:
            continue
        contents.append(draw_time_series(charts, values, dimension, order, opts, errors if error else None,
                                         _skipped_note(skipped, examples)))
        titles.append(dimension)
    if not contents:
        raise NodeProblem("None of the chosen samples has a value in the chosen columns.")
    return _finish(opts, "Time series", charts, titles, contents)


def _pair(rows, sample_col, date_col, value_col, error_col, sample, day_first):
    out = []
    for row in rows:
        if str(row.get(sample_col, "") or "").strip() != sample:
            continue
        when = dt.parse_date(row.get(date_col), day_first)
        value, err = number_of(row.get(value_col)), number_of(row.get(error_col))
        if when is not None and value is not None and err is not None:
            out.append((when, value, err))
    out.sort(key=lambda p: p[0])
    return out


def _validate_time_series(opts, context):
    if not opts.get("date"):
        return "Choose the date column."
    if not opts.get("dimensions"):
        return "Choose at least one column to plot."
    if opts.get("use_error") and not opts.get("error"):
        return "Choose the error column."
    return None


time_series = Node(
    "time_series", "Time series", "Graph",
    [Port("table", (TABLE,), "Table")], None,
    [
        _date_field(),
        Field("dimensions", "Plot", DIMENSIONS, numeric_only=True, page=DATA_PAGE,
              hint="Each becomes its own plot, with a line per sample"),
        Field("samples", "Samples", SAMPLES, page=DATA_PAGE),
        Field("use_error", "Error bars", CHECKBOX, page=DATA_PAGE),
        Field("error", "Error column", DIMENSION, numeric_only=True, nth=1, page=DATA_PAGE,
              when=lambda o: bool(o.get("use_error")), hint="Drawn as plus and minus this much"),
        Field("view", "Axis", SELECT, choices=TIME_VIEWS, default="date", page=OPTIONS_PAGE,
              hint="By day of the water year lays the years over one another to show the seasonal cycle"),
        Field("lines", "Join the points", CHECKBOX, default=True, page=OPTIONS_PAGE),
        DAY_FIRST, WATER_YEAR,
    ],
    _run_time_series, _validate_time_series,
    description="Plots any measurement against its date, a line per sample, optionally with error "
                "bars — a δ¹⁸O record, a fraction from a hydrograph separation. As a typical "
                "year the years are laid over one another by day of the water year to show the "
                "seasonal cycle.")


# ----------------------------------------------------------- hydrograph/hyetograph

HYDRO_VIEWS = {"timeline": "Through time", "annual": "The typical year (averaged over the years)"}


def _run_hydrograph(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    flow_col = opts.get("flow") if opts.get("use_flow") else None
    rain_col = opts.get("rain") if opts.get("use_rain") else None
    columns = [c for c in (flow_col, rain_col) if c]
    series, skipped, examples = read_series(rows, sample_col, opts["date"], columns, opts.get("samples"),
                                            bool(opts.get("day_first")))
    charts, titles, contents = [], [], []
    for name, entry in series.items():
        flow = entry.get(flow_col, []) if flow_col else []
        rain = entry.get(rain_col, []) if rain_col else []
        if not flow and not rain:
            continue
        contents.append(draw_hydrograph(charts, name, flow, rain, opts, _skipped_note(skipped, examples)))
        titles.append(name)
    if not contents:
        raise NodeProblem("None of the chosen samples has a discharge or precipitation value.")
    return _finish(opts, "Hydrograph", charts, titles, contents)


def _validate_hydrograph(opts, context):
    if not opts.get("date"):
        return "Choose the date column."
    if not (opts.get("use_flow") or opts.get("use_rain")):
        return "Show discharge, precipitation, or both."
    if opts.get("use_flow") and not opts.get("flow"):
        return "Choose the discharge column."
    if opts.get("use_rain") and not opts.get("rain"):
        return "Choose the precipitation column."
    if opts.get("use_flow") and opts.get("use_rain") and opts["flow"] == opts["rain"]:
        return "Discharge and precipitation need different columns."
    return None


hydrograph = Node(
    "hydrograph", "Hydrograph and hyetograph", "Graph",
    [Port("table", (TABLE,), "Table")], None,
    [
        _date_field(),
        Field("samples", "Sites", SAMPLES, page=DATA_PAGE, hint="One chart for each; the sample is the gauge or catchment"),
        Field("use_flow", "Discharge", CHECKBOX, default=True, page=DATA_PAGE),
        Field("flow", "Discharge column", DIMENSION, numeric_only=True, nth=0, page=DATA_PAGE,
              when=lambda o: o.get("use_flow", True)),
        Field("use_rain", "Precipitation", CHECKBOX, default=True, page=DATA_PAGE),
        Field("rain", "Precipitation column", DIMENSION, numeric_only=True, nth=1, page=DATA_PAGE,
              when=lambda o: o.get("use_rain", True),
              hint="An amount in each interval (mm per hour, per day, per month); rows may be at a "
                   "different spacing from the discharge's"),
        Field("view", "Show", SELECT, choices=HYDRO_VIEWS, default="timeline", page=OPTIONS_PAGE),
        Field("smooth", "Smooth discharge over (days)", NUMBER, default=10, page=OPTIONS_PAGE,
              when=lambda o: o.get("view") == "annual", hint="1 for none"),
        Field("rain_at", "A precipitation time marks its interval's", SELECT, default="start",
              choices={"start": "start (hour 05:00 is 05:00–06:00; 2023-09 is September)", "middle": "middle",
                       "end": "end"}, page=OPTIONS_PAGE, when=lambda o: o.get("view", "timeline") == "timeline"),
        Field("flow_units", "Discharge units", TEXT, page=OPTIONS_PAGE, hint="For the axis label, e.g. m³/s"),
        Field("rain_units", "Precipitation units", TEXT, page=OPTIONS_PAGE, hint="For the axis label, e.g. mm"),
        DAY_FIRST, WATER_YEAR,
    ],
    _run_hydrograph, _validate_hydrograph,
    description="Discharge through time with precipitation hanging from the top of the same chart, "
                "in separate bands so they never cross — a stream gauge figure. As the typical "
                "year it averages discharge by day of the water year (smoothed) and precipitation "
                "by month. Rows for discharge and for precipitation can be at different spacings "
                "(daily flow, monthly rain): leave the other column blank.")


# ------------------------------------------------------------ hydrograph separation

SEPARATION_CONSTRAINTS = {"bounded": "Fractions between 0 and 100%",
                          "free": "Sum to 100% only (negative fractions allowed)"}
SEPARATION_SPREADS = {"se": "Standard error of each end member's mean",
                      "sd": "Standard deviation of each end member", "none": "None — solve once"}


def _end_member_stats(rows, sample_col, sample, tracers):
    selected = [r for r in rows if str(r.get(sample_col, "") or "").strip() == sample]
    means, sds, counts = [], [], []
    for tracer in tracers:
        values = np.array([v for v in (number_of(r.get(tracer)) for r in selected) if v is not None])
        if not len(values):
            raise NodeProblem(f"'{sample}' has no values for {tracer}.")
        means.append(float(values.mean()))
        sds.append(float(values.std(ddof=1)) if len(values) > 1 else 0.0)
        counts.append(len(values))
    return means, sds, counts


def _run_separation(inputs, opts):
    rows, sample_col = table_of(inputs, "table")
    tracers, sources = list(opts["tracers"]), list(opts["sources"])
    mixtures = list(opts["mixture"])
    try:
        emma.check_shape(len(sources), len(tracers))
    except ValueError as error:
        raise NodeProblem(str(error)) from None
    stats = [_end_member_stats(rows, sample_col, s, tracers) for s in sources]
    means = np.array([st[0] for st in stats])
    spread_kind = opts.get("spread", "se")
    spread = None
    if spread_kind != "none":
        sds, counts = np.array([st[1] for st in stats]), np.array([st[2] for st in stats])
        spread = sds / (np.sqrt(counts) if spread_kind == "se" else 1.0)
    chosen = []
    unread = 0
    for row in rows:
        if str(row.get(sample_col, "") or "").strip() not in mixtures:
            continue
        values = [number_of(row.get(t)) for t in tracers]
        if any(v is None for v in values):
            unread += 1
            continue
        chosen.append((row, values))
    if not chosen:
        raise NodeProblem("None of the stream samples has a number for every tracer.")
    try:
        fractions, sd, clipped, used = emma.separate(
            means, [v for _, v in chosen], spread, opts.get("constraint", "bounded") == "bounded",
            int(opts.get("trials", 1000)))
    except ValueError as error:
        raise NodeProblem(str(error)) from None
    date_col = opts["date"]
    out = []
    for (row, _), f, k in zip(chosen, fractions, range(len(chosen))):
        for i, source in enumerate(sources):
            line = {sample_col: source, "mixture": str(row.get(sample_col, "")), date_col: row.get(date_col, ""),
                    "fraction_pct": float(100 * f[i]),
                    "sd_pct": float(100 * sd[k][i]) if sd is not None else ""}
            out.append(line)
    notes = [f"{len(chosen):,} stream sample{'s' if len(chosen) != 1 else ''} solved against "
             f"{len(sources)} end members on {len(tracers)} tracer{'s' if len(tracers) != 1 else ''}"
             + (" (exact)." if len(sources) == len(tracers) + 1 else " (least squares).")]
    if unread:
        notes.append(f"{unread:,} stream sample{'s' if unread != 1 else ''} lacked a tracer value and "
                     f"{'were' if unread != 1 else 'was'} left out.")
    if int(clipped.sum()):
        notes.append(f"{int(clipped.sum()):,} fell outside the end members, and were held to 0–100%: "
                     "the end members do not account for them.")
    if sd is not None:
        notes.append(f"Uncertainty: {used:,} Monte Carlo redraws of the end members' means with their "
                     f"{'standard errors' if spread_kind == 'se' else 'standard deviations'}; each stream sample is "
                     "taken as exact.")
    summary = [[s, f"{fractions[:, i].mean() * 100:.1f}", f"{fractions[:, i].min() * 100:.1f}",
                f"{fractions[:, i].max() * 100:.1f}"] for i, s in enumerate(sources)]
    card = StepOutput(opts.get("title") or "Hydrograph separation", Div(
        P(" ".join(notes), style=NOTE),
        result_table(["End member", "Mean %", "Lowest %", "Highest %"], summary),
        P("The table passed on has a row for each end member of each stream sample: "
          "graph its fraction_pct against the date with Time series.", style=NOTE)), [], None)
    return [out], card


def _validate_separation(opts, context):
    if not opts.get("tracers"):
        return "Choose at least one tracer."
    if not opts.get("date"):
        return "Choose the date column."
    mixtures, sources = opts.get("mixture") or [], opts.get("sources") or []
    if not mixtures:
        return "Choose the stream samples to separate."
    if len(sources) < 2:
        return "Choose at least two end-member samples."
    if set(mixtures) & set(sources):
        return "A sample cannot be both an end member and a stream sample."
    if len(sources) > len(opts["tracers"]) + 1:
        return (f"{len(sources)} end members need at least {len(sources) - 1} tracers; "
                f"{len(opts['tracers'])} chosen. Add a tracer, or use fewer end members.")
    return None


separation = Node(
    "hydrograph_separation", "Hydrograph separation", "Model",
    [Port("table", (TABLE,), "Table")], TABLE,
    [
        Field("tracers", "Tracers", DIMENSIONS, numeric_only=True, page=DATA_PAGE,
              hint="Conservative tracers: δ¹⁸O, δ²H, a conductance or a chloride. Needs at least one "
                   "fewer than the end members"),
        Field("mixture", "Stream samples", SAMPLES, unchecked=True, page=DATA_PAGE,
              hint="Every row of these samples is solved separately, giving a fraction through time"),
        Field("sources", "End-member samples", SAMPLES, unchecked=True, page=DATA_PAGE,
              hint="One sample per end member (snow, rain, groundwater); each one's mean is used"),
        _date_field(),
        Field("constraint", "Fractions", SELECT, choices=SEPARATION_CONSTRAINTS, default="bounded",
              page=OPTIONS_PAGE),
        Field("spread", "Uncertainty from", SELECT, choices=SEPARATION_SPREADS, default="se",
              page=OPTIONS_PAGE),
        Field("trials", "Draws", SELECT, choices={"500": "500", "1000": "1,000", "2000": "2,000"},
              default="1000", page=OPTIONS_PAGE, when=lambda o: o.get("spread", "se") != "none"),
    ],
    _run_separation, _validate_separation,
    description="Hydrograph separation: solves each stream sample, by its tracers, for the share of "
                "its water from each end member, with the same mass-balance solution and Monte Carlo "
                "uncertainty as End-member mixing but for every sample through time. The same "
                "caveats hold: conservative tracers, constant end members, and with δ¹⁸O and δ²H "
                "alone, at most two. Graph the fractions with Time series.")


HYDRO_NODES = [time_series, hydrograph, separation]
