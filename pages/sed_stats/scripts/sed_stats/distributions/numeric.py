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