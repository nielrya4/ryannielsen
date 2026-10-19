"""
Google Drive access for Antioch apps.

Components:
    GoogleSession - sign-in, access tokens, and the Google file picker
    DriveClient   - download and upload single files through the Drive v3 API
    PICKABLE      - the mime types the picker offers for spreadsheet data

The OAuth flow is the browser one: no client secret exists, the access token
is held in memory for the life of the page and never stored, and the Drive
scope is `drive.file`, so the app sees only the files the user picks and the
files it creates. `email` rides along so the UI can name the signed-in
account.
"""
from .gis import GoogleSession, DRIVE_SCOPE, SCOPE
from .files import DriveClient, DriveError, EXPORT_AS, PICKABLE

__all__ = [
    'GoogleSession',
    'SCOPE',
    'DRIVE_SCOPE',
    'DriveClient',
    'DriveError',
    'EXPORT_AS',
    'PICKABLE',
]

__version__ = '0.1.0'
