"""
Stable-isotope formulas: scales, fractionation, trophic position, lipid correction,
carbonate thermometry.

Each constant and equation here was checked against a source, and says which. Where
the literature offers several calibrations, the ones that could be confirmed are
offered and the rest are left to the user's own coefficients, rather than shipping
numbers nobody checked.

Delta values are in per mil (‰). Scales: VPDB (carbon, carbonate oxygen), VSMOW
(water and phosphate oxygen, hydrogen), AIR (nitrogen).
"""
import math

# --- oxygen scales ---------------------------------------------------------------
# delta18O(VSMOW) = a * delta18O(VPDB) + b.
#   Coplen, Kendall & Hopple (1983), Nature 302:236-238: 1.03091 and 30.91.
#   The IUPAC-recommended values: 1.03092 and 30.92.
OXYGEN_SCALE_CONVERSIONS = {
    "coplen": (1.03091, 30.91),
    "iupac": (1.03092, 30.92),
}

# Water on the SMOW scale is taken to the PDB scale by subtracting 0.27 when it is
# set beside carbonate (O'Neil et al. 1969; Shackleton 1974; as in Anand et al. 2003).
WATER_SMOW_TO_PDB = 0.27

# --- elemental ------------------------------------------------------------------
# Standard atomic weights, to turn a weight ratio into an atomic one.
ATOMIC_WEIGHT_C = 12.011
ATOMIC_WEIGHT_N = 14.007

# DeNiro (1985): bone collagen whose atomic C:N lies outside 2.9-3.6 is not well
# preserved. (For modern tissue a narrower window, 3.0-3.3, has been proposed by
# Guiry & Szpak 2020, so the range is always the user's to set.)
COLLAGEN_CN_RANGE = (2.9, 3.6)

# --- lipid normalisation --------------------------------------------------------
# Post et al. (2007), Oecologia 152:179-189, for aquatic animals:
#   delta13C_normalised = delta13C_untreated - 3.32 + 0.99 * C:N
# The coefficients were checked against that paper's own appendix: regressing the
# measured shift on lipid extraction against C:N for its 22 aquatic animals with a C:N
# gives -3.32 + 0.99 * C:N (R2 = 0.91), while its 14 terrestrial animals show no
# relation (R2 = 0.00). Its data reach C:N 6.9, so it should not be extrapolated far beyond.
LIPID_INTERCEPT = -3.32
LIPID_SLOPE = 0.99

# --- trophic position -----------------------------------------------------------
# Post (2002), Ecology 83:703-718: TP = lambda + (d15N_consumer - d15N_base) / Dn,
# lambda the trophic position of the baseline organism (1 for a primary producer, 2
# for a primary consumer) and Dn the enrichment in 15N per trophic level, 3.4 per mil
# on average.
DEFAULT_ENRICHMENT = 3.4

# --- carbonate thermometry -------------------------------------------------------
# Shackleton (1974), after O'Neil et al. (1969), with calcite on the VPDB scale and
# water on the VSMOW scale less 0.27:
#   T = 16.9 - 4.38 x + 0.10 x^2,   x = d18Oc - (d18Ow - 0.27)
SHACKLETON = (16.9, -4.38, 0.10)
# Kim & O'Neil (1997), GCA 61:3461-3475, synthetic calcite, both on VSMOW:
#   1000 ln(alpha) = 18.03 (10^3 / T) - 32.42,   T in kelvin
# and the same data recalculated with the current IUPAC acid fractionation factor
# (1.010254, against the 1.01050 they used): 18.04 and 32.18.
KIM_ONEIL = (18.03, 32.42)
KIM_ONEIL_RECALCULATED = (18.04, 32.18)

KELVIN = 273.15


def vpdb_to_vsmow(delta, which="coplen"):
    a, b = OXYGEN_SCALE_CONVERSIONS[which]
    return a * delta + b


def vsmow_to_vpdb(delta, which="coplen"):
    a, b = OXYGEN_SCALE_CONVERSIONS[which]
    return (delta - b) / a


def alpha(delta_a, delta_b):
    """The fractionation factor of A against B: (1000 + dA) / (1000 + dB)."""
    return (1000.0 + delta_a) / (1000.0 + delta_b)


def thousand_ln_alpha(delta_a, delta_b):
    """1000 ln(alpha), close to the plain difference for small fractionations."""
    return 1000.0 * math.log(alpha(delta_a, delta_b))


def atomic_cn(weight_percent_c, weight_percent_n):
    """Atomic C:N from weight percent carbon and nitrogen."""
    return (weight_percent_c / ATOMIC_WEIGHT_C) / (weight_percent_n / ATOMIC_WEIGHT_N)


def lipid_normalised(d13c, cn):
    """Post et al. (2007) lipid normalisation of delta13C from atomic C:N."""
    return d13c + LIPID_INTERCEPT + LIPID_SLOPE * cn


def trophic_position(d15n, baseline, baseline_position=2.0, enrichment=DEFAULT_ENRICHMENT):
    return baseline_position + (d15n - baseline) / enrichment


def temperature_polynomial(d_calcite_vpdb, d_water_vsmow, a, b, c=0.0):
    """T = a + b x + c x^2, x = d18Oc(VPDB) - (d18Ow(VSMOW) - 0.27), in degrees C."""
    x = d_calcite_vpdb - (d_water_vsmow - WATER_SMOW_TO_PDB)
    return a + b * x + c * x * x


def temperature_shackleton(d_calcite_vpdb, d_water_vsmow):
    return temperature_polynomial(d_calcite_vpdb, d_water_vsmow, *SHACKLETON)


def temperature_kim_oneil(d_calcite_vsmow, d_water_vsmow, constants=KIM_ONEIL):
    """
    Temperature in degrees C from 1000 ln(alpha) = A (10^3 / T) - B, with calcite and
    water both on the VSMOW scale.

    Raises:
        ValueError: if the fractionation is so small the equation has no temperature
    """
    slope, intercept = constants
    ln_alpha = thousand_ln_alpha(d_calcite_vsmow, d_water_vsmow)
    if ln_alpha + intercept <= 0:
        raise ValueError("The calcite-water fractionation is too small for this equation.")
    return slope * 1000.0 / (ln_alpha + intercept) - KELVIN
