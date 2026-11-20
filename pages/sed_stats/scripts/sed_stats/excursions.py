"""
Isotope excursions: where a record departs from its background.

A profile — δ¹³C or δ¹⁸O against depth in a core, or against age or year — has a background level
and, now and then, a stretch that departs from it (a negative carbon-isotope excursion, a
δ¹⁸O shift at a boundary). This finds them: a baseline (the median or mean of the whole record, or
a running median through it, for a record that drifts), the scatter of the points about it, and
every point further from it than `k` times that scatter. Consecutive flagged points on the same
side of the baseline are one excursion.

The scatter is a robust one (1.4826 × the median absolute deviation of the points about the
baseline), which excursions inflate less than they inflate a standard deviation, though not
nothing: with a third of a record in excursion it is roughly double the true scatter, and the
threshold is then too lenient. The method assumes the background is the larger part of the record;
for one that is half excursion neither the scatter nor the baseline means anything.

A baseline from the whole record suits a record that is level between its excursions. If the
background drifts (a trend through a core), the drift itself becomes the "scatter" and hides every
excursion; use the running median, whose window should be longer than an excursion is thick.
"""
import math

MAD_TO_SD = 1.4826            # a normal distribution's standard deviation per unit of MAD

BASELINES = {
    "median": "Median of the whole record",
    "mean": "Mean of the whole record",
    "rolling": "Running median (for a record that drifts)",
}


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def running_median(values, window):
    """The median of `window` points centred on each (shorter at the ends), window made odd."""
    window = max(1, int(window))
    window += 1 - window % 2
    half = window // 2
    return [_median(values[max(0, i - half): i + half + 1]) for i in range(len(values))]


def find(positions, values, k=2.0, baseline="median", window=11, min_run=1):
    """
    Excursions in a record.

    Args:
        positions: depth, age or year of each point (any order)
        values: the isotope value at each
        k: how many robust standard deviations from the baseline counts as an excursion
        baseline: "median", "mean" or "rolling"
        window: points in the running median
        min_run: the fewest consecutive points that make an excursion (single-point spikes are
            then not reported, though they are still flagged)

    Returns:
        dict: order (indexes, sorted by position), position, value, baseline, scale, z (each point's
        departure in robust standard deviations), flagged (bool), and runs — [{"start", "end",
        "n", "sign", "peak_position", "peak_value", "peak_z"}] for the excursions of at least min_run

    Raises:
        ValueError: for fewer than five points, a mismatch in length, or an unknown baseline
    """
    if len(positions) != len(values):
        raise ValueError("Positions and values differ in length.")
    pairs = sorted(((p, v, i) for i, (p, v) in enumerate(zip(positions, values))
                    if p is not None and v is not None and math.isfinite(p) and math.isfinite(v)))
    if len(pairs) < 5:
        raise ValueError("An excursion needs a record of at least five points.")
    if baseline not in BASELINES:
        raise ValueError(f"Unknown baseline '{baseline}'.")
    if k <= 0:
        raise ValueError("The threshold must be above zero.")
    pos = [p for p, _, _ in pairs]
    val = [v for _, v, _ in pairs]
    if baseline == "mean":
        base = [sum(val) / len(val)] * len(val)
    elif baseline == "median":
        base = [_median(val)] * len(val)
    else:
        base = running_median(val, window)
    resid = [v - b for v, b in zip(val, base)]
    centre = _median(resid)
    mad = _median([abs(r - centre) for r in resid])
    scale = MAD_TO_SD * mad
    if scale == 0:
        # More than half the points sit on the baseline: fall back to the ordinary spread
        mean = sum(resid) / len(resid)
        scale = math.sqrt(sum((r - mean) ** 2 for r in resid) / (len(resid) - 1))
    z = [r / scale if scale > 0 else 0.0 for r in resid]
    flagged = [abs(x) > k for x in z]

    runs, i = [], 0
    while i < len(val):
        if not flagged[i]:
            i += 1
            continue
        sign = 1 if z[i] > 0 else -1
        j = i
        while j + 1 < len(val) and flagged[j + 1] and (1 if z[j + 1] > 0 else -1) == sign:
            j += 1
        if j - i + 1 >= min_run:
            peak = max(range(i, j + 1), key=lambda t: abs(z[t]))
            runs.append({"start": pos[i], "end": pos[j], "n": j - i + 1, "sign": sign,
                         "peak_position": pos[peak], "peak_value": val[peak], "peak_z": z[peak]})
        i = j + 1
    return {"order": [idx for _, _, idx in pairs], "position": pos, "value": val, "baseline": base,
            "scale": scale, "z": z, "flagged": flagged, "runs": runs}
