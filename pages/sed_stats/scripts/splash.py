"""
Antioch Demo Splash Screen

This splash screen displays while Pyodide loads, providing SEO-friendly
static HTML content for search engines and a better user experience.
"""

from antioch.static import StaticPage, Div, P, keyframe, rotate, opacity, translateY

# Sky-strata-sky: blue fading to the icon's own sky color, a thin band of the
# strata browns across the middle, then back out to blue.
DEEP_BLUE = "#305a88"
SKY_BLUE = "#99b1cb"  # sampled from assets/sed_stats.png
STRATA = ["#ccc3ba", "#b2a48a", "#9c8969", "#9e6549", "#8e5b42", "#665141"]

BAND_START, BAND_END = 35, 65

# The sky reaches full light blue this far short of the band, leaving a stretch
# for it to wash into the first brown instead of meeting it at a hard edge.
BLEND = 5


def strata_gradient(angle="135deg"):
    """The background gradient, with the browns held to the middle band."""
    span = BAND_END - BAND_START
    stops = [f"{DEEP_BLUE} 0%", f"{SKY_BLUE} {BAND_START - BLEND}%"]
    for i, color in enumerate(STRATA):
        position = BAND_START + span * i / (len(STRATA) - 1)
        stops.append(f"{color} {position:g}%")
    stops.append(f"{SKY_BLUE} {BAND_END + BLEND}%")
    stops.append(f"{DEEP_BLUE} 100%")
    return f"linear-gradient({angle}, {', '.join(stops)})"


# Define keyframe animations pythonically!
@keyframe
def spin():
    rotate({0: 0, 100: 360})


@keyframe
def fadeInDown():
    opacity({0: 0, 100: 1})
    translateY({0: -30, 100: 0})


@keyframe
def fadeInUp():
    opacity({0: 0, 100: 1})
    translateY({0: 30, 100: 0})


def generate_splash():
    """Generate the static splash screen HTML."""

    # Create the page with SEO metadata
    page = StaticPage(title="Sed/Stats", lang="en")
    page.set_title("Sed/Stats")
    page.add_meta(
        name="viewport",
        content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"
    )

    # SEO Meta Tags
    page.set_description(
        "Sed/Stats is a web app that facilitates visualization and interpretation of sedimentological data"
        "Upload your data and generate high-quality, publication-ready figures in just a few clicks."
    )
    page.set_keywords("sedimentology", "geology", "detrital zircon", "python", "mixture modeling", "microplastics")
    page.set_author("Ryan Nielsen")

    # Open Graph tags for social media
    page.set_og_title("Sed/Stats")
    page.set_og_description("Build publication-ready figures in just a few clicks")
    page.set_og_url("https://sedstats.com")

    # Add animations to page
    page.add_style(spin.render())
    page.add_style(fadeInDown.render())
    page.add_style(fadeInUp.render())

    # Set body styles using dictionary assignment (just like DOM.body.style in Antioch!)
    page_div = Div(style = {
        'margin': '0',
        'padding': '0',
        'font_family': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        'background': strata_gradient(),
        'min_height': '100vh',
        'display': 'flex',
        'justify_content': 'center',
        'align_items': 'center',
        'color': 'white'
    })


    # Build the splash screen content with pythonic styles
    container = Div(id="loading-splash", style={
        'text-align': 'center',
        'padding': '40px',
        'max-width': '600px'
    })

    # Logo with gradient text effect
    logo = Div("Sed/Stats", style={
        'font-size': '4em',
        'font-weight': 'bold',
        'margin-bottom': '20px',
        'background': 'linear-gradient(135deg, #fff 0%, #f0f0f0 100%)',
        '-webkit-background-clip': 'text',
        '-webkit-text-fill-color': 'transparent',
        'background-clip': 'text'
    })

    # Tagline
    tagline = P("Visualize and Interpret Sedimentological Data", style={
        'font-size': '1.5em',
        'margin-bottom': '30px',
        'opacity': '0.9',
        'animation': 'fadeInUp 0.8s ease-out 0.2s both'
    })

    # Spinner
    spinner_container = Div(style={
        'margin': '30px auto 20px auto',
        'animation': 'fadeInUp 0.8s ease-out 0.6s both'
    })
    spinner = Div(style={
        'border': '4px solid rgba(255, 255, 255, 0.3)',
        'border-top': '4px solid white',
        'border-radius': '50%',
        'width': '60px',
        'height': '60px',
        'animation': 'spin 1s linear infinite',
        'margin': '0 auto'
    })
    spinner_container.add(spinner)

    # Loading text
    loading_text = P("Loading modules...", style={
        'font-size': '1.1em',
        'margin': '0',
        'opacity': '0.8'
    })

    # Add all elements to container
    container.add(logo, tagline, spinner_container, loading_text)
    page_div.add(container)
    page.add(page_div)

    return page


# Allow running this file directly to preview the splash screen
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Add parent directory to path to import antioch.static
    sys.path.insert(0, str(Path(__file__).parent.parent))

    page = generate_splash()
    preview_path = Path(__file__).parent.parent / "splash_preview.html"

    with open(preview_path, "w") as f:
        f.write(page.render())

    print(f"✅ Splash screen preview saved to: {preview_path}")
    print(f"   Open it in a browser to see how it looks!")