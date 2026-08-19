"""Full-screen busy overlay for work that blocks the UI thread."""
import asyncio

import js
from pyodide.ffi import create_proxy

_SPINNER_CSS_ID = "ui-lib-overlay-css"

# Keyframes can't be expressed as inline styles.
_CSS = """
@keyframes ui-lib-spin { to { transform: rotate(360deg); } }
.ui-lib-spinner {
  width: 44px;
  height: 44px;
  border: 4px solid rgba(255, 255, 255, 0.25);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: ui-lib-spin 0.8s linear infinite;
}
"""


def _ensure_css():
    if js.document.getElementById(_SPINNER_CSS_ID) is None:
        style = js.document.createElement("style")
        style.id = _SPINNER_CSS_ID
        style.textContent = _CSS
        js.document.head.appendChild(style)


async def next_frame():
    """
    Yield long enough for the browser to paint.

    A single rAF fires *before* the paint it schedules, so anything shown in
    the same tick as a synchronous computation would never appear. Waiting two
    frames guarantees at least one paint has landed.
    """
    future = asyncio.get_event_loop().create_future()
    proxies = []

    def cleanup():
        for proxy in proxies:
            proxy.destroy()

    def second(_time):
        if not future.done():
            future.set_result(None)

    def first(_time):
        proxy = create_proxy(second)
        proxies.append(proxy)
        js.requestAnimationFrame(proxy)

    outer = create_proxy(first)
    proxies.append(outer)
    js.requestAnimationFrame(outer)
    try:
        await future
    finally:
        cleanup()


class LoadingOverlay:
    """
    A curtain with a spinner, mounted straight on <body>.

    Built from raw DOM rather than antioch elements so it can sit above the
    modal layer without being reparented by whatever is mounting at the time.

        overlay = LoadingOverlay()
        await overlay.run(build_everything, "Building graphs…")
    """

    def __init__(self, z_index=2000):
        _ensure_css()

        self._root = js.document.createElement("div")
        self._root.style.cssText = (
            "position:fixed; inset:0; display:none;"
            "align-items:center; justify-content:center; flex-direction:column;"
            "gap:14px; background:rgba(20,25,32,0.55); cursor:wait;"
            f"z-index:{z_index};"
        )

        spinner = js.document.createElement("div")
        spinner.className = "ui-lib-spinner"

        self._label = js.document.createElement("div")
        self._label.style.cssText = (
            "color:#fff; font-size:14px; font-weight:500;"
            "text-shadow:0 1px 2px rgba(0,0,0,0.4);"
        )

        self._root.appendChild(spinner)
        self._root.appendChild(self._label)
        js.document.body.appendChild(self._root)

    def show(self, message="Working…"):
        self._label.textContent = message
        self._root.style.display = "flex"
        # The overlay swallows pointer events, but the cursor only changes over
        # elements it actually covers — body covers the scrollbars too.
        js.document.body.style.cursor = "wait"
        return self

    def hide(self):
        self._root.style.display = "none"
        js.document.body.style.cursor = ""
        return self

    async def run(self, work, message="Working…"):
        """
        Show the overlay, let it paint, run `work`, then always hide.

        `work` may be sync or async; its return value is passed through.
        """
        self.show(message)
        try:
            await next_frame()
            result = work()
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                result = await result
            return result
        finally:
            self.hide()