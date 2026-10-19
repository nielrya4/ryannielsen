"""
The Ternary tool's output: three components of a whole, one point per grain.

The three apex dimensions are chosen in the wizard rather than taken from the
dimension checklist, because on a triangle the order matters — which component
sits at the top is part of the diagram's meaning, and a checklist cannot say.
"""
from antioch.elements import Div, P

from plot_lib import (
    categorical_color, series_symbol, ternary_layout, ternary_trace,
)
from sed_stats import ternary

from .config import TERNARY_TOTAL
from .dataset import sample_names
from .plots import make_plot
from .tables import result_table

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}
NOTE_STYLE = {"color": "#6c757d"}

PLAIN_COLOR = "#4a5568"
CENTROID_COLOR = "#1a1a1a"


def build_ternary(charts, rows, sample_col, dimension, opts):
    """
    `dimension` is ignored — the three apexes come from the options panel.

    The tool runs with use_dimensions off, so there is one output rather than
    a tab per dimension.
    """
    apexes = [opts.get("apex_a"), opts.get("apex_b"), opts.get("apex_c")]
    if not all(apexes):
        return P("Choose all three apex dimensions.", style=NOTE_STYLE)
    if len(set(apexes)) < 3:
        return P("The three apexes must be different dimensions.",
                 style=NOTE_STYLE)

    grouped = _components_by_sample(rows, sample_col, apexes,
                                    opts.get("samples"))
    if not grouped:
        return P("No grains have a value for all three apex dimensions.",
                 style=NOTE_STYLE)

    order = {name: index
             for index, name in enumerate(sample_names(rows, sample_col))}
    closed = {sample: ternary.close(*parts, total=TERNARY_TOTAL)
              for sample, parts in grouped.items()}
    closed = {sample: data for sample, data in closed.items() if len(data)}
    if not closed:
        return P("Every grain had a zero or negative total across the three "
                 "components, so none can be placed on the triangle.",
                 style=NOTE_STYLE)

    traces = []
    for sample, data in closed.items():
        index = order.get(sample, 0)
        color, symbol = ((categorical_color(index), series_symbol(index))
                         if opts.get("color_by_sample", True)
                         else (PLAIN_COLOR, "circle"))
        traces.append(ternary_trace(
            data.a, data.b, data.c, sample,
            color=color, symbol=symbol,
            size=opts.get("point_size", 7),
            apex_names=apexes,
        ))

    if opts.get("show_centroids"):
        traces.extend(_centroid_traces(closed, apexes))

    title = f"{apexes[0]} – {apexes[1]} – {apexes[2]}"
    wrapper = Div(
        _caption(closed, apexes),
        Div(make_plot(
            charts, traces, title, apexes[1], apexes[2],
            height=560, show_legend=len(traces) > 1,
            filename=f"{'_'.join(apexes)}_ternary",
            extra_layout=ternary_layout(apexes, total=TERNARY_TOTAL),
        ).element),
    )
    if opts.get("show_centroids"):
        wrapper.add(_centroid_table(closed, apexes))
    return wrapper


def _components_by_sample(rows, sample_col, apexes, only_samples):
    """
    The three apex values per grain, grouped by sample.

    A grain missing any one component has no position on the triangle, so it
    is left out rather than treated as a zero — absent and zero mean different
    things in a composition.
    """
    grouped = {}
    for row in rows:
        sample = str(row.get(sample_col, "") or "").strip()
        if not sample:
            continue
        if only_samples is not None and sample not in only_samples:
            continue
        values = []
        for apex in apexes:
            raw = row.get(apex, "")
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
        entry = grouped.setdefault(sample, ([], [], []))
        for slot, value in zip(entry, values):
            slot.append(value)
    return grouped


def _caption(closed, apexes):
    """State the plot's size, and anything that had to be done to the data."""
    plotted = sum(len(data) for data in closed.values())
    dropped = sum(data.dropped_total for data in closed.values())

    text = (f"{plotted:,} grains across {len(closed)} "
            f"sample{'s' if len(closed) != 1 else ''}, "
            f"{apexes[0]} at the top with {apexes[1]} and {apexes[2]} "
            f"along the base.")

    if any(data.needed_closure for data in closed.values()):
        lows = [data.closure_range[0] for data in closed.values()]
        highs = [data.closure_range[1] for data in closed.values()]
        text += (f" Raw totals ran {min(lows):.3g}–{max(highs):.3g}, so each "
                 f"grain was scaled to {TERNARY_TOTAL:g}.")
    else:
        text += f" Totals were already {TERNARY_TOTAL:g}."

    caption = Div(P(text, style=CAPTION_STYLE))
    if dropped:
        caption.add(P(f"{dropped:,} grain{'s' if dropped != 1 else ''} left out "
                      f"for a zero or negative total.", style=NOTE_STYLE))
    return caption


def _centroid_traces(closed, apexes):
    """A ringed marker per sample at its mean composition."""
    traces = []
    for sample, data in closed.items():
        a, b, c = ternary.centroid(data)
        trace = ternary_trace([a], [b], [c], f"{sample} mean",
                              color=CENTROID_COLOR, symbol="star", size=14,
                              opacity=1.0, apex_names=apexes)
        trace["marker"]["line"] = {"width": 1.4, "color": "#ffffff"}
        trace["showlegend"] = False
        traces.append(trace)
    return traces


def _centroid_table(closed, apexes):
    body = []
    for sample, data in closed.items():
        a, b, c = ternary.centroid(data)
        body.append([sample, f"{a:.1f}", f"{b:.1f}", f"{c:.1f}", f"{len(data):,}"])

    return Div(
        P("Mean composition per sample",
          style={**CAPTION_STYLE, "margin": "16px 0 6px 0"}),
        result_table(["Sample", *apexes, "n"], body),
    )
