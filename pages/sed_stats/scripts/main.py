"""
Grain Dashboard

Editor-style layout: an Outputs tab holding a tool ribbon and the generated
graphs, and a Spreadsheet tab holding the data. Each ribbon tool opens a
wizard that collects samples, dimensions and options; graphs are produced
only on demand. Selecting several dimensions yields one tabbed output with a
tab per dimension. Data comes from the built-in example or an uploaded
csv/xls/xlsx file.
"""
import asyncio
import math
import random
import traceback

import numpy as np

from antioch import *
from antioch.macros import Modal

from plot_lib import (
    PlotlyChart, bar_trace, line_trace, marker_trace, series_color,
    stacked_subplot_layout, subplot_axes, subplot_title,
    charts_to_zip, download_bytes, safe_filename,
)
from spreadsheet_lib import TabulatorSheet, SpreadsheetUpload
from ui_lib import TabView, TabItem, Wizard, WizardPanel, CheckboxGroup, labeled, Ribbon
from sed_stats import metrics, mds
from sed_stats.distributions.histogram import Histogram
from sed_stats.distributions.categorical import categorical_pdp, categorical_cdf
from sed_stats.distributions.numeric import numeric_pdp, numeric_cdf

VIEWS = {
    "histogram": {"label": "Histogram", "chart_type": "bar"},
    "pdf": {"label": "PDF", "chart_type": "line"},
    "cdf": {"label": "CDF", "chart_type": "line"},
}

LAYOUTS = {
    "overlay": "Overlay (one plot)",
    "stacked": "Stacked subplots",
}

# Intersample comparison metrics from sed_stats.metrics.
# "input" selects what each metric is fed: normalized per-sample PDFs on the
# shared grid, or the corresponding CDFs (ks/kuiper compare CDF curves).
METRICS = {
    "similarity": {"label": "Similarity", "func": metrics.similarity, "input": "pdf",
                   "note": "0–1, higher is more similar"},
    "likeness": {"label": "Likeness", "func": metrics.likeness, "input": "pdf",
                 "note": "0–1, higher is more similar"},
    "r2": {"label": "Cross-correlation (R²)", "func": metrics.r2, "input": "pdf",
           "note": "0–1, higher is more similar"},
    "ks": {"label": "KS statistic", "func": metrics.ks, "input": "cdf",
           "note": "0–1, lower is more similar"},
    "kuiper": {"label": "Kuiper statistic", "func": metrics.kuiper, "input": "cdf",
               "note": "0–1, lower is more similar"},
}

MDS_TYPES = {
    "non_metric": "Non-metric MDS",
    "metric": "Metric MDS",
}

CHART_WIDTH = 760
MAX_BINS = 2000

COLORS = ["gray", "tan", "white", "black", "red"]
ROUNDNESS_LEVELS = ["low", "medium", "high"]
COMPOSITIONS = ["quartz", "feldspar", "lithic", "mica"]

# (center, spread) per sample. Samples 1-3 are pure location shifts, so their
# CDFs never cross and KS == Kuiper. Sample 4 shares sample 2's center but is
# much wider, so its CDF crosses sample 2's and Kuiper exceeds KS.
SAMPLE_SIZE_PARAMS = [(0.8, 0.3), (1.2, 0.3), (1.6, 0.3), (1.2, 0.9)]


def generate_example_rows():
    """Four samples of 40 grains; sample 3 also records roundness."""
    rows = []
    for s, (center, spread) in enumerate(SAMPLE_SIZE_PARAMS, start=1):
        for g in range(1, 41):
            rows.append({
                "sample": f"Sample {s}",
                "grain": f"G{g}",
                "size_mm": f"{max(0.05, random.gauss(center, spread)):.2f}",
                "color": random.choice(COLORS),
                "composition": random.choice(COMPOSITIONS),
                "roundness": random.choice(ROUNDNESS_LEVELS) if s == 3 else "",
            })
    return rows


def detect_columns(rows):
    """First column is the sample ID, second the grain ID, rest are dimensions."""
    if not rows:
        return None, None, []
    keys = list(rows[0].keys())
    sample_col = keys[0] if keys else None
    id_col = keys[1] if len(keys) > 1 else None
    return sample_col, id_col, keys[2:]


def sample_names(rows, sample_col):
    """Distinct sample names in spreadsheet order."""
    names = []
    for row in rows:
        name = str(row.get(sample_col, "") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def values_by_sample(rows, sample_col, attribute, only_samples=None):
    """Non-empty attribute values grouped by sample, preserving sample order."""
    grouped = {}
    for row in rows:
        sample = str(row.get(sample_col, "") or "").strip()
        value = row.get(attribute, "")
        if not sample or value in ("", None):
            continue
        if only_samples is not None and sample not in only_samples:
            continue
        grouped.setdefault(sample, []).append(value)
    return grouped


def nice_bin_size(vmin, vmax, target_bins=30):
    """A round bin width (1/2/2.5/5 x 10^k) giving roughly target_bins bins."""
    span = (vmax - vmin) or abs(vmin) or 1
    raw = span / target_bins
    magnitude = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * magnitude:
            return m * magnitude
    return raw


def _numeric_series(grouped, view, bin_size):
    """Per-sample histograms on a shared bin grid so all series align."""
    numeric = {s: [float(v) for v in vals] for s, vals in grouped.items()}
    all_values = [v for vals in numeric.values() for v in vals]

    if bin_size is None or (max(all_values) - min(all_values)) / bin_size > MAX_BINS:
        bin_size = nice_bin_size(min(all_values), max(all_values))

    first_bin = math.floor(min(all_values) / bin_size)
    last_bin = math.floor(max(all_values) / bin_size)
    bin_starts = [(first_bin + i) * bin_size for i in range(last_bin - first_bin + 1)]

    labels = [f"{b:g}" for b in bin_starts]
    series = []
    for sample, vals in numeric.items():
        counts = {str(b): 0 for b in bin_starts}
        for v in vals:
            index = math.floor(v / bin_size) - first_bin
            counts[str(bin_starts[index])] += 1
        histogram = Histogram(counts)

        if view == "histogram":
            data = list(histogram.counts)
        else:
            distribution = numeric_cdf(histogram) if view == "cdf" else numeric_pdp(histogram)
            data = [float(p) for p in distribution.probabilities]
        series.append((sample, data))
    return labels, series


def _categorical_series(grouped, view):
    """Per-sample histograms over the shared, sorted category set."""
    categories = sorted({str(v) for vals in grouped.values() for v in vals})
    series = []
    for sample, vals in grouped.items():
        str_vals = [str(v) for v in vals]
        histogram = Histogram({c: str_vals.count(c) for c in categories})

        if view == "histogram":
            data = list(histogram.counts)
        else:
            distribution = categorical_cdf(histogram) if view == "cdf" else categorical_pdp(histogram)
            data = [float(p) for p in distribution.probabilities]
        series.append((sample, data))
    return categories, series


def attribute_series(rows, sample_col, attribute, view, bin_size, only_samples=None):
    """Returns (labels, [(sample, data), ...]) for one dimension across samples."""
    grouped = values_by_sample(rows, sample_col, attribute, only_samples)
    if not grouped:
        return [], []
    try:
        return _numeric_series(grouped, view, bin_size)
    except (TypeError, ValueError):
        return _categorical_series(grouped, view)


def error_box(heading, exception):
    """Render an exception in the page; the browser console is out of reach on mobile."""
    details = traceback.format_exc()
    return Div(
        H3(f"{heading}: {type(exception).__name__}",
           style={"font-size": "15px", "margin": "20px 0 6px 0", "color": "#b00020"}),
        Pre(details, style={
            "font-size": "11px", "white-space": "pre-wrap", "word-break": "break-word",
            "background-color": "#fff4f4", "border": "1px solid #f0c0c0",
            "padding": "8px", "margin": "0", "max-width": f"{CHART_WIDTH}px",
            "overflow-x": "auto",
        }),
    )


def main():
    # App shell: viewport-height flex column with no page scroll, so the tab
    # bar and ribbon stay put and only the panels scroll.
    DOM.body.style.update({
        "margin": "0",
        "height": "100vh",
        "overflow": "hidden",
        "display": "flex",
        "flex-direction": "column",
        "font-family": "system-ui, -apple-system, sans-serif",
    })

    DOM.add(Div(
        H1("Sed/Stats", style={"margin": "0", "font-size": "20px"}),
        style={
            "flex-shrink": "0", "padding": "10px 16px",
            "background-color": "#2c3e50", "color": "#fff",
        },
    ))

    # ----------------------------------------------------------- spreadsheet

    # A definite height: Tabulator sizes its virtual viewport from this, and a
    # percentage would resolve against an auto-height parent and collapse.
    table = TabulatorSheet(data=generate_example_rows(), height="calc(100vh - 210px)")
    upload = SpreadsheetUpload()
    spreadsheet_panel = Div(
        Div(upload.element, style={
            "flex-shrink": "0", "padding": "10px 16px",
            "border-bottom": "1px solid #e9ecef",
        }),
        Div(table.element, style={"flex": "1", "min-height": "0", "padding": "16px"}),
        style={
            "display": "flex", "flex-direction": "column",
            "height": "100%", "min-height": "0",
        },
    )

    # --------------------------------------------------------------- outputs

    ribbon = Ribbon(tools=[
        ("distributions", "Distributions"),
        ("matrix", "Comparison matrices"),
        ("mds", "MDS"),
    ])
    ribbon.element.style.margin_bottom = "0"
    gallery_empty = P("No graphs yet. Pick a tool above to make one.",
                      style={"color": "#6c757d"})
    gallery = Div()
    outputs_panel = Div(
        Div(ribbon.element, style={"flex-shrink": "0"}),
        # Only this scrolls.
        Div(gallery_empty, gallery, style={
            "flex": "1", "min-height": "0", "overflow-y": "auto", "padding": "16px",
        }),
        style={
            "display": "flex", "flex-direction": "column",
            "height": "100%", "min-height": "0",
        },
    )

    tab_view = TabView(fill=True, tabs=[
        TabItem("Outputs", outputs_panel),
        TabItem("Spreadsheet", spreadsheet_panel),
    ])
    DOM.add(Div(tab_view.element, style={
        "flex": "1", "min-height": "0", "padding": "0 16px 16px",
        "display": "flex", "flex-direction": "column",
    }))

    entries = []  # [{"element", "charts", "tabview"}]
    tools = {}    # key -> {"wizard", "samples", "dimensions", ...}

    # ------------------------------------------------------------- plotting

    def make_plot(charts, traces, title, x_title, y_title, height=420,
                  show_legend=True, filename=None, extra_layout=None):
        """Build a plot and register it under `filename` for export."""
        name = filename or title.replace(" ", "_")
        layout = {
            "title": {"text": title},
            "xaxis": {"title": {"text": x_title}},
            "yaxis": {"title": {"text": y_title}, "rangemode": "tozero"},
            "showlegend": show_legend,
            "legend": {"orientation": "v", "x": 1.02, "y": 1},
            "barmode": "group",
        }
        if extra_layout:
            layout.update(extra_layout)

        chart = PlotlyChart(
            traces=traces,
            layout=layout,
            config={"toImageButtonOptions": {"format": "svg", "filename": name}},
            width=CHART_WIDTH,
            height=height,
        )
        charts.append((name, chart))
        return chart

    def distribution_traces(labels, series, view, offset=0, total=None):
        total = total or len(series)
        chart_type = VIEWS[view]["chart_type"]
        traces = []
        for i, (sample, data) in enumerate(series):
            color = series_color(offset + i, total)
            if chart_type == "bar":
                traces.append(bar_trace(labels, data, sample, color))
            else:
                traces.append(line_trace(labels, data, sample, color))
        return traces

    def build_distribution(charts, rows, sample_col, dimension, opts):
        labels, series = attribute_series(
            rows, sample_col, dimension, opts["view"], opts["bin_size"], opts["samples"]
        )
        if not series:
            return P(f"No data for '{dimension}'.", style={"color": "#6c757d"})

        y_title = "Count" if opts["view"] == "histogram" else "Probability"
        base = f"{dimension} — {VIEWS[opts['view']]['label']}"

        if opts["layout"] == "overlay":
            traces = distribution_traces(labels, series, opts["view"])
            return Div(make_plot(charts, traces, base, dimension, y_title,
                                 filename=f"{dimension}_{opts['view']}").element)

        # Stacked: one figure with real subplots sharing an x-axis, rather
        # than a column of separate figures.
        rows = len(series)
        axis_layout = stacked_subplot_layout(rows, shared_xaxis=True)
        traces = []
        annotations = []
        for i, (sample, data) in enumerate(series):
            trace = distribution_traces(labels, [(sample, data)], opts["view"],
                                        offset=i, total=rows)[0]
            x_axis, y_axis = subplot_axes(i)
            trace["xaxis"] = x_axis
            trace["yaxis"] = y_axis
            trace["showlegend"] = False
            traces.append(trace)
            annotations.append(subplot_title(i, sample))

            suffix = "" if i == 0 else str(i + 1)
            axis_layout[f"yaxis{suffix}"]["title"] = {"text": y_title}
            axis_layout[f"yaxis{suffix}"]["rangemode"] = "tozero"
            if i == rows - 1:
                axis_layout[f"xaxis{suffix}"]["title"] = {"text": dimension}

        extra_layout = dict(axis_layout)
        extra_layout["annotations"] = annotations
        return Div(make_plot(
            charts, traces, base, dimension, y_title,
            height=max(240, 150 * rows + 90), show_legend=False,
            filename=f"{dimension}_{opts['view']}_stacked",
            extra_layout=extra_layout,
        ).element)

    def build_matrix(charts, rows, sample_col, dimension, opts):
        metric = METRICS[opts["metric"]]
        _, series = attribute_series(
            rows, sample_col, dimension, metric["input"], opts["bin_size"], opts["samples"]
        )
        if len(series) < 2:
            return P("Need at least two samples with data to compare.", style={"color": "#6c757d"})

        series = [(name, np.array(data, dtype=float)) for name, data in series]

        cell_style = {
            "border": "1px solid #ddd", "padding": "4px 8px",
            "text-align": "right", "font-size": "13px",
        }
        head_style = {**cell_style, "text-align": "center", "background-color": "#f8f9fa"}

        header = Tr(Th("", style=head_style), *[Th(name, style=head_style) for name, _ in series])
        body_rows = []
        for name_i, data_i in series:
            cells = [Th(name_i, style=head_style)]
            for name_j, data_j in series:
                if name_i == name_j:
                    cells.append(Td("—", style=cell_style))
                else:
                    value = float(metric["func"](data_i, data_j))
                    # r2 is undefined when a sample has no variance across bins
                    text = "n/a" if math.isnan(value) else f"{value:.3g}"
                    cells.append(Td(text, style=cell_style))
            body_rows.append(Tr(*cells))

        return Div(
            P(f"{metric['label']} ({metric['note']})",
              style={"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}),
            Div(
                Table(header, *body_rows, style={"border-collapse": "collapse"}),
                style={"overflow-x": "auto", "max-width": f"{CHART_WIDTH}px"},
            ),
        )

    def build_mds(charts, rows, sample_col, dimension, opts):
        metric = opts["metric"]
        _, series = attribute_series(
            rows, sample_col, dimension, mds.expected_form(metric),
            opts["bin_size"], opts["samples"]
        )
        if len(series) < 3:
            return P("Need at least three samples with data for MDS.",
                     style={"color": "#6c757d"})

        non_metric = opts["mds_type"] == "non_metric"
        points, stress, matrix, embedding = mds.mds_function(series, metric, non_metric)
        wrapper = Div()

        # Dashed segments joining each sample to its nearest neighbor. A None
        # breaks the line between segments; Plotly reads array entries as
        # values, so a non-numeric entry is simply a gap.
        nn_x, nn_y = [], []
        for point in points:
            if point.nearest_neighbor is not None:
                nn_x.extend([point.x, point.nearest_neighbor[0], None])
                nn_y.extend([point.y, point.nearest_neighbor[1], None])

        traces = []
        if nn_x:
            traces.append({
                "type": "scatter", "mode": "lines", "x": nn_x, "y": nn_y,
                "name": "Nearest neighbor",
                "line": {"color": "#999", "width": 1, "dash": "dash"},
                "connectgaps": False, "hoverinfo": "skip",
            })
        # Points are added after the connectors so they draw on top.
        traces.extend(
            marker_trace([p.x], [p.y], p.label,
                         color=series_color(i, len(points)), labels=[p.label])
            for i, p in enumerate(points)
        )
        wrapper.add(
            P(f"{MDS_TYPES[opts['mds_type']]} on {METRICS[metric]['label']} "
              f"dissimilarity — Kruskal stress-1: {stress:.4f}",
              style={"font-size": "13px", "color": "#555", "margin": "0 0 6px 0"}),
            Div(make_plot(charts, traces, f"{dimension} — MDS",
                          "Dimension 1", "Dimension 2",
                          filename=f"{dimension}_mds").element),
        )

        if opts["shepard"]:
            shepard = mds.shepard_data(matrix, embedding, non_metric)
            dissimilarities = shepard["dissimilarities"]
            distances = shepard["distances"]
            max_val = float(max(dissimilarities.max(), distances.max())) if len(distances) else 1.0

            shepard_traces = [marker_trace(
                [float(d) for d in dissimilarities],
                [float(v) for v in distances],
                "Distances", color="rgba(54, 162, 235, 0.8)", size=7,
            )]
            if shepard["disparities"] is not None:
                order = np.argsort(dissimilarities)
                shepard_traces.append(line_trace(
                    [float(dissimilarities[i]) for i in order],
                    [float(shepard["disparities"][i]) for i in order],
                    "Disparities", color="#d62728", markers=False,
                ))
            shepard_traces.append({
                "type": "scatter", "mode": "lines",
                "x": [0, max_val], "y": [0, max_val], "name": "1:1",
                "line": {"color": "#000", "width": 1, "dash": "dot"},
            })
            wrapper.add(
                P(f"Shepard plot — R² = {shepard['r2']:.3f}, stress-1 = {stress:.4f}",
                  style={"font-size": "13px", "color": "#555", "margin": "16px 0 6px 0"}),
                Div(make_plot(charts, shepard_traces, f"{dimension} — Shepard plot",
                              "Dissimilarities", "Distances / disparities",
                              height=340, filename=f"{dimension}_shepard").element),
            )

        return wrapper

    # --------------------------------------------------------------- gallery

    def add_entry(title, body, charts, tabview=None):
        entry = {"element": None, "charts": charts, "tabview": tabview}

        download = Button("Download SVG", style={
            "background-color": "#146c2e", "color": "#fff", "border": "none",
            "padding": "5px 12px", "border-radius": "4px", "cursor": "pointer",
            "font-size": "13px", "margin-right": "8px",
        })
        delete = Button("Delete", style={
            "background-color": "#b00020", "color": "#fff", "border": "none",
            "padding": "5px 12px", "border-radius": "4px", "cursor": "pointer",
            "font-size": "13px",
        })

        base_name = safe_filename(title, "graph")

        async def download_archive():
            try:
                download.set_text("Zipping…")
                data = await charts_to_zip(entry["charts"])
                download_bytes(data, f"{base_name}.zip")
            finally:
                download.set_text("Download SVG")

        @when(download.events.click)
        def on_download(sender, *args):
            named = entry["charts"]
            if len(named) == 1:
                named[0][1].download_svg(base_name)
            else:
                # One file per plot would mean a browser download storm, and
                # most browsers block all but the first anyway.
                asyncio.ensure_future(download_archive())

        @when(delete.events.click)
        def on_delete(sender, *args):
            for _, chart in entry["charts"]:
                try:
                    chart.destroy()
                except Exception:
                    pass
            entry["element"].remove()
            entries.remove(entry)
            gallery_empty.style.display = "none" if entries else "block"

        header = Div(
            H3(title, style={"font-size": "16px", "margin": "0", "flex": "1", "min-width": "0"}),
            Div(download, delete, style={"flex-shrink": "0"}),
            style={
                "display": "flex", "align-items": "center", "gap": "10px",
                "flex-wrap": "wrap", "margin-bottom": "10px",
            },
        )
        if not charts:
            download.style.display = "none"

        entry["element"] = Div(header, body, style={
            "border": "1px solid #ddd", "border-radius": "8px",
            "padding": "14px", "margin-bottom": "16px", "background-color": "#fff",
        })
        entries.append(entry)
        gallery.add(entry["element"])
        gallery_empty.style.display = "none"

    # ----------------------------------------------------------------- tools

    def sync_tool_options(*args, **kwargs):
        """Keep every tool's sample/dimension choices in step with the spreadsheet."""
        rows = table.get_data()
        sample_col, _, dimensions = detect_columns(rows)
        names = sample_names(rows, sample_col)
        for tool in tools.values():
            tool["samples"].set_options(names)
            tool["dimensions"].set_options(dimensions)

    def make_tool(key, label, submit_text, option_rows, min_samples, build, read_extra):
        title_input = Input("text", placeholder=f"e.g. {label} of size",
                            style={"width": "260px"})
        sample_group = CheckboxGroup(empty_text="No samples in the spreadsheet")
        dimension_group = CheckboxGroup(empty_text="No dimensions in the spreadsheet")
        bin_size_input = Input("number", placeholder="auto", style={"width": "90px"})

        panels = [
            WizardPanel("Samples", Div(
                labeled("Output title", title_input,
                        "Optional; names the entry and its SVG file"),
                labeled("Samples", sample_group.element,
                        f"Choose at least {min_samples} sample"
                        f"{'s' if min_samples != 1 else ''}"),
            ), f"Choose the samples to include in the {label.lower()}."),
            WizardPanel("Dimensions", Div(
                labeled("Dimensions", dimension_group.element,
                        "Several dimensions produce one tabbed output, a tab each"),
            ), "Choose which dimensions of the sample set to graph."),
            WizardPanel("Options", Div(
                *option_rows,
                labeled("Bin size", bin_size_input,
                        "Numeric dimensions only; blank picks a round width automatically"),
            ), "Configure how the distributions are computed."),
        ]

        # The modal supplies the title bar and the curtain, so the wizard is
        # built without its own header.
        wizard = Wizard(submit_text=submit_text, panels=panels)
        wizard.element.style.update({
            "margin-top": "0", "border": "none", "border-radius": "0",
        })
        modal = Modal(title=label, modal_style={
            "max-width": "840px", "width": "92vw", "min-width": "0",
        })
        modal.set_content(wizard.element)
        DOM.add(modal.element)

        @when(modal.events.close)
        def on_modal_close(sender, *args):
            ribbon.select(None)

        def current_bin_size():
            try:
                size = float(bin_size_input.value)
                return size if size > 0 else None
            except ValueError:
                return None

        def read_options():
            opts = {
                "title": title_input.value.strip(),
                "samples": sample_group.values(),
                "dimensions": dimension_group.values(),
                "bin_size": current_bin_size(),
            }
            opts.update(read_extra())
            return opts

        @when(wizard.events.submit)
        def on_submit(sender, *args):
            opts = read_options()
            if len(opts["samples"]) < min_samples:
                wizard.set_status(
                    f"{label} needs at least {min_samples} sample"
                    f"{'s' if min_samples != 1 else ''}; "
                    f"{len(opts['samples'])} selected."
                )
                return
            if not opts["dimensions"]:
                wizard.set_status("Select at least one dimension.")
                return

            wizard.set_status("")
            rows = table.get_data()
            sample_col, _, _ = detect_columns(rows)
            charts = []
            contents = []

            for dimension in opts["dimensions"]:
                try:
                    contents.append(build(charts, rows, sample_col, dimension, opts))
                except Exception as e:
                    contents.append(error_box(f"Could not build '{dimension}'", e))

            tabview = None
            if len(contents) == 1:
                body = contents[0]
            else:
                tabview = TabView(tabs=[
                    TabItem(dimension, content)
                    for dimension, content in zip(opts["dimensions"], contents)
                ])
                body = tabview.element

                @when(tabview.events.change)
                def on_dimension_tab(sender, *args):
                    # Plots sized while their tab was hidden need a re-fit
                    for _, chart in charts:
                        chart.resize()

            base_title = opts["title"] or label
            add_entry(base_title, body, charts, tabview)

            wizard.set_status("")
            modal.close()
            # Plots were built inside a modal that is now hidden, so they need
            # a re-fit against their real size in the gallery.
            for _, chart in charts:
                chart.resize()

        tools[key] = {
            "wizard": wizard,
            "modal": modal,
            "samples": sample_group,
            "dimensions": dimension_group,
        }

    # Distributions
    dist_view = Select(*[Option(v["label"], value=k) for k, v in VIEWS.items()])
    dist_layout = Select(*[Option(label, value=k) for k, label in LAYOUTS.items()])
    make_tool(
        "distributions", "Distributions", "Create distribution plots",
        option_rows=[
            labeled("View", dist_view, "Histogram counts, or normalized PDF / CDF"),
            labeled("Layout", dist_layout, "Overlay samples on one plot, or stack one per sample"),
        ],
        min_samples=1,
        build=build_distribution,
        read_extra=lambda: {"view": dist_view.value, "layout": dist_layout.value},
    )

    # Comparison matrices
    matrix_metric = Select(*[Option(m["label"], value=k) for k, m in METRICS.items()])
    make_tool(
        "matrix", "Comparison matrices", "Create comparison matrices",
        option_rows=[
            labeled("Comparison metric", matrix_metric,
                    "Statistic computed for every pair of samples"),
        ],
        min_samples=2,
        build=build_matrix,
        read_extra=lambda: {"metric": matrix_metric.value},
    )

    # MDS
    mds_metric = Select(*[Option(m["label"], value=k) for k, m in METRICS.items()])
    mds_type = Select(*[Option(label, value=k) for k, label in MDS_TYPES.items()])
    mds_shepard = Input("checkbox")
    make_tool(
        "mds", "MDS", "Create MDS plots",
        option_rows=[
            labeled("Comparison metric", mds_metric, "Used to build the dissimilarity matrix"),
            labeled("MDS type", mds_type,
                    "Non-metric preserves rank order; metric preserves distances"),
            labeled("Shepard plot", mds_shepard,
                    "Diagnostic comparing dissimilarities to MDS distances"),
        ],
        min_samples=3,
        build=build_mds,
        read_extra=lambda: {
            "metric": mds_metric.value,
            "mds_type": mds_type.value,
            "shepard": mds_shepard._dom_element.checked,
        },
    )

    sync_tool_options()

    # ---------------------------------------------------------------- wiring

    @when(ribbon.events.select)
    def on_tool_select(sender, key):
        tools[key]["modal"].open()

    @when(tab_view.events.change)
    def on_top_tab(sender, tab, *args):
        # Both widgets measure themselves on render and read zero while hidden.
        if tab.title == "Spreadsheet":
            table.redraw()
        else:
            for entry in entries:
                for _, chart in entry["charts"]:
                    chart.resize()

    @when(table.events.data_change)
    def on_table_change(sender, *args):
        sync_tool_options()

    @when(upload.events.data_loaded)
    def on_upload(sender, rows, filename):
        table.set_data(rows)
        sync_tool_options()


if __name__ == "__main__":
    main()
