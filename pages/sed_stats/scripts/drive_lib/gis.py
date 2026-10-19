"""
Google sign-in and the file picker.

Everything Google's own JavaScript touches stays in JavaScript. The token
client and the Picker hand back live SDK objects, and Pyodide probes an
incoming object for `next`, `get`, `has` and friends to decide how to wrap
it — the same boundary that breaks Tabulator's components. The shim below does
that work in JS and returns nothing but plain strings and dicts.

What crosses into Python: an access token string, and a picked file's
id/name/mimeType. Nothing else.

The token lives in a JS variable for the life of the page and is never written
to storage. Google Identity Services re-issues it silently when it expires, so
persisting it would add a theft risk and buy nothing.
"""
import js
from pyodide.ffi import to_js
from pyodide.http import pyfetch

# Google's own scripts. GIS carries the token client; api.js carries the Picker.
GIS_SRC = "https://accounts.google.com/gsi/client"
GAPI_SRC = "https://apis.google.com/js/api.js"

# Least privilege: the app sees a file only once the user picks it in Google's
# own dialog, or because the app created it. Not the user's whole Drive.
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"

# `email` buys the signed-in address, and nothing else — no name, no picture,
# no contacts. It is worth the extra consent line because people routinely have
# several Google accounts, and "which Drive am I about to write to?" should not
# be a guess. Drop it and the status just reads "Signed in".
SCOPE = f"openid email {DRIVE_SCOPE}"

USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"

# What survives a reload: a single flag saying the user opted in, never a
# token. Access tokens last about an hour, and a stored one is a credential
# sitting in localStorage for any XSS to collect — for no benefit, because
# Google re-issues one silently while the grant is live.
_REMEMBER_KEY = "sedStats.google.connected"

_SHIM_ID = "sed-stats-google-shim"
_SHIM_NAME = "__sedStatsGoogle"
_SHIM = """
window.__sedStatsGoogle = (function () {
  let config = null;
  let tokenClient = null;
  let accessToken = null;
  let grantedScopes = "";
  let pickerReady = false;
  let pickerPromise = null;
  let pending = null;

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      if (document.querySelector('script[src="' + src + '"]')) return resolve();
      const el = document.createElement("script");
      el.src = src;
      el.async = true;
      el.onload = resolve;
      el.onerror = function () { reject(new Error("could not load " + src)); };
      document.head.appendChild(el);
    });
  }

  function waitFor(test, label, timeoutMs) {
    return new Promise(function (resolve, reject) {
      const deadline = Date.now() + (timeoutMs || 15000);
      (function poll() {
        if (test()) return resolve();
        if (Date.now() > deadline) return reject(new Error(label + " never became ready"));
        setTimeout(poll, 50);
      })();
    });
  }

  // Sign-in needs Identity Services and nothing else. The Picker libraries
  // are a second network round trip that used to be awaited here, which put
  // them on the critical path of every sign-in even though most of a session
  // never opens the picker.
  async function ready(cfg) {
    config = cfg;
    await loadScript(cfg.gis_src);
    await waitFor(function () {
      return window.google && google.accounts && google.accounts.oauth2;
    }, "Google Identity Services", 20000);
    return true;
  }

  // Loaded on demand, and warmed in the background once signed in, so the
  // first "Open from Drive" usually finds it already there.
  function ensurePicker() {
    if (!pickerPromise) {
      pickerPromise = (async function () {
        await loadScript(config.gapi_src);
        await waitFor(function () { return window.gapi; }, "gapi", 20000);
        await new Promise(function (resolve) { gapi.load("picker", resolve); });
        pickerReady = true;
      })();
    }
    return pickerPromise;
  }

  function client() {
    if (tokenClient) return tokenClient;
    tokenClient = google.accounts.oauth2.initTokenClient({
      client_id: config.client_id,
      scope: config.scope,
      callback: function (resp) {
        if (resp.error) {
          if (pending) { pending.reject(new Error(resp.error)); pending = null; }
          return;
        }
        accessToken = resp.access_token;
        // Google grants scopes individually: the consent screen has a
        // checkbox per scope, so a "successful" sign-in can come back
        // without Drive access at all. resp.scope is what was actually
        // granted, which is the only thing worth trusting.
        grantedScopes = resp.scope || "";
        // Deliberately not awaited: warming it must not delay sign-in.
        try { ensurePicker(); } catch (e) {}
        if (pending) { pending.resolve(accessToken); pending = null; }
      },
      error_callback: function (err) {
        // Fires when the user closes or blocks the popup, which the success
        // callback never hears about — without this the promise hangs forever.
        if (pending) {
          pending.reject(new Error((err && err.type) || "popup closed"));
          pending = null;
        }
      },
    });
    return tokenClient;
  }

  function signIn(interactive) {
    return new Promise(function (resolve, reject) {
      // Only one request can be outstanding: the token client has a single
      // callback, so a second would strand the first waiting forever.
      if (pending) pending.reject(new Error("superseded by a new sign-in"));
      pending = { resolve: resolve, reject: reject };
      try {
        client().requestAccessToken({ prompt: interactive ? "consent" : "" });
      } catch (e) {
        pending = null;
        reject(e);
      }
    });
  }

  return {
    ready: ready,
    signIn: signIn,
    token: function () { return accessToken; },
    scopes: function () { return grantedScopes; },
    signedIn: function () { return !!accessToken; },

    signOut: function () {
      const token = accessToken;
      accessToken = null;
      grantedScopes = "";
      if (token && window.google && google.accounts && google.accounts.oauth2) {
        // Tell Google to drop the grant too, so signing out actually revokes
        // rather than only forgetting locally.
        try { google.accounts.oauth2.revoke(token); } catch (e) {}
      }
      return true;
    },

    // Resolves to a plain {id, name, mimeType} or null if the user cancelled.
    // `folders` switches it from choosing a file to choosing a destination.
    pick: async function (mimeTypes, folders) {
      if (!accessToken) throw new Error("not signed in");
      await ensurePicker();
      return new Promise(function (resolve, reject) {
        const view = new google.picker.DocsView(
          folders ? google.picker.ViewId.FOLDERS : google.picker.ViewId.DOCS);
        view.setIncludeFolders(true).setSelectFolderEnabled(!!folders);
        // List mode instead of the default grid: the grid fetches a thumbnail
        // per file from googleusercontent, which Firefox blocks cross-origin
        // anyway, so they cost a round trip each and deliver nothing.
        view.setMode(google.picker.DocsViewMode.LIST);
        if (folders) {
          view.setMimeTypes("application/vnd.google-apps.folder");
        } else if (mimeTypes && mimeTypes.length) {
          view.setMimeTypes(mimeTypes.join(","));
        }
        // The picker renders in its own iframe and reports failure only by
        // never opening, so a bad key or a disabled Picker API would leave
        // this promise pending forever and the button spinning.
        let opened = false;
        const timer = setTimeout(function () {
          if (!opened) {
            reject(new Error(
              "the Google file picker did not open after 30s — check that the " +
              "Google " +
              "Picker API is enabled for this project and that the API key " +
              "is valid for this origin"));
          }
        }, 30000);

        const picker = new google.picker.PickerBuilder()
          .addView(view)
          .setOAuthToken(accessToken)
          .setDeveloperKey(config.api_key)
          // Required alongside the drive.file scope: without it the granted
          // token cannot read what the user just picked.
          .setAppId(config.app_id)
          // Picker checks this against the hosting page; without it a page
          // served on a non-default port can silently fail to render.
          .setOrigin(window.location.protocol + "//" + window.location.host)
          .setCallback(function (data) {
            if (data.action === google.picker.Action.LOADED) {
              opened = true;
              clearTimeout(timer);
              return;
            }
            if (data.action === google.picker.Action.CANCEL) {
              clearTimeout(timer);
              return resolve(null);
            }
            if (data.action !== google.picker.Action.PICKED) return;
            clearTimeout(timer);
            const doc = data.docs && data.docs[0];
            resolve(doc ? {id: doc.id, name: doc.name, mimeType: doc.mimeType} : null);
          })
          .build();
        picker.setVisible(true);
      });
    },
  };
})();
"""


def _remember(connected):
    """Record, or clear, the fact that the user connected an account."""
    try:
        storage = js.window.localStorage
        if connected:
            storage.setItem(_REMEMBER_KEY, "1")
        else:
            storage.removeItem(_REMEMBER_KEY)
    except Exception:
        # Private windows and blocked site data make storage throw. Losing
        # the flag only costs one extra click, so it must never be fatal.
        pass


def _was_connected():
    try:
        return js.window.localStorage.getItem(_REMEMBER_KEY) == "1"
    except Exception:
        return False


def _shim():
    """
    The shim object, fetched by name.

    Not `js.window.__sedStatsGoogle`: inside a class body Python mangles any
    leading-double-underscore attribute, so that expression silently becomes
    `js.window._GoogleSession__sedStatsGoogle`. getattr sidesteps the rewrite.
    """
    return getattr(js.window, _SHIM_NAME)


def _ensure_shim():
    # Not `is None`: Pyodide represents JS null as a `jsnull` sentinel, which
    # is not Python None, so `is None` is always False and the script would
    # never be injected. Truthiness is correct for both null and a real node.
    if not js.document.getElementById(_SHIM_ID):
        script = js.document.createElement("script")
        script.id = _SHIM_ID
        script.textContent = _SHIM
        js.document.head.appendChild(script)

    if not hasattr(js.window, _SHIM_NAME):
        raise RuntimeError(
            "the Google sign-in helper script did not run — "
            "check the browser console for a script error")


class GoogleSession:
    """
    One page's Google sign-in.

    Usage:
        session = GoogleSession(client_id=..., api_key=..., app_id=...)
        await session.sign_in()
        picked = await session.pick_file(["text/csv"])
        session.sign_out()
    """

    def __init__(self, client_id: str, api_key: str, app_id: str,
                 scope: str = SCOPE):
        self.client_id = client_id
        self.api_key = api_key
        self.app_id = app_id
        self.scope = scope
        self._ready = False

    @property
    def configured(self) -> bool:
        """Whether a Cloud project has been supplied to sign in against."""
        return bool(self.client_id and self.api_key and self.app_id)

    async def _prepare(self):
        if self._ready:
            return
        if not self.configured:
            raise RuntimeError(
                "Google sign-in is not configured — set client_id, api_key "
                "and app_id from your Google Cloud project")
        _ensure_shim()
        await _shim().ready(to_js({
            "client_id": self.client_id,
            "api_key": self.api_key,
            "app_id": self.app_id,
            "scope": self.scope,
            "gis_src": GIS_SRC,
            "gapi_src": GAPI_SRC,
        }, dict_converter=js.Object.fromEntries))
        self._ready = True

    async def sign_in(self, interactive: bool = True) -> str:
        """Open Google's consent popup and return the access token."""
        await self._prepare()
        token = str(await _shim().signIn(interactive))
        _remember(True)
        return token

    async def restore(self) -> bool:
        """
        Re-establish a previous session without prompting.

        Google issues a fresh token with no UI at all while the grant and the
        browser's Google session are both alive, so a reload does not have to
        look like being signed out. If anything is missing — the grant was
        revoked, the session expired, a popup would be needed — this reports
        failure quietly and the user simply sees the sign-in button.
        """
        if not self.configured or not _was_connected():
            return False
        try:
            await self._prepare()
            await _shim().signIn(False)
            return self.signed_in
        except Exception:
            _remember(False)
            return False

    async def token(self, refresh: bool = False) -> str:
        """
        A live access token.

        Tokens last about an hour. `refresh=True` asks for a new one without
        prompting, which is what a 401 mid-session calls for.
        """
        await self._prepare()
        if refresh or not self.signed_in:
            return str(await _shim().signIn(False))
        return str(_shim().token())

    @property
    def granted_scopes(self):
        """The scopes Google actually granted, as a set."""
        if not self._ready:
            return set()
        return set(str(_shim().scopes() or "").split())

    @property
    def has_drive_access(self) -> bool:
        """
        Whether the granted token can actually reach Drive.

        Consent is per-scope, so signing in successfully proves nothing about
        Drive: declining just the Drive checkbox yields a perfectly valid token
        that 403s on every file call. Checking up front turns that into one
        clear message instead of a failure at each button.

        An empty scope list means Google did not say, not that it refused, so
        that case stays permissive and lets the API be the judge — better a
        clear 403 than a UI that disables itself for no visible reason.
        """
        granted = self.granted_scopes
        return not granted or DRIVE_SCOPE in granted

    @property
    def signed_in(self) -> bool:
        if not self._ready:
            return False
        return bool(_shim().signedIn())

    def sign_out(self):
        """Drop the token and revoke the grant with Google."""
        _remember(False)
        if self._ready:
            _shim().signOut()
        return self

    async def account_email(self):
        """
        The signed-in address, or None if it could not be read.

        Purely for display, so a failure here downgrades the status line rather
        than failing the sign-in that just succeeded.
        """
        try:
            token = await self.token()
            response = await pyfetch(
                USERINFO, headers={"Authorization": f"Bearer {token}"})
            if response.status >= 400:
                return None
            return (await response.json()).get("email")
        except Exception:
            return None

    async def pick_file(self, mime_types=None):
        """
        Show Google's file picker.

        Returns {"id", "name", "mimeType"}, or None if the user cancelled.
        """
        return await self._pick(mime_types, folders=False)

    async def pick_folder(self):
        """
        Show Google's folder picker, for choosing where to save.

        Returns {"id", "name", "mimeType"}, or None if the user cancelled.
        Picking a folder is also what grants the app permission to write into
        it under `drive.file`.
        """
        return await self._pick(None, folders=True)

    async def _pick(self, mime_types, folders):
        await self._prepare()
        picked = await _shim().pick(
            to_js(list(mime_types or [])), folders)
        # Not `is None`: a cancelled picker resolves with JS null, which
        # reaches Python as a `jsnull` sentinel that is not None.
        if not picked:
            return None
        return {"id": str(picked.id), "name": str(picked.name),
                "mimeType": str(picked.mimeType)}
