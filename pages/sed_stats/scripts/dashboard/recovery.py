"""
A recovery copy of the work in progress, kept in the browser's IndexedDB.

IndexedDB rather than localStorage: a project with thousands of grains is
megabytes, past what localStorage will hold, and IndexedDB stores it without
blocking the page. One entry is kept, the latest unsaved state, written while
there are unsaved changes and cleared once they are saved.

Everything here is best effort. Private windows, blocked site data and a full
disk all make IndexedDB fail, and losing the recovery copy must never get in
the way of the app, so every failure becomes "nothing stored".
"""
import js
from pyodide.ffi import to_js

_SHIM_ID = "sedstats-recovery-shim"
_SHIM_NAME = "__sedStatsRecovery"

_SHIM = """
(function () {
  if (window.__sedStatsRecovery) return;
  const DB = 'sedstats', STORE = 'recovery', KEY = 'latest';

  function open() {
    return new Promise(function (resolve, reject) {
      const request = indexedDB.open(DB, 1);
      request.onupgradeneeded = function () { request.result.createObjectStore(STORE); };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
      request.onblocked = function () { reject(new Error('IndexedDB is blocked')); };
    });
  }

  // Resolves once the transaction has committed, not merely once the request
  // was queued, so a caller that awaits a write knows it is on disk.
  function run(mode, work) {
    return open().then(function (db) {
      return new Promise(function (resolve, reject) {
        const tx = db.transaction(STORE, mode);
        const request = work(tx.objectStore(STORE));
        tx.oncomplete = function () { db.close(); resolve(request && request.result); };
        tx.onerror = tx.onabort = function () { db.close(); reject(tx.error); };
      });
    });
  }

  window.__sedStatsRecovery = {
    put: function (value) { return run('readwrite', function (s) { return s.put(value, KEY); }); },
    get: function () { return run('readonly', function (s) { return s.get(KEY); }); },
    clear: function () { return run('readwrite', function (s) { return s.delete(KEY); }); },
  };

  // Read by the beforeunload handler below; Python keeps it current.
  window.__sedUnsaved = false;
  window.addEventListener('beforeunload', function (event) {
    if (window.__sedUnsaved) {
      event.preventDefault();
      event.returnValue = '';
      return '';
    }
  });
})();
"""


def _ensure_shim():
    if not js.document.getElementById(_SHIM_ID):
        script = js.document.createElement("script")
        script.id = _SHIM_ID
        script.textContent = _SHIM
        js.document.head.appendChild(script)
    return getattr(js.window, _SHIM_NAME, None)


def set_unsaved_flag(unsaved):
    """Tell the browser whether leaving the page would lose work."""
    try:
        _ensure_shim()
        js.window.__sedUnsaved = bool(unsaved)
    except Exception:
        pass


class RecoveryStore:
    """
    The one recovery entry.

    An entry is {"text", "name", "file_id", "saved_at", "rows", "outputs"}:
    `text` is a complete project (see `project_lib`), so restoring is just
    opening it.
    """

    async def put(self, entry):
        """Store `entry`; returns whether it was written."""
        try:
            shim = _ensure_shim()
            await shim.put(to_js(entry, dict_converter=js.Object.fromEntries))
            return True
        except Exception:
            return False

    async def get(self):
        """The stored entry as a dict, or None."""
        try:
            shim = _ensure_shim()
            found = await shim.get()
            # A missing key is JS undefined or null; a real entry is an object.
            if not found or not hasattr(found, "to_py"):
                return None
            entry = found.to_py()
            return entry if isinstance(entry, dict) and entry.get("text") else None
        except Exception:
            return None

    async def clear(self):
        try:
            shim = _ensure_shim()
            await shim.clear()
            return True
        except Exception:
            return False
