"""
The .sedprj file format.

    {
      "format": "sedstats-project",
      "version": 1,
      "name": "Snake River",
      "saved": "2026-10-10T14:03:22Z",
      "columns": ["Sample", "polymer", "Ti"],
      "rows": [{"Sample": "A", "polymer": "PE", "Ti": 21.3}, ...],
      "workflow": {"version": 2,
                   "steps": [{"id": "s1", "tool": "distribution", "title": "...",
                              "inputs": {"table": ["data"]}, "options": {...}}, ...]}
    }

`columns` fixes the column order, which a row's own keys cannot do for a
column that is empty in the first row. `workflow` is the chain of steps from the
Workflow tab (see `workflow_lib`), including the tools laid in as groups; it is
optional, so a file written before workflows existed still opens, and a reader that
does not know the key simply ignores it.

Older files also have a `"history": [{"tool": "mds", "title": "...", "options": {...}}, ...]`,
the outputs that used to live on a separate Outputs tab, each `tool` a dashboard tool key and
`options` what its dialog collected. It is still read, so those files open: the app adds each as
a tool to the workflow. It is no longer written, because a step's output is part of the
workflow now.

Plain JSON on purpose: a project can be read, diffed and repaired by hand, and
a future version can add keys without breaking this reader. A file written by
a newer version is refused rather than half-read.
"""
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

FORMAT = "sedstats-project"
VERSION = 1
EXTENSION = ".sedprj"
# A type of our own, so a Drive search can find projects without relying on
# how Drive tokenizes a file name.
MIME_TYPE = "application/vnd.sedstats.project+json"


class ProjectError(ValueError):
    """The text is not a project this version can open."""


@dataclass
class Project:
    name: str
    rows: list
    columns: list
    history: list = field(default_factory=list)
    saved: str = ""
    workflow: dict = None      # {"steps": [...]} or None; see workflow_lib


def project_filename(name):
    """`name` with the project extension, added only if it is missing."""
    name = str(name or "").strip() or "sed-stats-project"
    return name if name.lower().endswith(EXTENSION) else name + EXTENSION


def dump_project(name, rows, history=(), saved=None, workflow=None):
    """
    Serialize a project.

    Args:
        name: the project's display name
        rows: the spreadsheet, one dict per row
        history: [{"tool", "title", "options"}, ...]; no longer written by the app (see the
            module notes), accepted so an old project can be re-saved
        saved: ISO timestamp; defaults to now (UTC)
        workflow: the Workflow tab's state, {"steps": [...], and optionally the
            user's own "tools": [...]}; left out of the file when it has neither
    """
    rows = [dict(row) for row in rows or []]
    columns = _columns_of(rows)
    document = {
        "format": FORMAT,
        "version": VERSION,
        "name": str(name or ""),
        "saved": saved or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "columns": columns,
        "rows": [{column: _clean(row.get(column, "")) for column in columns}
                 for row in rows],
    }
    if history:
        document["history"] = [_clean_entry(entry) for entry in history]
    if workflow and (workflow.get("steps") or workflow.get("tools")):
        document["workflow"] = _clean(workflow)
    # allow_nan=False would raise on a stray NaN; _clean has already removed
    # them, so this is a guard that the file stays valid JSON for other readers.
    return json.dumps(document, indent=1, allow_nan=False)


def load_project(text):
    """
    Parse project text.

    Raises:
        ProjectError: if it is not JSON, not a Sed/Stats project, from a newer
            version, or has no usable spreadsheet
    """
    try:
        document = json.loads(text)
    except (TypeError, ValueError):
        raise ProjectError("This is not a valid project file (it is not JSON).")
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise ProjectError("This file is not a Sed/Stats project.")

    version = document.get("version")
    if not isinstance(version, int) or version < 1:
        raise ProjectError("This project file has no valid version.")
    if version > VERSION:
        raise ProjectError(
            f"This project was saved by a newer version of Sed/Stats "
            f"(file version {version}; this one reads up to {VERSION}).")

    raw_rows = document.get("rows")
    if not isinstance(raw_rows, list) or not all(isinstance(r, dict) for r in raw_rows):
        raise ProjectError("This project has no readable spreadsheet.")

    columns = document.get("columns")
    if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
        columns = _columns_of(raw_rows)
    else:
        # Keep any column a row has that `columns` forgot, after the listed ones.
        columns = columns + [c for c in _columns_of(raw_rows) if c not in columns]
    rows = [{column: row.get(column, "") for column in columns} for row in raw_rows]

    history = [entry for entry in document.get("history") or []
               if isinstance(entry, dict) and isinstance(entry.get("tool"), str)
               and isinstance(entry.get("options"), dict)]

    workflow = document.get("workflow")
    if not (isinstance(workflow, dict) and isinstance(workflow.get("steps"), list)):
        workflow = None

    return Project(
        name=str(document.get("name") or ""),
        rows=rows,
        columns=columns,
        history=history,
        saved=str(document.get("saved") or ""),
        workflow=workflow,
    )


def _columns_of(rows):
    """Every key in the rows, in first-seen order."""
    seen = {}
    for row in rows:
        for key in row:
            seen.setdefault(str(key), None)
    return list(seen)


def _clean_entry(entry):
    return {"tool": str(entry.get("tool", "")),
            "title": str(entry.get("title", "")),
            "options": _clean(entry.get("options") or {})}


def _clean(value):
    """Reduce to what JSON can hold: NaN and infinity become blank."""
    if hasattr(value, "item") and not isinstance(value, (dict, list, tuple, set, str)):
        value = value.item()  # a numpy scalar
    if isinstance(value, float):
        return value if math.isfinite(value) else ""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(v) for v in value]
    return str(value)
