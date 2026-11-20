"""The Bivariate density tool's output: one density grid per sample."""
from antioch.elements import Div, P


from .plots import make_plot

CAPTION_STYLE = {"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}

# Grains drawn over the density, faint enough not to fight it.
POINT_COLOR = "rgba(20, 20, 20, 0.45)"


def draw_raster(charts, raster, extras=None):
    """
    One density figure per sample.

    Args:
        extras: `(sample) -> [trace]`, drawn over that sample's density —
            its grains, or its outline
    """
    density_set = raster.density_set
    x_dimension, dimension = raster.x_name, raster.y_name
    wrapper = Div(P(f"{x_dimension} vs {dimension} — {density_set.method_note}.",
                    style=CAPTION_STYLE))

    for sample, distribution in density_set.entries:
        traces = [density_set.heatmap(
            distribution.densities, name=sample, colorbar_title="Density")]
        if extras:
            traces.extend(extras(sample))

        count = density_set.counts.get(sample, 0)
        wrapper.add(Div(make_plot(
            charts, traces, f"{sample} — {x_dimension} vs {dimension}",
            x_dimension, dimension,
            height=460, show_legend=False,
            filename=f"{sample}_{x_dimension}_{dimension}_density",
            # A density axis has no reason to reach zero; padding a Ti
            # temperature axis down to 0 K wastes most of the plot.
            extra_layout=density_set.axis_layout(x_dimension, dimension),
        ).element))
        wrapper.add(P(f"n = {count}", style={**CAPTION_STYLE,
                                            "margin": "0 0 14px 0"}))

    return wrapper

