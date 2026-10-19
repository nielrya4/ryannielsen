import math

import numpy as np

from .histogram import Histogram


class NumericDistribution:
    def __init__(self, probabilities: dict[float, float | int]):
        self.bin_starts: list[float] = sorted(probabilities.keys())
        self.probabilities: np.ndarray = np.array([probabilities[b] for b in self.bin_starts])

    def subset(self, low: float | None = None, high: float | None = None) -> "NumericDistribution":
        if low is None and high is None:
            return NumericDistribution(dict(zip(self.bin_starts, self.probabilities)))

        low = -math.inf if low is None else low
        high = math.inf if high is None else high
        mask = np.array([low <= b < high for b in self.bin_starts])
        new_bin_starts = np.array(self.bin_starts)[mask]
        new_probabilities = self.probabilities[mask]
        return NumericDistribution(dict(zip(new_bin_starts, new_probabilities)))


def numeric_histogram(values, bin_size: float) -> Histogram:
    """
    Bin numeric values into fixed-width bins.

    Parameters:
        values: Raw numeric values to bin
        bin_size: Width of each bin

    Returns:
        Histogram keyed by each bin's lower edge (as a string)
    """
    if bin_size <= 0:
        raise ValueError("bin_size must be positive")

    bin_counts: dict[float, int] = {}
    for value in values:
        bin_start = math.floor(value / bin_size) * bin_size
        bin_counts[bin_start] = bin_counts.get(bin_start, 0) + 1

    return Histogram({str(bin_start): count for bin_start, count in bin_counts.items()})


def numeric_pdp(histogram: Histogram) -> NumericDistribution:
    bin_counts = {float(name): count for name, count in zip(histogram.bin_names, histogram.counts)}
    total = sum(bin_counts.values())

    if total == 0:
        probabilities = {bin_start: 0.0 for bin_start in bin_counts}
    else:
        probabilities = {bin_start: count / total for bin_start, count in bin_counts.items()}

    return NumericDistribution(probabilities)


def numeric_cdf(histogram: Histogram) -> NumericDistribution:
    pdf = numeric_pdp(histogram)
    cumulative_probabilities = np.cumsum(pdf.probabilities)
    return NumericDistribution(dict(zip(pdf.bin_starts, cumulative_probabilities)))


# Measurements are summed as Gaussians in blocks, so a large sample against a
# fine grid does not allocate one giant (n_values x n_points) matrix.
_KERNEL_BLOCK_CELLS = 2_000_000


def kernel_density(values, uncertainties, x_values, sigma_floor: float = None) -> np.ndarray:
    """
    Sum one Gaussian per measurement, evaluated on `x_values`.

    This is the probability density plot proper: each measurement contributes a
    kernel as wide as its own uncertainty, so precise values make sharp peaks
    and imprecise ones spread out. Binning throws that information away.

    Parameters:
        values: The measured values
        uncertainties: One standard deviation per value, same length
        x_values: Grid to evaluate on, shared across samples so they align
        sigma_floor: Smallest usable width. Values with a missing, zero or
                     negative uncertainty use this instead of producing an
                     infinitely tall spike. Defaults to half the grid step.

    Returns:
        Densities summing to 1, matching how the binned distributions normalize
    """
    values = np.asarray(values, dtype=float)
    uncertainties = np.asarray(uncertainties, dtype=float)
    x_values = np.asarray(x_values, dtype=float)

    if values.size == 0 or x_values.size == 0:
        return np.zeros(x_values.shape, dtype=float)
    if values.shape != uncertainties.shape:
        raise ValueError("values and uncertainties must be the same length")

    if sigma_floor is None:
        step = float(x_values[1] - x_values[0]) if x_values.size > 1 else 1.0
        sigma_floor = abs(step) / 2 or 1e-12
    sigma_floor = max(float(sigma_floor), 1e-12)

    widths = np.where(np.isfinite(uncertainties) & (uncertainties > sigma_floor),
                      uncertainties, sigma_floor)

    totals = np.zeros(x_values.shape, dtype=float)
    block = max(1, _KERNEL_BLOCK_CELLS // max(x_values.size, 1))
    for start in range(0, values.size, block):
        stop = min(start + block, values.size)
        centers = values[start:stop, np.newaxis]
        spreads = widths[start:stop, np.newaxis]
        offsets = x_values[np.newaxis, :] - centers
        kernels = np.exp(-(offsets ** 2) / (2 * spreads ** 2)) / (
            np.sqrt(2 * np.pi) * spreads)
        totals += kernels.sum(axis=0)

    total = totals.sum()
    return totals / total if total > 0 else totals


def kernel_pdp(values, uncertainties, x_values, sigma_floor: float = None) -> NumericDistribution:
    """Uncertainty-weighted PDP, keyed by grid position."""
    densities = kernel_density(values, uncertainties, x_values, sigma_floor)
    return NumericDistribution(dict(zip([float(x) for x in x_values], densities)))


def kernel_cdf(values, uncertainties, x_values, sigma_floor: float = None) -> NumericDistribution:
    """Cumulative form of kernel_pdp."""
    pdf = kernel_pdp(values, uncertainties, x_values, sigma_floor)
    return NumericDistribution(dict(zip(pdf.bin_starts, np.cumsum(pdf.probabilities))))


def silverman_bandwidth(values) -> float:
    """
    Silverman's rule of thumb: 0.9 * A * n^(-1/5).

    A takes the smaller of the standard deviation and a robust spread from the
    interquartile range, so one outlier cannot smear the whole curve.
    """
    values = np.asarray(values, dtype=float)
    n = values.size
    if n < 2:
        return 1.0

    deviation = float(values.std(ddof=1))
    q75, q25 = np.percentile(values, [75, 25])
    iqr_spread = float(q75 - q25) / 1.349

    spread = min(s for s in (deviation, iqr_spread) if s > 0) if (
        deviation > 0 or iqr_spread > 0) else 0.0
    if spread <= 0:
        # Every value identical; any positive width will do.
        return abs(float(values[0])) * 0.01 or 1.0
    return 0.9 * spread * n ** (-0.2)


def kde(values, bandwidth: float, x_values) -> NumericDistribution:
    """
    Kernel density estimate: one Gaussian per value, all the same width.

    The difference from kernel_pdp is where the width comes from — a single
    chosen bandwidth rather than each measurement's own uncertainty. Use it
    when the data has no uncertainty column, or to smooth deliberately.
    """
    values = np.asarray(values, dtype=float)
    widths = np.full(values.shape, float(bandwidth))
    densities = kernel_density(values, widths, x_values, sigma_floor=1e-12)
    return NumericDistribution(dict(zip([float(x) for x in x_values], densities)))


def kde_cdf(values, bandwidth: float, x_values) -> NumericDistribution:
    """Cumulative form of kde."""
    pdf = kde(values, bandwidth, x_values)
    return NumericDistribution(dict(zip(pdf.bin_starts, np.cumsum(pdf.probabilities))))