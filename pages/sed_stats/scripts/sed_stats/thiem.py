"""
Steady-state drawdown to a pumping well in a confined aquifer: the Thiem equation.

    s(r) = Q · ln(R / r) / (2π · K · b)          (any consistent units)

the drawdown s at distance r from a well pumping Q from an aquifer of hydraulic conductivity K
and thickness b, when the cone of depression reaches a radius R (the radius of influence, where
drawdown is zero). K · b is the transmissivity T. The drawdown is logarithmic in distance, so it
is a straight line on a semilog plot, and the contours round a single well are circles whose
radii are r = R · exp(-s · 2π K b / Q).

Two sets of units are offered:

  "us"  Q in gpm, lengths in feet, K in gpd/ft². Written as in Driscoll (1986, p. 214) and the
        usual hydrogeology course:   s = 528 · Q · log10(R / r) / (K · b).  The 528 is the
        conversion (1,440 min/day ÷ 2π, times ln 10 ≈ 527.7) rounded as the textbook rounds it.
  "si"  Q in m³/day, lengths in metres, K in m/day, with the equation exactly as above.

Assumptions of the equation itself: a confined aquifer of uniform thickness, homogeneous and
isotropic, a fully penetrating well, steady flow, and no regional gradient (a sloping water
table or potentiometric surface is ignored). It does not apply as it stands to an unconfined
aquifer, where the drawdown is a sizeable fraction of the saturated thickness, or to flow that
is still changing (that is the Theis equation).
"""
import math

UNITS = {
    "us": {"label": "US (gpm, ft, gpd/ft²)", "flow": "gpm", "length": "ft", "k": "gpd/ft²"},
    "si": {"label": "SI (m³/day, m, m/day)", "flow": "m³/day", "length": "m", "k": "m/day"},
}

# s = FACTOR * Q * log10(R / r) / (K * b)
FACTOR = {"us": 528.0, "si": math.log(10.0) / (2.0 * math.pi)}


def _factor(units):
    if units not in FACTOR:
        raise ValueError(f"Unknown units '{units}'.")
    return FACTOR[units]


def _check(**values):
    for name, value in values.items():
        if value is None or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a number above zero.")


def conductivity(flow, thickness, radius_of_influence, well_radius, drawdown_at_well, units="us"):
    """
    Hydraulic conductivity from the drawdown measured in the pumping well itself (the first
    question of the usual problem set).

    Raises:
        ValueError: for a non-positive input, or a radius of influence not beyond the well
    """
    _check(flow=flow, thickness=thickness, radius_of_influence=radius_of_influence,
           well_radius=well_radius, drawdown_at_well=drawdown_at_well)
    if radius_of_influence <= well_radius:
        raise ValueError("The radius of influence must be larger than the well's radius.")
    return (_factor(units) * flow * math.log10(radius_of_influence / well_radius)
            / (thickness * drawdown_at_well))


def drawdown(distance, flow, conductivity_, thickness, radius_of_influence, well_radius=None,
             units="us"):
    """
    Drawdown at `distance` from the well (a number or a NumPy array). Beyond the radius of
    influence it is zero; closer than the well's radius it is the drawdown at the well's wall.
    """
    import numpy as np
    _check(flow=flow, conductivity=conductivity_, thickness=thickness,
           radius_of_influence=radius_of_influence)
    r = np.asarray(distance, dtype=float)
    if well_radius is not None:
        r = np.maximum(r, well_radius)
    if np.any(r <= 0):
        raise ValueError("Distances from the well must be above zero.")
    s = _factor(units) * flow * np.log10(radius_of_influence / r) / (conductivity_ * thickness)
    s = np.maximum(s, 0.0)
    return float(s) if s.ndim == 0 else s


def distance_for_drawdown(level, flow, conductivity_, thickness, radius_of_influence, units="us"):
    """The distance from the well at which the drawdown is `level` (the radius of that contour)."""
    _check(level=level, flow=flow, conductivity=conductivity_, thickness=thickness,
           radius_of_influence=radius_of_influence)
    return radius_of_influence * 10.0 ** (-level * conductivity_ * thickness
                                          / (_factor(units) * flow))


def contour_radii(interval, flow, conductivity_, thickness, radius_of_influence, well_radius,
                  units="us"):
    """
    [(level, radius)] for the contours at every `interval` of drawdown that lie in the aquifer,
    that is, between the well's wall and the radius of influence. A level at or above the
    drawdown in the well itself is inside the well and has no contour.
    """
    _check(interval=interval)
    wall = drawdown(well_radius, flow, conductivity_, thickness, radius_of_influence, units=units)
    found, k = [], 1
    while k * interval <= wall + 1e-9 and k < 500:
        level = k * interval
        found.append((level, distance_for_drawdown(level, flow, conductivity_, thickness,
                                                   radius_of_influence, units)))
        k += 1
    return found


def transmissivity(conductivity_, thickness):
    """T = K · b, in the units of K times the units of b."""
    return conductivity_ * thickness


def parse_distances(text):
    """
    Distances typed as "200, 600" (commas, spaces or semicolons) as floats, in the order
    given.

    Raises:
        ValueError: naming the entry that is not a positive number
    """
    found = []
    for token in str(text or "").replace(";", ",").replace("\n", ",").split(","):
        for piece in token.split():
            try:
                value = float(piece)
            except ValueError:
                raise ValueError(f"'{piece}' is not a distance.") from None
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"'{piece}' is not a distance above zero.")
            found.append(value)
    return found
