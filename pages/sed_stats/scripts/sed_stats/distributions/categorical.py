import numpy as np

from .histogram import Histogram


class CategoricalDistribution:
    def __init__(self, probabilities: dict[str, float | int]):
        self.categories: list[str] = list[str](probabilities.keys())
        self.probabilities: np.ndarray = np.array(list[float | int](probabilities.values()))

    def subset(self, categories: list[str] | None = None) -> "CategoricalDistribution":
        if categories is None:
            return CategoricalDistribution(dict(zip(self.categories, self.probabilities)))
        mask = np.isin(self.categories, categories)
        new_categories = np.array(self.categories)[mask]
        new_probabilities = self.probabilities[mask]
        return CategoricalDistribution(dict(zip(new_categories, new_probabilities)))


def categorical_pdp(histogram: Histogram) -> CategoricalDistribution:
    category_counts = dict(zip(histogram.bin_names, histogram.counts))
    categories = sorted(category_counts.keys())
    counts = np.array([category_counts[cat] for cat in categories])
    total = counts.sum()

    if total == 0:
        probabilities = np.zeros_like(counts, dtype=float)
    else:
        probabilities = counts / total

    return CategoricalDistribution(dict(zip(categories, probabilities)))


def categorical_cdf(histogram: Histogram) -> CategoricalDistribution:
    pdf = categorical_pdp(histogram)
    cumulative_probabilities = np.cumsum(pdf.probabilities)
    return CategoricalDistribution(dict(zip(pdf.categories, cumulative_probabilities)))