"""
Sed/Stats project files (.sedprj).

A project is the spreadsheet plus the options of each output generated from
it, as one JSON document. Plots themselves are not stored: they are rebuilt
from the data and the recorded options.

Components:
    dump_project  - serialize a project to text
    load_project  - parse and validate text into a Project
    Project       - the parsed result
    ProjectError  - raised for anything that is not a usable project file
"""
from .sedprj import (
    EXTENSION, FORMAT, MIME_TYPE, VERSION, Project, ProjectError,
    dump_project, load_project, project_filename,
)

__all__ = [
    'EXTENSION', 'FORMAT', 'MIME_TYPE', 'VERSION',
    'Project', 'ProjectError',
    'dump_project', 'load_project', 'project_filename',
]
