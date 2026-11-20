"""
Grouping dated values into periods for a boxplot: each calendar month of the record, the twelve
months of the year pooled over the years, the seasons, years, or water years.

Each period is a (sort key, label) pair so the boxes can be put in time order whatever their
labels are.
"""
from . import dates as dt

PERIODS = {
    "month": "Each month of the record (2021-03)",
    "month_of_year": "Month of the year, all years together (Jan … Dec)",
    "season": "Season of the year, all years together",
    "year": "Calendar year",
    "water_year": "Water year",
}


def period_of(when, period, water_year_start=10):
    """(sort key, label) of the period `when` falls in."""
    if period == "month":
        return (when.year, when.month), f"{when.year}-{when.month:02d}"
    if period == "month_of_year":
        return (when.month,), dt.MONTH_NAMES[when.month - 1][:3]
    if period == "season":
        order = {"Winter": 0, "Spring": 1, "Summer": 2, "Autumn": 3}
        name = dt.season(when)
        return (order[name],), name
    if period == "year":
        return (when.year,), str(when.year)
    if period == "water_year":
        wy = dt.water_year(when, water_year_start)
        return (wy,), f"WY{wy}"
    raise ValueError(f"Unknown period '{period}'.")


def month_of_year_order(start_month=1):
    """January … December starting from `start_month`, for a water-year-ordered climatology."""
    return [(m - 1) % 12 + 1 for m in range(start_month, start_month + 12)]
