"""Colors and styles. Everything is styled inline from here; the page has no stylesheet."""
import js


def _dark():
    try:
        return bool(js.window.matchMedia("(prefers-color-scheme: dark)").matches)
    except Exception:
        return False


DARK = _dark()

# Page chrome follows the viewer's light/dark setting; popups stay light (they sit on the map).
SURFACE = "#161616" if DARK else "#fcfcfb"
PANEL = "#1f1f1e" if DARK else "#ffffff"
INK = "#f2f1ee" if DARK else "#0b0b0b"
INK_MUTED = "#b4b2ab" if DARK else "#52514e"
RULE = "#3a3936" if DARK else "#e2e0da"
ACCENT = "#6aa7ec" if DARK else "#2a78d6"
ACTIVE = "rgba(106, 167, 236, 0.18)" if DARK else "rgba(42, 120, 214, 0.12)"
HOVER = "rgba(106, 167, 236, 0.10)" if DARK else "rgba(42, 120, 214, 0.06)"

POPUP_INK = "#0b0b0b"
POPUP_MUTED = "#52514e"
TRACK = "#f0efea"

# The ternary corners of the land-cover maps.
SHARE_COLORS = {"agricultural": "#e8b000", "urban": "#d23c6e", "wilderness": "#2f6db5"}
SHARE_LABELS = {"agricultural": "Agricultural", "urban": "Urban", "wilderness": "Wilderness"}

RIVER = "#2f5f8f"
OUTLINE = "#ffffff"
FILL_OPACITY = 0.8

SIDEBAR_WIDTH = "340px"
NARROW = "(max-width: 720px)"  # below this the sidebar sits above the map
FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

BODY_STYLE = {
    "margin": "0", "padding": "0", "height": "100vh", "overflow": "hidden",
    "background-color": SURFACE, "color": INK, "font-family": FONT,
}

APP_STYLE = {"display": "flex", "height": "100vh", "width": "100%"}
APP_NARROW = {"flex-direction": "column"}
APP_WIDE = {"flex-direction": "row"}

SIDEBAR_STYLE = {
    "flex": f"0 0 {SIDEBAR_WIDTH}", "box-sizing": "border-box", "height": "100%",
    "overflow-y": "auto", "padding": "20px 18px", "background-color": PANEL,
    "border-right": f"1px solid {RULE}",
}
SIDEBAR_NARROW = {"flex": "0 0 auto", "height": "auto", "max-height": "45vh",
                  "border-right": "none", "border-bottom": f"1px solid {RULE}",
                  "padding": "14px 16px"}
SIDEBAR_WIDE = {"flex": f"0 0 {SIDEBAR_WIDTH}", "height": "100%", "max-height": "none",
                "border-right": f"1px solid {RULE}", "border-bottom": "none",
                "padding": "20px 18px"}
MAP_PANE_STYLE = {"flex": "1 1 auto", "min-width": "0", "min-height": "0", "height": "100%"}

TITLE_STYLE = {"font-size": "19px", "line-height": "1.25", "margin": "0 0 6px",
               "color": INK, "border": "none", "padding": "0"}
LEDE_STYLE = {"font-size": "13px", "color": INK_MUTED, "margin": "0 0 18px",
              "line-height": "1.45"}
HEADING_STYLE = {"font-size": "12px", "text-transform": "uppercase", "letter-spacing": "0.06em",
                 "color": INK_MUTED, "margin": "18px 0 8px"}
CHOICE_STYLE = {"display": "flex", "align-items": "center", "gap": "8px",
                "padding": "7px 8px", "margin": "2px 0", "border-radius": "6px",
                "font-size": "14px", "cursor": "pointer", "color": INK,
                "background-color": "transparent", "font-weight": "400"}
CHOICE_ACTIVE = {"background-color": ACTIVE, "font-weight": "600"}
CHOICE_IDLE = {"background-color": "transparent", "font-weight": "400"}
RADIO_STYLE = {"margin": "0", "accent-color": ACCENT, "width": "auto", "padding": "0"}
DESCRIPTION_STYLE = {"font-size": "13px", "line-height": "1.45", "color": INK_MUTED,
                     "margin": "8px 0 12px"}
LEGEND_ROW_STYLE = {"display": "flex", "align-items": "center", "gap": "8px",
                    "font-size": "12.5px", "margin": "4px 0", "color": INK}
SWATCH_STYLE = {"flex": "0 0 18px", "height": "14px", "border-radius": "3px",
                "border": "1px solid rgba(0, 0, 0, 0.15)"}
# A watershed's point on the land-cover triangle, matched in its legend row.
DOT_SWATCH = {"flex": "0 0 12px", "height": "12px", "border-radius": "50%",
              "border": "1.5px solid #ffffff", "box-shadow": f"0 0 0 0.75px {INK}",
              "margin": "0 3px"}
GRADIENT_STYLE = {"height": "14px", "border-radius": "3px", "margin": "6px 8px 0",
                  "border": "1px solid rgba(0, 0, 0, 0.15)"}
TICKS_STYLE = {"position": "relative", "height": "26px", "margin": "0 8px"}
TICK_STYLE = {"position": "absolute", "top": "0", "width": "1px", "height": "6px",
              "background-color": INK_MUTED}
TICK_LABEL_STYLE = {"position": "absolute", "top": "8px", "transform": "translateX(-50%)",
                    "font-size": "12px", "color": INK_MUTED}
FOOTNOTE_STYLE = {"font-size": "11.5px", "color": INK_MUTED, "line-height": "1.45",
                  "margin-top": "22px"}

POPUP_STYLE = {"width": "300px", "font-size": "12.5px", "line-height": "1.4", "color": POPUP_INK,
               "font-family": FONT}
POPUP_TITLE_STYLE = {"margin": "0 0 2px", "font-size": "15px", "display": "flex",
                     "align-items": "center", "gap": "7px", "color": POPUP_INK}
DOT_STYLE = {"width": "11px", "height": "11px", "border-radius": "50%", "display": "inline-block"}
META_STYLE = {"color": POPUP_MUTED, "margin-bottom": "8px"}
POPUP_HEADING_STYLE = {"font-size": "11px", "text-transform": "uppercase",
                       "letter-spacing": "0.05em", "color": POPUP_MUTED, "margin": "10px 0 4px"}
BIG_STYLE = {"font-size": "20px", "font-weight": "600"}
RANGE_STYLE = {"color": POPUP_MUTED, "margin-left": "6px"}
BAR_ROW_STYLE = {"display": "grid", "grid-template-columns": "70px 1fr 44px",
                 "align-items": "center", "gap": "6px", "margin": "2px 0"}
BAR_TRACK_STYLE = {"position": "relative", "height": "10px", "background-color": TRACK,
                   "border-radius": "3px"}
BAR_FILL_STYLE = {"position": "absolute", "left": "0", "top": "0", "bottom": "0",
                  "border-radius": "3px"}
VALUE_STYLE = {"text-align": "right", "font-variant-numeric": "tabular-nums"}
STAT_GRID_STYLE = {"display": "grid", "grid-template-columns": "1fr auto", "gap": "2px 10px"}
