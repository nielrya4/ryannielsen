"""Surfacing failures where the user can actually see them."""
import traceback

from antioch.elements import Div, H3, Pre

from .config import CHART_WIDTH


def error_box(heading, exception):
    """Render an exception in the page; the browser console is out of reach on mobile."""
    details = traceback.format_exc()
    return Div(
        H3(f"{heading}: {type(exception).__name__}",
           style={"font-size": "15px", "margin": "20px 0 6px 0", "color": "#b00020"}),
        Pre(details, style={
            "font-size": "11px", "white-space": "pre-wrap", "word-break": "break-word",
            "background-color": "#fff4f4", "border": "1px solid #f0c0c0",
            "padding": "8px", "margin": "0", "max-width": f"{CHART_WIDTH}px",
            "overflow-x": "auto",
        }),
    )
