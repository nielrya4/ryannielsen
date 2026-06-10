"""
Antioch Framework Homepage
A showcase of the Pyodide-powered Python UI framework
"""
from antioch import *
from antioch.macros import CodeBlock, DownloadLink

def main():
    # Set page background
    DOM.body.style.update({
        "margin": "0",
        "padding": "0",
        "font-family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif",
        "background": "#1a1a1a",
        "color": "#e0e0e0",
        "min-height": "100vh"
    })

    # Container
    container = Div(style={
        "max-width": "1200px",
        "margin": "0 auto",
        "padding": "20px"
    })
    DOM.add(container)

    # Hero Section
    hero = Section(
        H1("Antioch", style={
            "font-size": "3.5rem",
            "margin": "0 0 20px 0",
            "color": "#ffffff",
            "font-weight": "300"
        }),
        P("Antioch is a Python UI framework for the browser based on Pyodide.", style={
            "font-size": "1.2rem",
            "color": "#b0b0b0",
            "margin": "0 0 60px 0",
            "line-height": "1.6"
        }),
        style={
            "padding": "60px 0 40px 0",
            "border-bottom": "1px solid #333"
        }
    )
    container.add(hero)

    # What is Antioch Section
    what_section = Section(
        H2("What is Antioch?", style={
            "color": "#ffffff",
            "margin": "50px 0 30px 0",
            "font-size": "2.5rem",
            "font-weight": "300"
        }),
        P(
            "Antioch is a port of Python DOM manipulation to the browser via ",
            A("Pyodide", href="https://pyodide.org", style={"color": "#4A9EFF", "text-decoration": "none"}),
            ".",
            style={
                "font-size": "1.1rem",
                "color": "#b0b0b0",
                "line-height": "1.8",
                "margin-bottom": "20px"
            }
        ),
        P(
            "Antioch makes it possible to build interactive web UIs entirely in Python with an intuitive, Pythonic API. ",
            "Write your UI code in Python using familiar DOM elements, style them with dictionaries, and handle events with decorators.",
            style={
                "font-size": "1.1rem",
                "color": "#b0b0b0",
                "line-height": "1.8",
                "margin-bottom": "20px"
            }
        ),
        P(
            "Antioch comes with a rich set of built-in components (modals, tabs, forms, charts, and more) and gives you full access to the browser's Web APIs. ",
            "No server required—everything runs directly in the browser.",
            style={
                "font-size": "1.1rem",
                "color": "#b0b0b0",
                "line-height": "1.8",
                "margin-bottom": "40px"
            }
        ),
        style={
            "border-bottom": "1px solid #333",
            "padding-bottom": "40px"
        }
    )
    container.add(what_section)

    # Try Antioch Section
    try_section = Section(
        H2("Try Antioch", style={
            "color": "#ffffff",
            "margin": "50px 0 30px 0",
            "font-size": "2.5rem",
            "font-weight": "300"
        }),
        Div(
            Div(
                CodeBlock(
                    content='''from antioch import *

def main():
    # Create a counter
    count = 0
    display = H2(f"Count: {count}")

    btn = Button("Click me!")

    @when(btn.events.click)
    def increment(sender, event):
        nonlocal count
        count += 1
        display.set_text(f"Count: {count}")

    DOM.add(display, btn)''',
                    language="python",
                    editable=False,
                    theme="monokai",
                    line_numbers=True,
                    height="350px",
                    container_style={
                        "border-radius": "4px",
                        "overflow": "hidden",
                        "border": "1px solid #333"
                    }
                ),
                style={
                    "flex": "1"
                }
            ),
            Div(
                create_counter_demo(),
                style={
                    "flex": "1",
                    "background": "#252525",
                    "border-radius": "4px",
                    "padding": "30px",
                    "border": "1px solid #333",
                    "display": "flex",
                    "flex-direction": "column",
                    "align-items": "center",
                    "justify-content": "center"
                }
            ),
            style={
                "display": "grid",
                "grid-template-columns": "repeat(auto-fit, minmax(400px, 1fr))",
                "gap": "20px",
                "margin-bottom": "40px"
            }
        ),
        style={
            "border-bottom": "1px solid #333",
            "padding-bottom": "40px"
        }
    )
    container.add(try_section)

    # Getting Started Section
    getting_started = Section(
        H2("Getting Started", style={
            "color": "#ffffff",
            "margin": "50px 0 30px 0",
            "font-size": "2.5rem",
            "font-weight": "300"
        }),

        # Installation
        H3("Installation", style={
            "color": "#ffffff",
            "margin": "30px 0 20px 0",
            "font-size": "1.8rem",
            "font-weight": "300"
        }),
        P("Download and install Antioch with our installer script:", style={
            "font-size": "1.1rem",
            "color": "#b0b0b0",
            "line-height": "1.8",
            "margin-bottom": "20px"
        }),
        Div(
            DownloadLink(
                href="assets/antioch-installer.sh",
                filename="antioch-installer.sh",
                text="Download Installer",
                link_style={
                    "display": "inline-block",
                    "padding": "12px 24px",
                    "background": "#4A9EFF",
                    "color": "white",
                    "text-decoration": "none",
                    "border-radius": "4px",
                    "font-weight": "500",
                    "font-size": "1rem",
                    "transition": "background 0.2s ease"
                }
            ),
            style={
                "margin-bottom": "20px"
            }
        ),
        Pre(
            Code("chmod +x antioch-installer.sh && ./antioch-installer.sh", style={
                "color": "#e0e0e0",
                "font-size": "0.95rem"
            }),
            style={
                "background": "#252525",
                "padding": "15px",
                "border-radius": "4px",
                "border": "1px solid #333",
                "overflow-x": "auto",
                "margin-bottom": "40px"
            }
        ),

        # Using Antioch
        H3("Using Antioch", style={
            "color": "#ffffff",
            "margin": "30px 0 20px 0",
            "font-size": "1.8rem",
            "font-weight": "300"
        }),
        P("Once installed, use the antioch command to create and manage projects:", style={
            "font-size": "1.1rem",
            "color": "#b0b0b0",
            "line-height": "1.8",
            "margin-bottom": "20px"
        }),

        # Create new project
        P("Create a new project:", style={
            "font-size": "1.05rem",
            "color": "#b0b0b0",
            "margin": "20px 0 10px 0",
            "font-weight": "500"
        }),
        Pre(
            Code(f"mkdir antioch_project && cd antioch_project\nantioch env", style={
                "color": "#e0e0e0",
                "font-size": "0.95rem"
            }),
            style={
                "background": "#252525",
                "padding": "15px",
                "border-radius": "4px",
                "border": "1px solid #333",
                "overflow-x": "auto",
                "margin-bottom": "20px"
            }
        ),

        # Build project
        P("Build your project:", style={
            "font-size": "1.05rem",
            "color": "#b0b0b0",
            "margin": "20px 0 10px 0",
            "font-weight": "500"
        }),
        Pre(
            Code("antioch build", style={
                "color": "#e0e0e0",
                "font-size": "0.95rem"
            }),
            style={
                "background": "#252525",
                "padding": "15px",
                "border-radius": "4px",
                "border": "1px solid #333",
                "overflow-x": "auto",
                "margin-bottom": "20px"
            }
        ),

        # Run dev server
        P("Start the development server:", style={
            "font-size": "1.05rem",
            "color": "#b0b0b0",
            "margin": "20px 0 10px 0",
            "font-weight": "500"
        }),
        Pre(
            Code("antioch run", style={
                "color": "#e0e0e0",
                "font-size": "0.95rem"
            }),
            style={
                "background": "#252525",
                "padding": "15px",
                "border-radius": "4px",
                "border": "1px solid #333",
                "overflow-x": "auto",
                "margin-bottom": "20px"
            }
        ),

        # Install packages
        P("Add Python packages to your project:", style={
            "font-size": "1.05rem",
            "color": "#b0b0b0",
            "margin": "20px 0 10px 0",
            "font-weight": "500"
        }),
        Pre(
            Code("antioch install numpy pandas", style={
                "color": "#e0e0e0",
                "font-size": "0.95rem"
            }),
            style={
                "background": "#252525",
                "padding": "15px",
                "border-radius": "4px",
                "border": "1px solid #333",
                "overflow-x": "auto",
                "margin-bottom": "40px"
            }
        ),

        style={
            "border-bottom": "1px solid #333",
            "padding-bottom": "40px"
        }
    )
    container.add(getting_started)

    # Footer
    footer = Footer(
        P(
            "Built with ",
            Strong("Antioch"),
            " • Powered by ",
            A("Pyodide", href="https://pyodide.org", target="_blank", style={
                "color": "#4A9EFF",
                "text-decoration": "none"
            }),
            style={
                "text-align": "center",
                "color": "#808080",
                "margin": "40px 0 20px 0",
                "font-size": "0.95rem"
            }
        )
    )
    container.add(footer)

def create_counter_demo():
    """Create the interactive counter demo"""
    count = 0

    display = H2(f"Count: {count}", style={
        "color": "#ffffff",
        "font-size": "2rem",
        "margin": "20px 0",
        "font-weight": "300"
    })

    btn = Button("Click me!", style={
        "padding": "10px 20px",
        "margin": "5px",
        "font-size": "0.95rem",
        "background": "#4A9EFF",
        "color": "white",
        "border": "none",
        "border-radius": "4px",
        "cursor": "pointer",
        "font-weight": "500",
        "transition": "background 0.2s ease"
    })

    @when(btn.events.click)
    def increment(sender, event):
        nonlocal count
        count += 1
        display.set_text(f"Count: {count}")

    # Add hover effect
    @when(btn.events.mouseenter)
    def on_hover(sender, event):
        sender.style.background = "#3a8eef"

    @when(btn.events.mouseleave)
    def on_leave(sender, event):
        sender.style.background = "#4A9EFF"

    return Div(
        display,
        btn,
        style={
            "display": "flex",
            "flex-direction": "column",
            "align-items": "center",
            "gap": "10px"
        }
    )

if __name__ == "__main__":
    main()
