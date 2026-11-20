"""The surfaces behind a bivariate mixture: the sink, the best model, and the mismatch."""
from antioch.elements import Div

from plot_lib import DENSITY_COLORSCALE
from sed_stats import metrics_2d

from .plots import make_plot


# Mismatch is signed in spirit — where the model over- or under-shoots — so it
# gets a diverging scale rather than the density ramp.
MISMATCH_COLORSCALE = [
    [0.0, "#ffffff"],
    [0.5, "#f5c542"],
    [1.0, "#c1121f"],
]


def _surfaces(charts, label, sink_name, density_set, sink, result,
              x_title, y_title):
    """
    Sink, best model, and where they disagree.

    Ten overlaid trial curves work in 1D; ten stacked heatmaps do not. The
    useful comparison in 2D is the sink against the single best model, plus the
    mismatch surface showing which part of the grid the model fails to
    reproduce.
    """
    grids = result.top_grids
    if not grids:
        return Div()
    best = grids[0]

    wrapper = Div()
    for title, grid, scale, filename in (
        (f"{sink_name} (sink)", sink.densities, DENSITY_COLORSCALE, "sink"),
        ("Best model", best, DENSITY_COLORSCALE, "model"),
        ("Mismatch", metrics_2d.mismatch_surface(sink.densities, best),
         MISMATCH_COLORSCALE, "mismatch"),
    ):
        trace = density_set.heatmap(
            grid, colorscale=scale,
            colorbar_title="Mismatch" if filename == "mismatch" else "Density",
        )
        wrapper.add(Div(make_plot(
            charts, [trace], f"{label} — {title}",
            x_title, y_title,
            height=420, show_legend=False,
            filename=f"{label}_{filename}".replace(" ", "_"),
            extra_layout=density_set.axis_layout(x_title, y_title),
        ).element))
    return wrapper

