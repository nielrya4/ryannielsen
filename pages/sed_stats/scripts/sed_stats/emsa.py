"""
End-member splitting analysis (EMSA).

Kirchner & Allen (2020), Hydrol. Earth Syst. Sci. 24:17-39. End-member *mixing* says
what share of a stream's water came from each of two precipitation end members (snow
and rain, say), from the tracer alone. End-member *splitting* adds the fluxes and says
where each end member's water went: what share of the snow, and of the rain, left as
each kind of streamflow, and what share is left over for evapotranspiration.

This follows the equations of that paper (numbers in the comments are its, and its
supplement's "S" numbers), as implemented in Kirchner's EndSplit script, which is
distributed under the GNU General Public License v3 (Copyright 2020 ETH Zurich and
James Kirchner). Errors are propagated analytically, first order, as there. Nothing
here depends on pandas.

Terms: a *precipitation* series must have exactly two categories; *streamflow* has one
or more. Each category has tracer values (with weights, usually the water volume each
represents) and a flux series (depth or volume per time) from which its total is found.
"""
from dataclasses import dataclass, field

import numpy as np


@dataclass
class SplitResult:
    """Everything an analysis returns; rows are the streamflow categories, then the two derived ones."""
    precipitation: list                 # the two categories
    streamflow: list                    # the measured streamflow categories
    rows: list                          # streamflow + ["all_streamflow", "non_streamflow"]
    mixing: np.ndarray                  # (rows, 2)  share of each row's water from each precipitation category
    mixing_se: np.ndarray
    splitting: np.ndarray               # (rows, 2)  share of each precipitation category leaving as each row
    splitting_se: np.ndarray
    precipitation_mean: np.ndarray      # tracer, per precipitation category
    precipitation_se: np.ndarray
    streamflow_mean: np.ndarray         # tracer, per row
    streamflow_se: np.ndarray
    total_precipitation: np.ndarray     # per year, per precipitation category
    total_precipitation_se: np.ndarray
    total_streamflow: np.ndarray        # per year, per row (the last being what precipitation does not leave as streamflow)
    total_streamflow_se: np.ndarray
    free_mixing: np.ndarray = None      # (rows, 2)  what the equations of the paper give, before any holding
    held: list = field(default_factory=list)    # streamflow categories whose shares were held to 0-100 %
    water_limited: bool = False         # shares were also moved so no end member sends out more water than fell


def weighted_mean_and_se(values, weights=None):
    """
    Weighted mean and its standard error, where weights are amounts (volumes), not
    inverse variances. The usual weighted standard error tends to zero when one weight
    dominates, which is wrong here; this one grows instead (equations S4-S9).

    Returns:
        (mean, standard error); (nan, nan) if nothing is left once missing values are dropped
    """
    values = np.asarray(values, dtype=float)
    weights = np.ones(len(values)) if weights is None else np.asarray(weights, dtype=float)
    if len(values) != len(weights):
        raise ValueError("values and weights have different lengths")
    keep = ~(np.isnan(values) | np.isnan(weights))
    values, weights = values[keep], weights[keep]
    if len(values) == 0:
        return float("nan"), float("nan")
    if np.any(weights < 0):
        raise ValueError("Weights cannot be negative.")
    total = weights.sum()
    effective_n = total * total / (weights * weights).sum()                      # (S6)
    mean = (values * weights).sum() / total                                      # (S4)
    with np.errstate(divide="ignore", invalid="ignore"):
        variance = ((weights * (values - mean) ** 2).sum() / total
                    * effective_n / (effective_n - 1.0))                          # (S8)
        se = np.sqrt(variance / effective_n)                                      # (S9)
    return float(mean), float(se)


def _group(categories, levels):
    cats = np.asarray(categories)
    return [cats == level for level in levels]


def physical_fractions(free, flows, precip_totals, precision=None):
    """
    The share of each streamflow that came from the first precipitation end member, held to
    what is physically possible: between 0 and 1 for each streamflow, and with no end member
    sending out more water than fell. The equations of the paper put no such limits on the
    answer, and give a negative share, or more water leaving than arrived, whenever a
    streamflow's tracer lies outside the two end members or the fluxes do not add up.

    The answer is the closest one to the tracer's (`free`), in the sense of least squares weighted
    by `precision`: each share is clipped to 0-1, and if the water from either end member is still
    over its total, every share is moved along the same line, the better-measured ones less, until
    it fits. Where the free answer is already possible it is returned unchanged.

    Args:
        free: the share each streamflow's tracer gives, with no limits
        flows: each streamflow's yearly total
        precip_totals: (first end member's yearly total, the second's)
        precision: how well each streamflow's tracer is known (1 / its variance); equal if None

    Raises:
        ValueError: if the streamflow totals more than the precipitation, so no split can
            conserve the water
    """
    free = np.asarray(free, dtype=float)
    q = np.asarray(flows, dtype=float)
    p0, p1 = float(precip_totals[0]), float(precip_totals[1])
    total = q.sum()
    if total > (p0 + p1) * (1 + 1e-9):
        raise ValueError(
            f"The streamflow totals {total:,.4g} but the precipitation only {p0 + p1:,.4g}, so "
            "no split can account for the water. Check that the flux columns share units and "
            "cover the same period, or untick the limit to see the unconstrained numbers.")
    a = np.ones(len(free)) if precision is None else np.asarray(precision, dtype=float)
    a = np.where(np.isfinite(a) & (a > 0), a, np.nan)
    a = np.where(np.isnan(a), np.nanmedian(a) if np.isfinite(np.nanmedian(a)) else 1.0, a)

    def at(lam):
        return np.clip(free - lam * q / a, 0.0, 1.0)

    f = np.clip(free, 0.0, 1.0)
    low, high = total - p1, p0              # what the first end member may send out, in all
    sent = float((f * q).sum())
    if low - 1e-12 <= sent <= high + 1e-12:
        return f
    target = high if sent > high else low
    # `sent` falls as lam rises; find the lam that puts it exactly on the limit it passed.
    lo, hi = -1.0, 1.0
    while (at(lo) * q).sum() < target and lo > -1e15:
        lo *= 2
    while (at(hi) * q).sum() > target and hi < 1e15:
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        if (at(mid) * q).sum() > target:
            lo = mid
        else:
            hi = mid
    return at((lo + hi) / 2)


def end_member_splitting(precip_values, stream_values, precip_categories, stream_categories,
                         precip_flux, stream_flux, precip_flux_categories,
                         stream_flux_categories, precip_weights=None, stream_weights=None,
                         years=1.0, bounded=True, constrain_water=True):
    """
    The mixing and splitting fractions, with standard errors.

    Args:
        precip_values, stream_values: tracer values (a delta, or a concentration)
        precip_categories, stream_categories: the category of each value; exactly two
            precipitation categories
        precip_flux, stream_flux: flux series (depth or volume per time) and their categories,
            whose labels must be those of the tracer values
        precip_weights, stream_weights: weights for the tracer values (usually the water
            amount each represents); equal if left out
        years: how many years the flux series cover, to turn totals into yearly ones
        bounded: keep the shares physical (see `physical_fractions`): no negative share and no
            more than 100 %, and — with `constrain_water` — no end member sending out more water
            than fell. Where the paper's equations already give such an answer, the two agree
            exactly. False gives the equations as they are, with whatever they come to.
        constrain_water: apply the water limit too; leave it off when there is no flux column,
            since every row then counts as one unit of water and the totals mean nothing

    Raises:
        ValueError: for mismatched lengths or labels, not two precipitation categories, a
            category with fewer than two values (no standard error can be found), two
            precipitation end members with the same tracer value, or (when bounded and
            constraining water) more streamflow than precipitation
    """
    pv = np.asarray(precip_values, dtype=float)
    sv = np.asarray(stream_values, dtype=float)
    pw = np.ones(len(pv)) if precip_weights is None else np.asarray(precip_weights, dtype=float)
    sw = np.ones(len(sv)) if stream_weights is None else np.asarray(stream_weights, dtype=float)
    pc, sc = np.asarray(precip_categories), np.asarray(stream_categories)
    pf, sf = np.asarray(precip_flux, dtype=float), np.asarray(stream_flux, dtype=float)
    pfc, sfc = np.asarray(precip_flux_categories), np.asarray(stream_flux_categories)
    if years <= 0:
        raise ValueError("The number of years must be above zero.")
    if not (len(pv) == len(pw) == len(pc)) or not (len(sv) == len(sw) == len(sc)):
        raise ValueError("Each tracer series needs its weights and categories to match in length.")
    if len(pf) != len(pfc) or len(sf) != len(sfc):
        raise ValueError("Each flux series needs its categories to match in length.")

    precip_levels, stream_levels = list(np.unique(pfc)), list(np.unique(sfc))
    if set(precip_levels) != set(np.unique(pc)) or set(stream_levels) != set(np.unique(sc)):
        raise ValueError("The tracer values and the fluxes use different category labels.")
    if len(precip_levels) != 2:
        raise ValueError("Precipitation needs exactly two categories.")
    if not stream_levels:
        raise ValueError("Streamflow needs at least one category.")
    for name, categories, levels in (("precipitation", pc, precip_levels), ("streamflow", sc, stream_levels),
                                     ("precipitation flux", pfc, precip_levels),
                                     ("streamflow flux", sfc, stream_levels)):
        for level in levels:
            if (categories == level).sum() < 2:
                raise ValueError(f"'{level}' has fewer than two {name} values, so a standard "
                                 "error cannot be found.")

    ni, nj = 2, len(stream_levels)
    p_mean, p_se, p_tot, p_tot_se = (np.full(ni, np.nan) for _ in range(4))
    s_mean, s_se, s_tot, s_tot_se = (np.full(nj + 2, np.nan) for _ in range(4))

    for i, level in enumerate(precip_levels):
        mask = pc == level
        p_mean[i], p_se[i] = weighted_mean_and_se(pv[mask], pw[mask])
        mask = pfc == level
        mean, se = weighted_mean_and_se(pf[mask])
        p_tot[i], p_tot_se[i] = mean * mask.sum() / years, se * mask.sum() / years
    for j, level in enumerate(stream_levels):
        mask = sc == level
        s_mean[j], s_se[j] = weighted_mean_and_se(sv[mask], sw[mask])
        mask = sfc == level
        mean, se = weighted_mean_and_se(sf[mask])
        s_tot[j], s_tot_se[j] = mean * mask.sum() / years, se * mask.sum() / years

    if not np.isfinite(p_mean[0] - p_mean[1]) or abs(p_mean[0] - p_mean[1]) < 1e-12 * max(1.0, np.nanmax(np.abs(p_mean))):
        raise ValueError("The two precipitation end members have the same mean tracer value, so "
                         "the tracer cannot tell them apart.")

    with np.errstate(divide="ignore", invalid="ignore"):
        # All the streamflow together, and what precipitation does not leave as streamflow
        # (evapotranspiration, and any storage change, which the method cannot tell apart).
        q, q_se = s_tot[:nj], s_tot_se[:nj]
        all_q = np.nansum(q)
        all_q_se = np.sqrt(np.nansum(q_se ** 2))
        all_q_mean = np.nansum(s_mean[:nj] * q) / all_q
        all_q_mean_se = np.sqrt(np.nansum((s_se[:nj] * q / all_q) ** 2)
                                + np.nansum((s_mean[:nj] * q_se * (all_q - q) / all_q ** 2) ** 2))
        all_p = np.nansum(p_tot)
        all_p_se = np.sqrt(np.nansum(p_tot_se ** 2))
        all_p_mean = np.nansum(p_mean * p_tot) / all_p
        non_q = all_p - all_q
        non_q_se = np.sqrt(all_p_se ** 2 + all_q_se ** 2)
        non_q_mean = (all_p_mean * all_p - all_q_mean * all_q) / non_q
        non_q_mean_se = np.sqrt(
            (p_se[0] * p_tot[0] / non_q) ** 2 + (p_se[1] * p_tot[1] / non_q) ** 2
            + (all_q_mean_se * -all_q / non_q) ** 2
            + (p_tot_se[0] * (p_mean[0] - non_q_mean) / non_q) ** 2
            + (p_tot_se[1] * (p_mean[1] - non_q_mean) / non_q) ** 2
            + (all_q_se * (non_q_mean - all_q_mean) / non_q) ** 2)
        s_mean[nj], s_se[nj], s_tot[nj], s_tot_se[nj] = all_q_mean, all_q_mean_se, all_q, all_q_se
        s_mean[nj + 1], s_se[nj + 1], s_tot[nj + 1], s_tot_se[nj + 1] = non_q_mean, non_q_mean_se, non_q, non_q_se

        # End-member mixing
        mixing = np.full((nj + 2, ni), np.nan)
        mixing_se = np.full((nj + 2, ni), np.nan)
        gap = p_mean[0] - p_mean[1]
        for j in range(nj + 1):
            mixing[j, 0] = (s_mean[j] - p_mean[1]) / gap                                # (3)
            mixing[j, 1] = 1.0 - mixing[j, 0]
            mixing_se[j, 0] = np.sqrt((s_se[j] / gap) ** 2
                                      + (p_se[0] * (-mixing[j, 0] / gap)) ** 2
                                      + (p_se[1] * (p_mean[0] - s_mean[j]) / gap ** 2) ** 2)   # (S12)
            mixing_se[j, 1] = mixing_se[j, 0]
        n = nj + 1                                  # the row of what is not streamflow
        mixing[n, 0] = (p_tot[0] - all_q * (s_mean[nj] - p_mean[1]) / gap) / (p_tot.sum() - all_q)   # (8), (18)
        mixing_se[n, 0] = np.sqrt(
            (p_tot_se[0] * (1 - mixing[n, 0]) / non_q) ** 2
            + (p_tot_se[1] * mixing[n, 0] / non_q) ** 2
            + (s_tot_se[nj] * (mixing[n, 0] - mixing[nj, 0]) / non_q) ** 2
            + (s_se[nj] * all_q / gap / non_q) ** 2
            + (p_se[0] * all_q * mixing[nj, 0] / gap / non_q) ** 2
            + (p_se[1] * all_q * mixing[nj, 1] / (p_mean[1] - p_mean[0]) / non_q) ** 2)           # (S20)
        mixing[n, 1] = 1.0 - mixing[n, 0]
        mixing_se[n, 1] = mixing_se[n, 0]

        # End-member splitting
        splitting = np.full((nj + 2, ni), np.nan)
        splitting_se = np.full((nj + 2, ni), np.nan)
        for j in range(nj + 1):
            for i in range(ni):
                splitting[j, i] = mixing[j, i] * s_tot[j] / p_tot[i]                       # (4), (22)-(24)
                splitting_se[j, i] = abs(splitting[j, i]) * np.sqrt(
                    (mixing_se[j, i] / mixing[j, i]) ** 2 + (s_tot_se[j] / s_tot[j]) ** 2
                    + (p_tot_se[i] / p_tot[i]) ** 2)                                        # (S17)
        for i in range(ni):
            splitting[n, i] = 1.0 - splitting[nj, i]                                        # (24)
            splitting_se[n, i] = splitting_se[nj, i]

    free_mixing = mixing.copy()
    held = []
    water_limited = False
    if bounded:
        with np.errstate(divide="ignore", invalid="ignore"):
            q = s_tot[:nj]
            if constrain_water:
                precision = 1.0 / np.maximum(s_se[:nj], 1e-12 * abs(gap)) ** 2
                f = physical_fractions(mixing[:nj, 0], q, p_tot, precision)
            else:
                f = np.clip(mixing[:nj, 0], 0.0, 1.0)
            moved = np.abs(f - mixing[:nj, 0]) > 1e-12
            clipped = (mixing[:nj, 0] < 0) | (mixing[:nj, 0] > 1)
            held = [stream_levels[j] for j in range(nj) if clipped[j]]
            water_limited = bool(np.any(moved & ~clipped))
            if np.any(moved):
                mixing[:nj, 0], mixing[:nj, 1] = f, 1.0 - f
                sent = float((f * q).sum())
                mixing[nj, 0] = sent / all_q
                mixing[nj, 1] = 1.0 - mixing[nj, 0]
                mixing[n, 0] = (p_tot[0] - sent) / (p_tot.sum() - all_q)
                mixing[n, 1] = 1.0 - mixing[n, 0]
                for j in range(nj + 1):
                    for i in range(ni):
                        splitting[j, i] = mixing[j, i] * s_tot[j] / p_tot[i]
                for i in range(ni):
                    splitting[n, i] = 1.0 - splitting[nj, i]
                # A share held at a limit has no meaningful first-order error, nor does anything
                # worked out from it: those are left blank rather than quoted wrongly.
                for j in list(np.nonzero(moved)[0]) + [nj, n]:
                    mixing_se[j, :] = np.nan
                    splitting_se[j, :] = np.nan
                splitting_se[n, :] = np.nan

    return SplitResult(
        precipitation=precip_levels, streamflow=stream_levels,
        rows=stream_levels + ["all_streamflow", "non_streamflow"],
        mixing=mixing, mixing_se=mixing_se, splitting=splitting, splitting_se=splitting_se,
        precipitation_mean=p_mean, precipitation_se=p_se, streamflow_mean=s_mean, streamflow_se=s_se,
        total_precipitation=p_tot, total_precipitation_se=p_tot_se,
        total_streamflow=s_tot, total_streamflow_se=s_tot_se,
        free_mixing=free_mixing, held=held, water_limited=water_limited)
