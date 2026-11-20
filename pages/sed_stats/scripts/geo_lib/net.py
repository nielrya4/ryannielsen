"""
The browser's `fetch`, as the few things the map needs from it: JSON, text and bytes.

`js` is imported when first used, so the modules that parse what comes back stay importable (and
testable) outside the browser. Tests replace `FETCH` with a fake.
"""
import json


class RateLimitedError(Exception):
    """A service answered 429: its free allowance is used up. Kept apart from "no data" so the
    message can say to try again later."""


REQUEST_SECONDS = 60       # a request that has not answered by then is given up on, not waited for forever


async def js_fetch(url, seconds=REQUEST_SECONDS):
    import js
    from pyodide.ffi import to_js
    options = to_js({"signal": js.AbortSignal.timeout(int(seconds * 1000))},
                    dict_converter=js.Object.fromEntries)
    return await js.fetch(url, options)


FETCH = js_fetch      # `async (url) -> response` with .status, .ok, .text(), .arrayBuffer(), .blob()


async def get_text(url):
    """The body of `url` as text, or None if the request failed or was refused."""
    try:
        response = await FETCH(url)
    except Exception:
        return None
    if response.status == 429:
        raise RateLimitedError()
    if not response.ok:
        return None
    try:
        return await response.text()
    except Exception:
        return None


async def get_json(url):
    """`url`'s JSON, or None if it could not be fetched or parsed."""
    text = await get_text(url)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None
