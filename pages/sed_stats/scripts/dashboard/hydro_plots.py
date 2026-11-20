"""
Plots through time: a series of any measurement by date, and the hydrograph with its
hyetograph.

The hydrograph and hyetograph share one time axis in two bands, as in a stream-gauge figure:
discharge fills the bottom, precipitation hangs from the top on an inverted axis, so the bars of
rain and the flow that follows them never cross.
"""
from datetime import timedelta

from antioch.elements import Div, P

from plot_lib import categorical_color, series_symbol
from sed_stats import dates as dt
from sed_stats import hydro
from workflow_lib import NodeProblem

from .plots import make_plot
from .table_ops import number_of

CAPTION = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
FLOW_COLOR = "#1f6fb2"
RAIN_COLOR = "#7aa6d6"
RAIN_BAND = 0.36                  # the top share of the chart that rain hangs in
GAP = 0.06


def _iso(when):
    return when.strftime("%Y-%m-%d %H:%M:%S")


def _sample(row, sample_col):
    return str(row.get(sample_col, "") or "").strip()


def read_series(rows, sample_col, date_col, columns, samples=None, day_first=False):
    """
    {sample: {column: [(datetime, value)]}} in date order, for the rows whose date can be read
    and whose value is a number; and how many rows were skipped because the date could not be.

    Raises:
        NodeProblem: when no row has a readable date
    """
    chosen = set(samples) if samples is not None else None
    out, skipped, readable = {}, 0, 0
    examples = []
    for row in rows:
        sample = _sample(row, sample_col)
        if not sample or (chosen is not None and sample not in chosen):
            continue
        when = dt.parse_date(row.get(date_col), day_first)
        if when is None:
            skipped += 1
            raw = row.get(date_col)
            if raw not in ("", None) and len(examples) < 2 and str(raw) not in examples:
                examples.append(str(raw))
            continue
        readable += 1
        entry = out.setdefault(sample, {c: [] for c in columns})
        for column in columns:
            value = number_of(row.get(column))
            if value is not None:
                entry[column].append((when, value))
    if not readable:
        hint = f" (for example '{examples[0]}')" if examples else ""
        raise NodeProblem(f"No row has a date that can be read in '{date_col}'{hint}.")
    for entry in out.values():
        for column in columns:
            entry[column].sort(key=lambda p: p[0])
    return out, skipped, examples


def _skipped_note(skipped, examples):
    if not skipped:
        return ""
    return (f"{skipped:,} row{'s' if skipped != 1 else ''} had no readable date and "
            f"{'were' if skipped != 1 else 'was'} left out"
            + (f" (for example '{examples[0]}')." if examples else "."))


# ----------------------------------------------------------------- time series

def draw_time_series(charts, series, dimension, order, opts, errors=None, note=""):
    """
    One chart of `dimension` through time, a trace per sample.

    Args:
        series: {sample: [(datetime, value)]}; errors: {sample: [error]} aligned with it
        order: the samples in spreadsheet order, so each keeps its colour and marker
        opts: view ("date" or "annual": the days of the water year, each year its own trace),
            lines (join the points), water_year_start
    """
    start = int(opts.get("water_year_start") or 10)
    annual = opts.get("view", "date") == "annual"
    lines = opts.get("lines", True)
    traces = []
    for sample, points in series.items():
        index = order.index(sample) if sample in order else 0
        color = categorical_color(index)
        errs = (errors or {}).get(sample)
        if not annual:
            trace = {"type": "scatter", "mode": "lines+markers" if lines else "markers",
                     "x": [_iso(w) for w, _ in points], "y": [v for _, v in points], "name": sample,
                     "line": {"color": color, "width": 1.5},
                     "marker": {"color": color, "size": 6, "symbol": series_symbol(index)}}
            if errs:
                trace["error_y"] = {"type": "data", "array": errs, "visible": True, "color": color,
                                    "thickness": 1, "width": 3}
            traces.append(trace)
            continue
        by_year = {}
        for k, (when, value) in enumerate(points):
            day = dt.reference_day(when.month, when.day, start)
            if day is None:
                continue
            by_year.setdefault(dt.water_year(when, start), []).append(
                (day, value, errs[k] if errs else None))
        years = sorted(by_year)
        for y, year in enumerate(years):
            data = sorted(by_year[year])
            trace = {"type": "scatter", "mode": "lines+markers" if lines else "markers",
                     "x": [d for d, _, _ in data], "y": [v for _, v, _ in data],
                     "name": f"{sample} · WY{year}" if len(series) > 1 or len(years) > 1 else sample,
                     "line": {"color": color, "width": 1.2, "dash": ["solid", "dash", "dot", "dashdot"][y % 4]},
                     "marker": {"color": color, "size": 6, "symbol": series_symbol(y)}}
            if errs:
                trace["error_y"] = {"type": "data", "array": [e for _, _, e in data], "visible": True,
                                    "color": color, "thickness": 1, "width": 3}
            traces.append(trace)
    if not traces:
        raise NodeProblem(f"No sample has a value for {dimension}.")
    x_axis = {"title": {"text": "Date" if not annual else f"Day of the water year (starting {dt.MONTH_NAMES[start - 1]})"}}
    if annual:
        ticks = dt.month_tick_positions(start)
        x_axis.update({"tickmode": "array", "tickvals": [p for p, _ in ticks],
                       "ticktext": [n for _, n in ticks], "range": [1, 365]})
    else:
        x_axis["type"] = "date"
    wrapper = Div()
    if note:
        wrapper.add(P(note, style=CAPTION))
    wrapper.add(Div(make_plot(
        charts, traces, f"{dimension} through time" if not annual else f"{dimension} through the year",
        x_axis["title"]["text"], dimension, height=480, show_legend=len(traces) > 1,
        filename=f"{dimension}_time_series".replace(" ", "_"),
        extra_layout={"xaxis": x_axis, "yaxis": {"title": {"text": dimension}, "rangemode": "normal"}}).element))
    return wrapper


# -------------------------------------------------------- hydrograph / hyetograph

def draw_hydrograph(charts, name, flow, rain, opts, note=""):
    """
    One site's hydrograph and hyetograph.

    Args:
        flow, rain: [(datetime, value)] or empty
        opts: view ("timeline" or "annual": the typical year), rain_at, smooth, flow_units,
            rain_units, water_year_start
    """
    start = int(opts.get("water_year_start") or 10)
    annual = opts.get("view", "timeline") == "annual"
    flow_label = f"Discharge ({opts['flow_units']})" if opts.get("flow_units") else "Discharge"
    rain_label = f"Precipitation ({opts['rain_units']})" if opts.get("rain_units") else "Precipitation"
    traces, rain_top = [], None
    both = bool(flow) and bool(rain)

    if annual:
        if flow:
            days, values = hydro.annual_flow(flow, int(opts.get("smooth") or 1), start)
            traces.append({"type": "scatter", "mode": "lines", "x": days, "y": values,
                           "name": "Typical daily discharge", "fill": "tozeroy",
                           "line": {"color": FLOW_COLOR, "width": 2}, "fillcolor": "rgba(31,111,178,0.25)"})
        if rain:
            totals = hydro.monthly_mean_totals(rain, start)
            xs, ys, widths = [], [], []
            for month, (total, _) in sorted(totals.items()):
                first, length = dt.month_span(month, start)
                xs.append(first - 1 + length / 2)
                ys.append(total)
                widths.append(length * 0.92)
            rain_top = max(ys) if ys else None
            traces.append({"type": "bar", "x": xs, "y": ys, "width": widths, "name": "Typical monthly precipitation",
                           "marker": {"color": RAIN_COLOR, "line": {"color": "#355c8a", "width": 1}}, "yaxis": "y2"})
        ticks = dt.month_tick_positions(start)
        x_axis = {"title": {"text": "Month of the water year"}, "tickmode": "array",
                  "tickvals": [p - 1 + 15 for p, _ in ticks], "ticktext": [n for _, n in ticks], "range": [0, 365]}
    else:
        if flow:
            traces.append({"type": "scatter", "mode": "lines", "x": [_iso(w) for w, _ in flow],
                           "y": [v for _, v in flow], "name": "Discharge", "fill": "tozeroy",
                           "line": {"color": FLOW_COLOR, "width": 1.6}, "fillcolor": "rgba(31,111,178,0.25)"})
        if rain:
            centres, width = hydro.bar_edges([w for w, _ in rain], opts.get("rain_at", "start"))
            rain_top = max(v for _, v in rain)
            traces.append({"type": "bar", "x": [_iso(c) for c in centres], "y": [v for _, v in rain],
                           "width": [width.total_seconds() * 1000 * 0.92] * len(rain), "name": "Precipitation",
                           "marker": {"color": RAIN_COLOR, "line": {"color": "#355c8a", "width": 0.6}}, "yaxis": "y2"})
        x_axis = {"title": {"text": "Date"}, "type": "date"}
    if not traces:
        raise NodeProblem(f"'{name}' has no discharge or precipitation values to draw.")

    layout = {"xaxis": x_axis, "barmode": "overlay"}
    if both:
        layout["yaxis"] = {"title": {"text": flow_label}, "domain": [0, 1 - RAIN_BAND - GAP],
                           "rangemode": "tozero"}
        layout["yaxis2"] = {"title": {"text": rain_label}, "domain": [1 - RAIN_BAND, 1], "anchor": "x",
                            "range": [rain_top * 1.1 if rain_top else 1, 0]}
    elif flow:
        layout["yaxis"] = {"title": {"text": flow_label}, "rangemode": "tozero"}
    else:
        layout["yaxis2"] = {"title": {"text": rain_label}, "anchor": "x", "domain": [0, 1],
                            "range": [rain_top * 1.1 if rain_top else 1, 0]}
        layout["yaxis"] = {"visible": False}
    wrapper = Div()
    parts = [note] if note else []
    if rain:
        parts.append(f"Precipitation recorded: {sum(v for _, v in rain):,.4g}"
                     + (f" {opts['rain_units']}" if opts.get("rain_units") else "") + f" over {len(rain):,} values.")
    if flow:
        parts.append(f"Mean discharge {sum(v for _, v in flow) / len(flow):,.4g}"
                     + (f" {opts['flow_units']}" if opts.get("flow_units") else "") + f" over {len(flow):,} values.")
    if parts:
        wrapper.add(P(" ".join(parts), style=CAPTION))
    wrapper.add(Div(make_plot(
        charts, traces, f"{name}: " + ("typical year" if annual else "hydrograph and hyetograph"),
        x_axis["title"]["text"], flow_label if flow else rain_label, height=520, show_legend=True,
        filename=f"{name}_hydrograph".replace(" ", "_"), extra_layout=layout).element))
    return wrapper
