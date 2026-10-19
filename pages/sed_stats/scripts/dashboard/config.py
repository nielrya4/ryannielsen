"""Choices the wizards offer, and the constants the builders share."""
from sed_stats import metrics, metrics_2d

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

# The mixture model scores a modelled curve against the sink, so it only takes
# the metrics sed_stats.mixture knows how to evaluate in bulk.
MIXTURE_METRICS = {
    "cross_correlation": {"label": "Cross-correlation (R²)",
                          "note": "higher is a better fit"},
    "ks": {"label": "KS statistic", "note": "lower is a better fit"},
    "kuiper": {"label": "Kuiper statistic", "note": "lower is a better fit"},
}

MIXTURE_TRIALS = [1000, 5000, 10000, 50000]

# Whose variance a grain-level PCA should follow. Sample-weighted by default:
# a sample with three times the analyses would otherwise pull the axis three
# times as hard, which is an artefact of how much was measured rather than
# anything about the rocks.
GRAIN_WEIGHTINGS = {
    "sample": "Every sample equally",
    "grain": "Every grain equally",
}

# Two-dimensional measures, Sundell & Saylor (2021) eqs 15-20. Unlike the 1D
# table there is no "input" key: the 2D measures all consume the same density
# grid, and the CDF ones build their own cumulative forms internally.
BIVARIATE_METRICS = {
    "similarity": {"label": "Similarity (S₂D)", "func": metrics_2d.similarity_2d,
                   "note": "0–1, higher is more similar"},
    "likeness": {"label": "Likeness (L₂D)", "func": metrics_2d.likeness_2d,
                 "note": "0–1, higher is more similar"},
    "r2": {"label": "Cross-correlation (R²₂D)", "func": metrics_2d.r2_2d,
           "note": "0–1, higher is more similar"},
    "ks": {"label": "KS statistic (D₂D)", "func": metrics_2d.ks_2d,
           "note": "0–1, lower is more similar"},
    "kuiper": {"label": "Kuiper statistic (V₂D)", "func": metrics_2d.kuiper_2d,
               "note": "lower is more similar"},
}

# Grid resolution per axis for bivariate densities. Cost is quadratic, and the
# metrics only need both samples on the *same* grid, not a fine one.
GRID_SIZES = {
    "64": "64 × 64 (fast)",
    "128": "128 × 128",
    "256": "256 × 256",
    "512": "512 × 512 (as published)",
}
DEFAULT_GRID = "128"

# How a scatterplot arranges several samples.
SCATTER_LAYOUTS = {
    "overlay": "Overlay (one plot)",
    "facet": "One plot per sample",
}

SCATTER_SIZES = {"5": "Small", "7": "Medium", "10": "Large"}
DEFAULT_POINT_SIZE = "7"

# What a ternary composition is closed to. 100 reads as percent, which is how
# modal counts and normalized oxides are reported.
TERNARY_TOTAL = 100.0

# Toolbar structure: menu label -> a tool key, or a nested dict of the same.
# The two categories say what a tool consumes, which is the distinction that
# actually matters when choosing one — a univariate tool takes one dimension at
# a time, a multivariate tool relates two or more.
#
# The Bivariate submenu deliberately mirrors the Univariate list: density,
# comparison, MDS and mixture exist in both a 1-D and a 2-D form, and the menu
# should show that rather than hide it in a flat row of ten buttons.
TOOL_MENU = {
    "Univariate": {
        "Distributions": "distributions",
        "Comparison matrices": "matrix",
        "MDS": "mds",
        "Mixture model": "mixture",
    },
    "Multivariate": {
        "Scatterplot": "scatter",
        "Ternary": "ternary",
        "PCA": "pca",
        "Bivariate": {
            "Density": "bivariate",
            "Comparison matrices": "bivariate_matrix",
            "MDS": "bivariate_mds",
            "Mixture model": "bivariate_mixture",
        },
    },
}

# Every tool, keyed the way TOOL_MENU refers to them. The label here names the
# tool's own modal and gallery entries; TOOL_MENU chooses how it is worded in
# the menu, where the category already supplies context.
TOOLS = {
    "scatter": "Scatterplot",
    "ternary": "Ternary",
    "distributions": "Distributions",
    "matrix": "Comparison matrices",
    "mds": "MDS",
    "mixture": "Mixture model",
    "pca": "PCA",
    "bivariate": "Bivariate density",
    "bivariate_matrix": "Bivariate comparison",
    "bivariate_mds": "Bivariate MDS",
    "bivariate_mixture": "Bivariate mixture",
}

# How a PDF/CDF's curve is built. Histograms always bin, whatever this says.
DENSITY_METHODS = {
    "auto": "PDP — uncertainties if present",
    "kde": "KDE — one fixed bandwidth",
    "bins": "Bins only",
}

# What an uncertainty column means when its header does not say ("1s"/"2s" do).
SIGMA_LEVELS = {
    "1": "1σ (standard deviation)",
    "2": "2σ (95% confidence)",
}

CHART_WIDTH = 760

# Guards against a user-supplied bin size that would shred the range into an
# unrenderable number of bins.
MAX_BINS = 2000

# Kernel PDP grid: roughly this many points across the data's range, and this
# many standard deviations of padding so the widest kernel's tails fit.
PDP_POINTS = 512
PDP_PAD_SIGMAS = 3.0


# --------------------------------------------------------------- Google Drive
#
# Fill these in from a Google Cloud project to switch on "Sign in with Google".
# While any of them is blank the Drive controls stay hidden, so an unconfigured
# copy of the app simply has no Google features rather than a broken button.
#
# To get them (https://console.cloud.google.com/):
#   1. Create a project, then enable the Google Drive API and the Google
#      Picker API under "APIs & Services > Library".
#   2. "APIs & Services > Credentials":
#        - OAuth client ID, type "Web application". Add the origin this app is
#          served from (e.g. http://localhost:8000 for `antioch serve`, plus
#          the deployed URL) under "Authorized JavaScript origins".
#          That client ID goes in CLIENT_ID.
#        - API key, restricted to the same origins. That goes in API_KEY.
#   3. APP_ID is the project number, the leading digits of the client ID.
#
# All three are public client-side values — this is the OAuth flow for browser
# apps, which has no client secret. They are worth restricting by origin, but
# not worth hiding.
GOOGLE_CLIENT_ID = "770446409887-96onabcd5sb8q0l5qjf25eds1sactan0.apps.googleusercontent.com"
GOOGLE_API_KEY = "AIzaSyDFcwFdko7MD58XnHYeyCGY6whophu7jR8"
GOOGLE_APP_ID = "770446409887"
