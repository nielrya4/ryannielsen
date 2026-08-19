"""Turning spreadsheet rows into the per-sample series the plots consume."""
import math

from sed_stats.distributions.histogram import Histogram
from sed_stats.distributions.categorical import categorical_pdp, categorical_cdf
from sed_stats.distributions.numeric import numeric_pdp, numeric_cdf

from .config import MAX_BINS


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
