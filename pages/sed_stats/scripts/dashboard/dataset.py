"""Turning spreadsheet rows into the per-sample series the plots consume."""
import math

from sed_stats.distributions.histogram import Histogram
from sed_stats.distributions.categorical import categorical_pdp, categorical_cdf
from sed_stats.distributions.numeric import (
    kde, kde_cdf, kernel_cdf, kernel_pdp, numeric_pdp, numeric_cdf,
    silverman_bandwidth,
)

from .config import MAX_BINS, PDP_POINTS, PDP_PAD_SIGMAS

# Header spellings that mark a column as an uncertainty on its neighbour, and
# the sigma level each one implies. None means the level is not stated, so the
# caller's assumption is used.
UNCERTAINTY_TOKENS = {
    "1s": 1.0, "1sigma": 1.0, "1se": 1.0, "1sd": 1.0, "s1": 1.0,
    "2s": 2.0, "2sigma": 2.0, "2se": 2.0, "2sd": 2.0, "s2": 2.0,
    "uncertainty": None, "uncert": None, "unc": None,
    "error": None, "err": None, "sigma": None,
    "sd": None, "std": None, "stdev": None, "stddev": None, "se": None,
    "": None,  # a bare "±" normalizes to empty
}


# A sigma glyph is alphanumeric, so it survives the alnum filter and has to be
# folded to "s" for "± 1σ" to read the same as "1s".
_SIGMA_GLYPHS = str.maketrans({"σ": "s", "ς": "s", "Σ": "s"})


def _normalize(name):
    """Lowercase, alphanumerics only, so '± 1σ' and '1_S' compare equal."""
    folded = str(name).lower().translate(_SIGMA_GLYPHS)
    return "".join(c for c in folded if c.isalnum())


def _uncertainty_level(name):
    """The sigma level a header implies, or False if it isn't an uncertainty."""
    token = _normalize(name)
    if token in UNCERTAINTY_TOKENS:
        return UNCERTAINTY_TOKENS[token]
    return False


def find_uncertainty_column(keys, attribute):
    """
    The column carrying `attribute`'s uncertainty, and the sigma level it states.

    Recognises two conventions: a suffixed name ("age_1s", "size_mm error"),
    and a bare uncertainty column sitting immediately to the right of its
    measurement, which is how most detrital spreadsheets are laid out.

    Returns:
        (column_name, sigma_level) where sigma_level is 1.0 / 2.0 when the
        header states it and None when it does not, or (None, None)
    """
    prefix = _normalize(attribute)

    for key in keys:
        if key == attribute:
            continue
        token = _normalize(key)
        if token.startswith(prefix) and len(token) > len(prefix):
            level = _uncertainty_level(token[len(prefix):])
            if level is not False:
                return key, level

    if attribute in keys:
        index = keys.index(attribute)
        if index + 1 < len(keys):
            neighbour = keys[index + 1]
            level = _uncertainty_level(neighbour)
            if level is not False:
                return neighbour, level

    return None, None


def detect_columns(rows):
    """
    First column is the sample ID, second the grain ID, rest are dimensions.

    Uncertainty columns are pulled out of the dimension list: they describe a
    measurement rather than being one, and offering "1s" as something to graph
    on its own is just noise.
    """
    if not rows:
        return None, None, []
    keys = list(rows[0].keys())
    sample_col = keys[0] if keys else None
    id_col = keys[1] if len(keys) > 1 else None

    candidates = keys[2:]
    spoken_for = set()
    for attribute in candidates:
        if attribute in spoken_for:
            continue
        column, _ = find_uncertainty_column(keys, attribute)
        if column is not None and column != attribute:
            spoken_for.add(column)

    return sample_col, id_col, [k for k in candidates if k not in spoken_for]


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


def is_numeric_column(rows, column):
    """
    Whether every non-empty value in `column` parses as a number.

    Matches how attribute_series decides: it attempts the numeric path and
    falls back to the categorical one on the first value that won't convert.
    """
    seen = False
    for row in rows:
        value = row.get(column, "")
        if value in ("", None):
            continue
        try:
            float(value)
        except (TypeError, ValueError):
            return False
        seen = True
    return seen


def numeric_columns(rows, columns):
    """The subset of `columns` holding numbers."""
    return {column for column in columns if is_numeric_column(rows, column)}


def pairs_by_sample(rows, sample_col, attribute, uncertainty_col, only_samples=None):
    """
    (value, uncertainty) pairs grouped by sample, keeping only numeric rows.

    A row whose uncertainty is missing or unparseable keeps its value with an
    uncertainty of 0; kernel_density floors those rather than dropping the
    measurement, since the value itself is still good data.
    """
    grouped = {}
    for row in rows:
        sample = str(row.get(sample_col, "") or "").strip()
        value = row.get(attribute, "")
        if not sample or value in ("", None):
            continue
        if only_samples is not None and sample not in only_samples:
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"'{attribute}' is not numeric")
        try:
            sigma = abs(float(row.get(uncertainty_col, "")))
        except (TypeError, ValueError):
            sigma = 0.0
        grouped.setdefault(sample, []).append((numeric_value, sigma))
    return grouped


def paired_by_sample(rows, sample_col, x_attribute, y_attribute,
                     only_samples=None, sigma_in=1.0):
    """
    Paired x/y measurements and their uncertainties, grouped by sample.

    A bivariate distribution needs both coordinates for the same grain, so a
    row missing either one is dropped — unlike the univariate path, where each
    column stands alone.

    Returns:
        {sample: (xs, ys, x_sigmas, y_sigmas)} with equal-length lists

    Raises:
        ValueError: if either attribute is not numeric
    """
    keys = list(rows[0].keys()) if rows else []
    x_uncertainty, x_level = find_uncertainty_column(keys, x_attribute)
    y_uncertainty, y_level = find_uncertainty_column(keys, y_attribute)
    x_scale = x_level or sigma_in or 1.0
    y_scale = y_level or sigma_in or 1.0

    def read_sigma(row, column, scale):
        if not column:
            return 0.0
        try:
            return abs(float(row.get(column, ""))) / scale
        except (TypeError, ValueError):
            return 0.0

    grouped = {}
    for row in rows:
        sample = str(row.get(sample_col, "") or "").strip()
        if not sample:
            continue
        if only_samples is not None and sample not in only_samples:
            continue
        x_raw = row.get(x_attribute, "")
        y_raw = row.get(y_attribute, "")
        if x_raw in ("", None) or y_raw in ("", None):
            continue
        try:
            x_value, y_value = float(x_raw), float(y_raw)
        except (TypeError, ValueError):
            raise ValueError(
                f"'{x_attribute}' and '{y_attribute}' must both be numeric")

        entry = grouped.setdefault(sample, ([], [], [], []))
        entry[0].append(x_value)
        entry[1].append(y_value)
        entry[2].append(read_sigma(row, x_uncertainty, x_scale))
        entry[3].append(read_sigma(row, y_uncertainty, y_scale))
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


def _kernel_grid(pairs, bin_size):
    """
    A shared x grid for kernel PDPs, wide and fine enough for every sample.

    Padded by PDP_PAD_SIGMAS so the widest kernel's tails are not clipped, and
    stepped finely enough to resolve the narrowest one — a grid built for the
    histogram's ~30 bins would turn a precise measurement into a single spike.
    """
    values = [v for v, _ in pairs]
    sigmas = [s for _, s in pairs if s > 0]

    low = min(v - PDP_PAD_SIGMAS * s for v, s in pairs)
    high = max(v + PDP_PAD_SIGMAS * s for v, s in pairs)
    if high <= low:
        # Every measurement identical and exact; give the spike somewhere to sit.
        pad = abs(low) * 0.01 or 1.0
        low, high = low - pad, high + pad
    span = high - low

    if bin_size and bin_size > 0:
        step = bin_size
    else:
        step = span / PDP_POINTS
        if sigmas:
            step = min(step, min(sigmas) / 2)

    n_points = int(span / step) + 1
    if n_points > MAX_BINS:
        n_points = MAX_BINS
        step = span / (n_points - 1)
    n_points = max(n_points, 2)

    return [low + i * step for i in range(n_points)], step


def _kernel_series(grouped, view, bin_size):
    """Per-sample kernel PDPs/CDFs on one shared grid."""
    all_pairs = [pair for pairs in grouped.values() for pair in pairs]
    x_values, step = _kernel_grid(all_pairs, bin_size)
    labels = [f"{x:g}" for x in x_values]

    series = []
    for sample, pairs in grouped.items():
        values = [v for v, _ in pairs]
        sigmas = [s for _, s in pairs]
        build = kernel_cdf if view == "cdf" else kernel_pdp
        distribution = build(values, sigmas, x_values, sigma_floor=step / 2)
        series.append((sample, [float(p) for p in distribution.probabilities]))
    return labels, series


def _kde_series(grouped, view, bin_size, bandwidth):
    """
    Per-sample KDEs on one shared grid, all using the same bandwidth.

    One bandwidth for every sample is the point: the curves are compared to
    each other downstream, so smoothing them differently would put a
    difference in the metric that isn't in the data.
    """
    numeric = {}
    for sample, values in grouped.items():
        numeric[sample] = [float(v) for v in values]

    pooled = [v for values in numeric.values() for v in values]
    if bandwidth is None or bandwidth <= 0:
        bandwidth = float(silverman_bandwidth(pooled))

    x_values, _ = _kernel_grid([(v, bandwidth) for v in pooled], bin_size)
    labels = [f"{x:g}" for x in x_values]

    series = []
    for sample, values in numeric.items():
        build = kde_cdf if view == "cdf" else kde
        distribution = build(values, bandwidth, x_values)
        series.append((sample, [float(p) for p in distribution.probabilities]))
    return labels, series, bandwidth


def attribute_series(rows, sample_col, attribute, view, bin_size, only_samples=None,
                     density="auto", sigma_in=1.0, bandwidth=None):
    """
    Returns (labels, [(sample, data), ...]) for one dimension across samples.

    Histograms are counts, so they always bin. For a PDF/CDF, `density`
    chooses how the curve is built:

        "auto" - spread each measurement by its own uncertainty column (a PDP),
                 falling back to bins when the dimension has no such column
        "kde"  - one Gaussian per measurement, all `bandwidth` wide
        "bins" - bin, whatever columns exist

    Args:
        sigma_in: Sigma level of an uncertainty column that does not state its
                  own (a bare "1s"/"2s" header overrides this)
        bandwidth: KDE width; None picks one by Silverman's rule
    """
    if view in ("pdf", "cdf"):
        if density == "auto":
            labels, series = _uncertainty_series(
                rows, sample_col, attribute, view, bin_size, only_samples, sigma_in)
            if series:
                return labels, series
        elif density == "kde":
            grouped = values_by_sample(rows, sample_col, attribute, only_samples)
            if grouped:
                try:
                    labels, series, _ = _kde_series(grouped, view, bin_size, bandwidth)
                    return labels, series
                except (TypeError, ValueError):
                    pass  # categorical dimension; bin it below

    grouped = values_by_sample(rows, sample_col, attribute, only_samples)
    if not grouped:
        return [], []
    try:
        return _numeric_series(grouped, view, bin_size)
    except (TypeError, ValueError):
        return _categorical_series(grouped, view)


def _uncertainty_series(rows, sample_col, attribute, view, bin_size,
                        only_samples, sigma_in):
    """The kernel path, or ([], []) when it does not apply to this dimension."""
    if not rows:
        return [], []

    column, stated_level = find_uncertainty_column(list(rows[0].keys()), attribute)
    if column is None:
        return [], []

    try:
        grouped = pairs_by_sample(rows, sample_col, attribute, column, only_samples)
    except ValueError:
        # Categorical dimension; the uncertainty column was a false positive.
        return [], []
    if not grouped:
        return [], []

    # A stated "2s" header wins over the caller's assumption. Bandwidths are
    # always 1 sigma.
    level = stated_level or sigma_in or 1.0
    if level != 1.0:
        grouped = {sample: [(v, s / level) for v, s in pairs]
                   for sample, pairs in grouped.items()}

    if not any(s > 0 for pairs in grouped.values() for _, s in pairs):
        # Column present but empty; binning is the honest fallback.
        return [], []

    return _kernel_series(grouped, view, bin_size)


def series_for(rows, sample_col, dimension, view, opts):
    """attribute_series with the options every tool's wizard collects."""
    return attribute_series(
        rows, sample_col, dimension, view,
        opts.get("bin_size"), opts.get("samples"),
        density=opts.get("density", "auto"),
        sigma_in=opts.get("sigma_in", 1.0),
        bandwidth=opts.get("bandwidth"),
    )
