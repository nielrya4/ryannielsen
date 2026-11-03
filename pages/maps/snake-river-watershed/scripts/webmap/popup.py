"""The stats a watershed (or the sink sample) shows when clicked, built as Antioch elements for a
Leaflet popup: a header, then only the stats behind the map's current coloring."""
from antioch.elements import Div, H3, Span

from . import config as c
from .data import MODEL, POLYMERS, PROPS, SINK
from .plotly_chart import PlotlyChart


def _bar(label, value, scale, color, text):
    """One labelled bar."""
    track = Div(Div(style={**c.BAR_FILL_STYLE, "width": f"{_percent(value, scale)}%",
                           "background-color": color}),
                style=c.BAR_TRACK_STYLE)
    return Div(Span(label), track, Span(text, style=c.VALUE_STYLE), style=c.BAR_ROW_STYLE)


def _percent(value, scale):
    return 0 if scale <= 0 else min(100.0, 100 * value / scale)


def _heading(text):
    return Div(text, style=c.POPUP_HEADING_STYLE)


def _shares(values, fmt):
    return [_bar(c.SHARE_LABELS[k], values[k], 1, c.SHARE_COLORS[k], fmt(values[k]))
            for k in c.SHARE_LABELS]


def _stats(rows):
    grid = Div(style=c.STAT_GRID_STYLE)
    for label, value in rows:
        grid.add(Span(label), Span(value, style=c.VALUE_STYLE))
    return grid


def _bar_chart(trace, charts):
    """A Plotly bar chart of one trace, its y axis in percent, with hover values but fixed axes
    (no zooming); added to charts so the popup can draw and free it."""
    chart = PlotlyChart(
        traces=[{"type": "bar", **trace}],
        layout={"bargap": 0.25, "showlegend": False, "dragmode": False,
                "font": {"family": c.FONT, "size": 11, "color": c.POPUP_INK},
                "yaxis": {"tickformat": ".0%", "gridcolor": c.TRACK, "zeroline": False,
                          "fixedrange": True},
                "xaxis": {"tickangle": -45, "fixedrange": True},
                "margin": {"l": 40, "r": 8, "t": 8, "b": 58}},
        config={"scrollZoom": False, "doubleClick": False},
        width=300, height=210)
    charts.append(chart)
    return chart.element


def _polymers(p, charts):
    """This sample's polymer mix."""
    return [_heading("Polymer mix (share of particles)"), _bar_chart(
        {"x": POLYMERS, "y": [p["polymers"][q] for q in POLYMERS],
         "marker": {"color": p["color"]}, "hovertemplate": "%{x}: %{y:.1%}<extra></extra>"},
        charts)]


def _model_mix(charts):
    """The sink's modelled mix: each source's contribution, whiskers its bootstrap range."""
    sources = sorted((p for p in PROPS.values() if "contribution" in p),
                     key=lambda p: -p["contribution"])
    best = [p["contribution"] / 100 for p in sources]
    lo, hi = ([p["contribution_range"][i] / 100 for p in sources] for i in (0, 1))
    return [_heading("Modelled sources of this sample"), _bar_chart(
        {"x": [p["name"].split(" (")[0].replace(" River", "") for p in sources], "y": best,
         "marker": {"color": [p["dot_color"] for p in sources]},  # as the sample dots
         "error_y": {"type": "data", "symmetric": False, "thickness": 1.2, "width": 4,
                     "color": c.POPUP_MUTED, "array": [h - b for h, b in zip(hi, best)],
                     "arrayminus": [b - l for b, l in zip(best, lo)]},
         "customdata": [[l, h] for l, h in zip(lo, hi)],
         "hovertemplate": "%{x}: %{y:.0%} (bootstrap %{customdata[0]:.0%}–"
                          "%{customdata[1]:.0%})<extra></extra>"}, charts),
        Div("Optimised best fit of the polymer mixture model; whiskers: bootstrap 16–84%.",
            style=c.META_STYLE)]


def _source_likeness():
    """How alike each source alone is to the sink, beside the modelled mix's fit (above)."""
    sources = sorted((p for p in PROPS.values() if "likeness" in p), key=lambda p: -p["likeness"])
    return [_heading("Each source alone vs. this sample"),
            _stats([(p["name"], f"{p['likeness']:.3f}") for p in sources])]


def _not_for_sink(what):
    return lambda p, charts: [_heading(what), Div(
        "Computed for each source catchment, not for the sink, which receives all six.",
        style=c.META_STYLE)]


def _contribution(p):
    lo, hi = p["contribution_range"]
    return [_heading("Contribution to the sink"),
            Div(Span(f"{p['contribution']:.0f}%", style=c.BIG_STYLE),
                Span(f"bootstrap range {lo:.0f}–{hi:.0f}%", style=c.RANGE_STYLE))]


def _connectivity(p):
    return [_heading("Stream connectivity"),
            _stats([("Connected on sampling day", f"{p['connected_sampling']:.0%}"),
                    ("Connected, year average", f"{p['connected_annual']:.0%}"),
                    ("Stream length mapped", f"{p['stream_km']:,.0f} km")])]


# coloring (layers.json id) -> the stats behind it; each takes the properties and a list to
# add any Plotly charts it builds to
SECTIONS = {
    "basin": _polymers,
    "whole": lambda p, charts: [_heading("Land cover, whole watershed"),
                                *_shares(p["whole"], lambda v: f"{v:.1%}")],
    "corridor": lambda p, charts: [_heading("Land-cover score along connected streams"),
                                   *_shares(p["corridor"], lambda v: f"{v:.3f}")],
    "contribution": lambda p, charts: _contribution(p),
    "likeness": lambda p, charts: [_heading("Likeness to the sink"), _stats([
        ("This sample alone vs. the sink", f"{p['likeness']:.3f}")])],
    "connected_sampling": lambda p, charts: _connectivity(p),
    "peak": lambda p, charts: [_heading("Flow"),
                               _stats([("Median peak flow", p["peak_flow"])])],
}


# The same for the sink sample, whose catchment is the whole basin above it.
SINK_SECTIONS = {
    "basin": _polymers,
    "whole": lambda p, charts: [_heading("Land cover, whole basin above the sink"),
                                *_shares(p["whole"], lambda v: f"{v:.1%}")],
    "corridor": _not_for_sink("Land-cover score along connected streams"),
    "contribution": lambda p, charts: _model_mix(charts),
    "likeness": lambda p, charts: _source_likeness(),
    "connected_sampling": _not_for_sink("Stream connectivity"),
    "peak": _not_for_sink("Flow"),
}


class Popup:
    """
    A watershed's popup under one coloring; Popup(SINK, layer, sink=True) is the sink sample's.

    Attributes:
        element - the content (an Antioch Div) to hand to Leaflet
    """

    def __init__(self, p, layer, sink=False):
        self._charts = []
        self.element = Div(style=c.POPUP_STYLE)
        title = H3(Span(style={**c.DOT_STYLE, "background-color": p["color"]}), Span(p["name"]),
                   style=c.POPUP_TITLE_STYLE)
        if "sample_id" not in p:
            self.element.add(title, Div("Land draining straight to the Snake between the "
                                        "sample sites; not sampled.", style=c.META_STYLE))
            return
        area = f"{p['area_km2']:,.0f} km²" + (" upstream" if sink else "")
        self.element.add(
            title,
            Div(f"Sample {p['sample_id'][-2:]} · {p['particles']:.0f} particles · {area}",
                style=c.META_STYLE),
        )
        if sink:  # how well the modelled mix of sources reproduces this sample
            self.element.add(_stats([(f"Mixture-model fit ({MODEL['metric']})",
                                      f"{MODEL['best_score']:.3f}")]))
        self.element.add(*(SINK_SECTIONS if sink else SECTIONS)[layer](p, self._charts))

    def opened(self):
        """Draw the charts, now that the content is in the page."""
        for chart in self._charts:
            chart.ensure_initialized()

    def closed(self):
        for chart in self._charts:
            chart.destroy()
        self._charts = []
