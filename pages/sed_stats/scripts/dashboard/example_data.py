"""
The built-in dataset: four sources and a sink mixed from them in known
proportions.

Built so the unmixing tools can be checked against a right answer, and so the
multivariate route demonstrably earns its keep:

    Source A and Source D share almost the same age spectrum but have opposite
    geochemistry.

So unmixing on age alone cannot tell A from D — it will recover their combined
share (~60%) but split it more or less arbitrarily. Running the PCA tool over
the geochemical variables and unmixing along PC1 separates them, because the
three geochemical variables co-vary by source and give PC1 something clean to
find. That contrast is the whole point of the dataset.

Reproducible: a fixed seed on a private Random, so reloading the page gives
the same numbers and the recovered proportions can be compared run to run
without the data moving underneath.
"""
import random

SEED = 20260829

SINK_NAME = "Sink"
GRAINS_PER_SOURCE = 100
SINK_GRAINS = 220

# What the unmixing tools should recover, give or take sampling noise.
SINK_PROPORTIONS = {
    "Source A (young arc)": 0.40,
    "Source B (Grenville)": 0.25,
    "Source C (Mazatzal)": 0.15,
    "Source D (evolved arc)": 0.20,
}

# Each source: age modes as (weight, center, spread), then the geochemistry
# that actually distinguishes it. eHf, Th/U and Ti temperature co-vary by
# source, which is what gives PCA a well-defined first component.
SOURCES = {
    "Source A (young arc)": {
        "ages": [(0.6, 120, 15), (0.4, 205, 22)],
        "eHf": (8.0, 2.0),
        "Th_U": (0.85, 0.15),
        "Ti_temp": (750, 30),
        "roundness": {"angular": 0.7, "subangular": 0.25, "rounded": 0.05},
    },
    "Source B (Grenville)": {
        "ages": [(1.0, 1050, 60)],
        "eHf": (-5.0, 2.5),
        "Th_U": (0.32, 0.10),
        "Ti_temp": (680, 25),
        "roundness": {"angular": 0.1, "subangular": 0.4, "rounded": 0.5},
    },
    "Source C (Mazatzal)": {
        "ages": [(1.0, 1700, 70)],
        "eHf": (2.0, 2.0),
        "Th_U": (0.52, 0.12),
        "Ti_temp": (705, 25),
        "roundness": {"angular": 0.15, "subangular": 0.45, "rounded": 0.4},
    },
    # Deliberately shares A's age modes. Only the geochemistry separates them.
    "Source D (evolved arc)": {
        "ages": [(0.6, 128, 18), (0.4, 212, 25)],
        "eHf": (-12.0, 2.5),
        "Th_U": (0.22, 0.07),
        "Ti_temp": (620, 28),
        "roundness": {"angular": 0.6, "subangular": 0.3, "rounded": 0.1},
    },
}

# Analytical precision on age, as a fraction of the age itself — the reason
# older grains get wider kernels in a PDP.
AGE_UNCERTAINTY = (0.010, 0.022)


def _draw_age(spec, rng):
    """One age from the source's mixture of modes."""
    roll = rng.random()
    running = 0.0
    for weight, center, spread in spec["ages"]:
        running += weight
        if roll <= running:
            return max(1.0, rng.gauss(center, spread))
    _, center, spread = spec["ages"][-1]
    return max(1.0, rng.gauss(center, spread))


def _draw_category(weights, rng):
    roll = rng.random()
    running = 0.0
    for name, weight in weights.items():
        running += weight
        if roll <= running:
            return name
    return next(reversed(weights))


def _draw_grain(sample, spec, index, rng):
    age = _draw_age(spec, rng)
    uncertainty = age * rng.uniform(*AGE_UNCERTAINTY)
    return {
        "sample": sample,
        "grain": f"g{index}",
        "age_Ma": f"{age:.1f}",
        "1s": f"{uncertainty:.2f}",
        "eHf": f"{rng.gauss(*spec['eHf']):.2f}",
        "Th_U": f"{max(0.01, rng.gauss(*spec['Th_U'])):.3f}",
        "Ti_temp": f"{rng.gauss(*spec['Ti_temp']):.0f}",
        "roundness": _draw_category(spec["roundness"], rng),
    }


def sink_counts():
    """
    Exactly how many sink grains come from each source.

    Drawing each grain's source at random would leave the realized mix several
    points off the target — noise that has nothing to do with the unmixing and
    would muddy any check of it. Fixing the counts makes SINK_PROPORTIONS the
    literal right answer.
    """
    counts = {name: int(round(share * SINK_GRAINS))
              for name, share in SINK_PROPORTIONS.items()}
    # Rounding can leave the total a grain or two out.
    drift = SINK_GRAINS - sum(counts.values())
    if drift:
        largest = max(counts, key=counts.get)
        counts[largest] += drift
    return counts


def generate_example_rows():
    """
    Four source samples plus a sink drawn from them in SINK_PROPORTIONS.

    The sink's grains are fresh draws from the same populations rather than
    copies of source grains, which is what mixing at the population level
    actually means — and what makes the sink's distribution a convex
    combination of the sources'.
    """
    rng = random.Random(SEED)
    rows = []

    for sample, spec in SOURCES.items():
        for index in range(1, GRAINS_PER_SOURCE + 1):
            rows.append(_draw_grain(sample, spec, index, rng))

    sink_rows = []
    for source, count in sink_counts().items():
        for _ in range(count):
            sink_rows.append(_draw_grain(SINK_NAME, SOURCES[source], 0, rng))
    # Shuffled so the sink is not silently ordered by its own answer.
    rng.shuffle(sink_rows)
    for index, row in enumerate(sink_rows, start=1):
        row["grain"] = f"g{index}"
    rows.extend(sink_rows)

    return rows
