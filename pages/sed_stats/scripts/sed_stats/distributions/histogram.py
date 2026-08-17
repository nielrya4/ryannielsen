
class Histogram:
    def __init__(self, bins: dict[str, int]):
        self.bin_names: list[str] = list(bins.keys())
        self.counts: list[int] = list(bins.values())
        self.n_bins = len(self.bin_names)