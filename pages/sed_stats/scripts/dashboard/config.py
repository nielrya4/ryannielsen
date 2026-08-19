"""Choices the wizards offer, and the constants the builders share."""
from sed_stats import metrics

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

# Ribbon buttons, in order. The keys tie a button to its Tool.
TOOLS = {
    "distributions": "Distributions",
    "matrix": "Comparison matrices",
    "mds": "MDS",
}

CHART_WIDTH = 760

# Guards against a user-supplied bin size that would shred the range into an
# unrenderable number of bins.
MAX_BINS = 2000
