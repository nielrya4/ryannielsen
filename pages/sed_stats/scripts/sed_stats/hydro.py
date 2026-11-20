"""
Calculations behind the hydrograph and hyetograph: the typical year, smoothing, monthly
precipitation totals. No plotting and no browser.

A *hydrograph* is discharge through time; a *hyetograph* is precipitation through time, drawn
hanging from the top of the same chart so that rain and the flow it feeds read together.
"""
import statistics
from datetime import timedelta

from . import dates


def median_spacing(times):
    """The median gap between consecutive distinct times, or None for fewer than two."""
    ordered = sorted(set(times))
    gaps = [b - a for a, b in zip(ordered, ordered[1:])]
    return statistics.median(gaps) if gaps else None


def bar_edges(times, at="start"):
    """
    (centre, width) for a bar at each time, given where in its interval the time is recorded:
    "start" (hourly rain stamped at the start of the hour, a month stamped 1 January), "middle"
    or "end". The width is the median spacing between the times, so bars touch.
    """
    width = median_spacing(times)
    if width is None:
        width = timedelta(days=1)
    shift = {"start": width / 2, "middle": timedelta(0), "end": -width / 2}[at]
    return [t + shift for t in times], width


def annual_flow(points, window=10, start_month=10):
    """
    The typical year of a flow record: the mean at each calendar day over every year,
    smoothed over `window` days (centred; the days with data inside it are averaged).

    Args:
        points: [(datetime, value)]; 29 February is left out so that years line up
        window: days in the smoothing window; 1 for none

    Returns:
        (days, values) with days the day of the water year, in order, for the days that have data
    """
    by_day = {}
    for when, value in points:
        day = dates.reference_day(when.month, when.day, start_month)
        if day is not None and value is not None:
            by_day.setdefault(day, []).append(value)
    days = sorted(by_day)
    means = {d: sum(by_day[d]) / len(by_day[d]) for d in days}
    if window <= 1:
        return days, [means[d] for d in days]
    half = int(window) // 2
    smoothed = []                                    # centred; an even window leans one day earlier
    for d in days:
        low, high = d - half, d + (half - 1 if int(window) % 2 == 0 else half)
        inside = [means[k] for k in range(low, high + 1) if k in means]
        smoothed.append(sum(inside) / len(inside))
    return days, smoothed


def monthly_mean_totals(points, start_month=10):
    """
    The typical month of precipitation: each year's total for the month, averaged over the
    years that have that month.

    Returns:
        {month: (mean total, years averaged)} for the months with any data
    """
    totals = {}
    for when, value in points:
        if value is not None:
            totals[(when.year, when.month)] = totals.get((when.year, when.month), 0.0) + value
    by_month = {}
    for (_, month), total in totals.items():
        by_month.setdefault(month, []).append(total)
    return {m: (sum(v) / len(v), len(v)) for m, v in by_month.items()}
