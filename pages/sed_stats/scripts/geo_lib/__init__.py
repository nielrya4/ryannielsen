"""
Geography for the Maps tab: DEMs, watershed delineation, precomputed basins, gauges and climate.

The arithmetic and parsing (`terrain`, `watershed`, `geometry`, `series`, and the `parse_*` and
`*_streams` functions of `basins`, `gauges` and `climate`) never touch the browser and are
tested without it; `net` and `dem` are the only modules that fetch.
"""
