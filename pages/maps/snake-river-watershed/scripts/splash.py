"""
Splash screen: static HTML shown while Pyodide loads (antioch.toml splash_file), as in Sed/Stats.
"""

from antioch.static import StaticPage, Div, P, keyframe, rotate, opacity, translateY

# River blue fading into the light gray of the map's basemap.
DEEP_BLUE = "#1f4e79"
RIVER_BLUE = "#2f6fa8"
MIST = "#9fb8cf"
FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'


@keyframe
def spin():
    rotate({0: 0, 100: 360})


@keyframe
def fadeInUp():
    opacity({0: 0, 100: 1})
    translateY({0: 20, 100: 0})


def generate_splash():
    """Generate the static splash screen HTML."""
    page = StaticPage(title="Snake River Watersheds", lang="en")
    page.set_title("Snake River Watersheds")
    page.add_meta(name="viewport", content="width=device-width, initial-scale=1.0")
    page.set_description("An interactive map of microplastic sources in the Snake River above "
                         "the Weiser River confluence: polymer mixes, land cover, stream "
                         "connectivity and modelled contributions of six source watersheds.")
    page.set_keywords("microplastics", "Snake River", "watersheds", "mixture modeling",
                      "land cover", "Idaho")
    page.set_author("Ryan Nielsen")
    page.add_style(spin.render())
    page.add_style(fadeInUp.render())

    background = Div(style={
        "margin": "0",
        "padding": "0 16px",
        "font_family": FONT,
        "background": f"linear-gradient(160deg, {DEEP_BLUE} 0%, {RIVER_BLUE} 55%, {MIST} 100%)",
        "min_height": "100vh",
        "display": "flex",
        "justify_content": "center",
        "align_items": "center",
        "color": "white",
    })
    container = Div(id="loading-splash", style={
        "text-align": "center",
        "max-width": "560px",
    })
    title = Div("Microplastics in the Snake River Watershed", style={
        "font-size": "2.4em",
        "font-weight": "bold",
        "line-height": "1.2",
        "margin-bottom": "16px",
        "animation": "fadeInUp 0.8s ease-out both",
    })
    tagline = P("Six source watersheds, one downstream sample, and where its plastics came from",
                style={
                    "font-size": "1.2em",
                    "margin": "0 0 32px",
                    "opacity": "0.9",
                    "animation": "fadeInUp 0.8s ease-out 0.2s both",
                })
    spinner = Div(style={
        "border": "4px solid rgba(255, 255, 255, 0.3)",
        "border-top": "4px solid white",
        "border-radius": "50%",
        "width": "48px",
        "height": "48px",
        "animation": "spin 1s linear infinite",
        "margin": "0 auto 16px",
    })
    loading = P("Loading the map...", style={"font-size": "1em", "margin": "0", "opacity": "0.8"})

    container.add(title, tagline, spinner, loading)
    background.add(container)
    page.add(background)
    return page


# Run directly to preview the splash screen.
if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    preview = Path(__file__).parent.parent / "splash_preview.html"
    preview.write_text(generate_splash().render())
    print(f"Splash screen preview saved to: {preview}")
