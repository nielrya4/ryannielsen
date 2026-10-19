"""
Reading and writing single files in Google Drive.

web_os mounts Drive as a whole filesystem; sed/stats only ever wants one file
at a time — open a spreadsheet the user picked, or write a result back out — so
this is the two-call version rather than a VFS.

The REST calls live in Python (pyfetch gives bytes back cleanly); only the
OAuth popup and the Picker need JavaScript, and those are in `gis`.
"""
import json

import js
from pyodide.http import pyfetch

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"

# Google's own document formats hold no bytes to download — asking for their
# media gives a 403. They have to be converted on the way out instead.
EXPORT_AS = {
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
    "application/vnd.google-apps.document": ("text/plain", ".txt"),
}

# What the picker will show. Drive reports .xls/.xlsx with these types, and
# hand-made CSVs are frequently mislabelled text/plain.
PICKABLE = [
    "text/csv",
    "text/plain",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.google-apps.spreadsheet",
]


class DriveError(RuntimeError):
    pass


class DriveClient:
    """Single-file reads and writes against Drive v3."""

    def __init__(self, session):
        self.session = session

    async def _fetch(self, url, **kwargs):
        """
        A Drive request, retried once on 401 with a fresh token.

        Access tokens expire after about an hour, which a long session will
        cross. The retry turns that into a hiccup instead of an error the user
        has to resolve by signing in again.
        """
        base = dict(kwargs.pop("headers", {}))

        def authorized(token):
            # A fresh dict per attempt: the first one has already been handed
            # to fetch, and reusing it would edit a request in flight.
            return dict(base, Authorization=f"Bearer {token}")

        response = await pyfetch(
            url, headers=authorized(await self.session.token()), **kwargs)

        if response.status == 401:
            token = await self.session.token(refresh=True)
            response = await pyfetch(url, headers=authorized(token), **kwargs)

        if response.status >= 400:
            raise DriveError(await _describe(response))
        return response

    # ------------------------------------------------------------------ read

    async def download(self, file_id, mime_type=None):
        """
        Fetch a file's contents.

        Returns (filename, payload) where payload is `str` for text formats and
        `bytes` for the binary ones, matching what `parse_file` expects.
        """
        meta = await self.metadata(file_id)
        name = meta.get("name") or file_id
        mime_type = mime_type or meta.get("mimeType", "")

        if mime_type in EXPORT_AS:
            export_mime, suffix = EXPORT_AS[mime_type]
            url = (f"{API}/files/{file_id}/export"
                   f"?mimeType={js.encodeURIComponent(export_mime)}")
            # A Google-native file carries no extension, so parse_file would
            # have nothing to dispatch on.
            if not name.lower().endswith(suffix):
                name += suffix
            response = await self._fetch(_bust(url), **_NO_CACHE)
            return name, await response.string()

        url = f"{API}/files/{file_id}?alt=media"
        response = await self._fetch(_bust(url), **_NO_CACHE)
        if name.lower().endswith(".csv") or mime_type.startswith("text/"):
            return name, await response.string()
        return name, await response.bytes()

    async def metadata(self, file_id):
        response = await self._fetch(
            _bust(f"{API}/files/{file_id}?fields=id,name,mimeType,modifiedTime"),
            **_NO_CACHE)
        return await response.json()

    # ----------------------------------------------------------------- write

    async def upload(self, name, content, mime_type="text/csv", folder_id=None):
        """
        Create a new file in Drive and return its metadata.

        Always a new file, never an overwrite: under the `drive.file` scope the
        app can only touch what the user picked or what it made, and silently
        replacing a picked file is not what "save" should mean here.
        """
        metadata = {"name": name, "mimeType": mime_type}
        if folder_id:
            metadata["parents"] = [folder_id]

        # A multipart upload sends the metadata and the bytes together, so the
        # file never exists in a half-made state.
        boundary = "sedstats-boundary-3f1c9a"
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
            json.dumps(metadata).encode(),
            f"\r\n--{boundary}\r\n".encode(),
            f"Content-Type: {mime_type}\r\n\r\n".encode(),
            content.encode() if isinstance(content, str) else content,
            f"\r\n--{boundary}--\r\n".encode(),
        ])

        response = await self._fetch(
            f"{UPLOAD}/files?uploadType=multipart&fields=id,name,webViewLink",
            method="POST",
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
            body=_as_js_bytes(body),
        )
        return await response.json()


# Drive serves file media without a no-cache header, so a browser will happily
# hand back a stale copy of a file that was edited since it was last read.
# no-store alone is not enough in practice, hence the unique parameter.
_NO_CACHE = {"cache": "no-store"}


def _bust(url):
    """Append a unique parameter so no layer can serve a cached response."""
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}t={js.Date.now()}"


def _as_js_bytes(data):
    array = js.Uint8Array.new(len(data))
    array.assign(data)
    return array


# Google's 403s are indistinguishable without reading the reason, and the two
# common ones need completely different fixes from the person seeing them.
_HINTS = (
    ("insufficientpermissions",
     "the signed-in account did not grant Drive access — sign out, sign in "
     "again, and tick the Google Drive permission"),
    ("insufficient permission",
     "the signed-in account did not grant Drive access — sign out, sign in "
     "again, and tick the Google Drive permission"),
    ("has not been used in project",
     "enable the Google Drive API for this project in the Cloud console"),
    ("accessnotconfigured",
     "enable the Google Drive API for this project in the Cloud console"),
    ("daily limit",
     "the API key is missing or restricted — check it in the Cloud console"),
)


async def _describe(response):
    """Google's error JSON, if it sent any, else the bare status."""
    message = ""
    try:
        payload = await response.json()
        error = payload.get("error", {})
        message = error.get("message") or ""
        reasons = " ".join(
            str(item.get("reason", "")) for item in error.get("errors", []))
    except Exception:
        reasons = ""

    described = f"Drive error {response.status}"
    if message:
        described += f": {message}"

    haystack = f"{message} {reasons}".lower()
    for needle, hint in _HINTS:
        if needle in haystack:
            return f"{described} — {hint}"
    return described
