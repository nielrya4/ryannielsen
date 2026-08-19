"""The built-in sample dataset the app opens with."""
import random

COLORS = ["gray", "tan", "white", "black", "red"]
ROUNDNESS_LEVELS = ["low", "medium", "high"]
COMPOSITIONS = ["quartz", "feldspar", "lithic", "mica"]

# (center, spread) per sample. Samples 1-3 are pure location shifts, so their
# CDFs never cross and KS == Kuiper. Sample 4 shares sample 2's center but is
# much wider, so its CDF crosses sample 2's and Kuiper exceeds KS.
SAMPLE_SIZE_PARAMS = [(0.8, 0.3), (1.2, 0.3), (1.6, 0.3), (1.2, 0.9)]

GRAINS_PER_SAMPLE = 40


def generate_example_rows():
    """Four samples of 40 grains; sample 3 also records roundness."""
    rows = []
    for s, (center, spread) in enumerate(SAMPLE_SIZE_PARAMS, start=1):
        for g in range(1, GRAINS_PER_SAMPLE + 1):
            rows.append({
                "sample": f"Sample {s}",
                "grain": f"G{g}",
                "size_mm": f"{max(0.05, random.gauss(center, spread)):.2f}",
                "color": random.choice(COLORS),
                "composition": random.choice(COMPOSITIONS),
                "roundness": random.choice(ROUNDNESS_LEVELS) if s == 3 else "",
            })
    return rows
