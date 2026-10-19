"""
Typography component library for Antioch.

Provides text and typography components with consistent styling.
"""
from antioch import *
from antioch.elements import Code as CodeElement
from antioch.macros.base import Macro


class Heading(Macro):
    """
    A styled heading component with multiple levels.

    Features:
    - Six heading levels (h1-h6)
    - Consistent styling
    - Color variants
    - Custom margins

    Usage:
        heading = Heading("Page Title", level=1)
        DOM.add(heading.element)
    """

    def __init__(self, text="", level=1, color="inherit", margin_bottom="16px",
                 weight="bold", **kwargs):
        """
        Initialize a heading.

        Args:
            text: Heading text
            level: Heading level (1-6)
            color: Text color
            margin_bottom: Bottom margin
            weight: Font weight (normal, bold, etc.)
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="heading", **kwargs)

        self._set_state(
            text=text,
            level=min(max(level, 1), 6),  # Clamp between 1 and 6
            color=color,
            margin_bottom=margin_bottom,
            weight=weight
        )

        self._init_macro()

    def _get_level_styles(self):
        """Get level-specific styles."""
        level_styles = {
            1: {"font_size": "36px", "line_height": "1.2"},
            2: {"font_size": "30px", "line_height": "1.3"},
            3: {"font_size": "24px", "line_height": "1.4"},
            4: {"font_size": "20px", "line_height": "1.4"},
            5: {"font_size": "16px", "line_height": "1.5"},
            6: {"font_size": "14px", "line_height": "1.5"}
        }
        level = self._get_state('level')
        return level_styles.get(level, level_styles[1])

    def _create_elements(self):
        """Create the heading element."""
        level = self._get_state('level')
        level_styles = self._get_level_styles()

        heading_styles = {
            "color": self._get_state('color'),
            "margin": f"0 0 {self._get_state('margin_bottom')} 0",
            "font_weight": self._get_state('weight'),
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            **level_styles
        }

        # Create appropriate heading element
        heading_map = {
            1: H1,
            2: H2,
            3: H3,
            4: H4,
            5: H5,
            6: H6
        }

        HeadingElem = heading_map.get(level, H1)
        heading = HeadingElem(self._get_state('text'), style=heading_styles)

        self._register_element('heading', heading)
        return heading

    def set_text(self, text):
        """Update heading text."""
        self._set_state(text=text)
        heading = self._get_element('heading')
        if heading:
            heading.dom_element.textContent = text


class Text(Macro):
    """
    A styled text component with variants.

    Features:
    - Size variants
    - Color options
    - Weight options
    - Inline or block display

    Usage:
        text = Text("Hello, world!", size="large", color="#667eea")
        DOM.add(text.element)
    """

    def __init__(self, text="", size="medium", color="inherit", weight="normal",
                 align="left", display="inline", **kwargs):
        """
        Initialize a text component.

        Args:
            text: Text content
            size: Text size (small, medium, large, xlarge)
            color: Text color
            weight: Font weight (normal, medium, semibold, bold)
            align: Text alignment (left, center, right, justify)
            display: Display mode (inline, block, inline-block)
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="text", **kwargs)

        self._set_state(
            text=text,
            size=size,
            color=color,
            weight=weight,
            align=align,
            display=display
        )

        self._init_macro()

    def _get_size_styles(self):
        """Get size-specific styles."""
        sizes = {
            "small": {"font_size": "12px", "line_height": "1.5"},
            "medium": {"font_size": "14px", "line_height": "1.5"},
            "large": {"font_size": "16px", "line_height": "1.6"},
            "xlarge": {"font_size": "18px", "line_height": "1.6"}
        }
        size = self._get_state('size')
        return sizes.get(size, sizes["medium"])

    def _get_weight_value(self):
        """Get font weight value."""
        weights = {
            "normal": "400",
            "medium": "500",
            "semibold": "600",
            "bold": "700"
        }
        weight = self._get_state('weight')
        return weights.get(weight, "400")

    def _create_elements(self):
        """Create the text element."""
        size_styles = self._get_size_styles()

        text_styles = {
            "color": self._get_state('color'),
            "font_weight": self._get_weight_value(),
            "text_align": self._get_state('align'),
            "display": self._get_state('display'),
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "margin": "0",
            **size_styles
        }

        text = Span(self._get_state('text'), style=text_styles)
        self._register_element('text', text)

        return text

    def set_text(self, text):
        """Update text content."""
        self._set_state(text=text)
        elem = self._get_element('text')
        if elem:
            elem.dom_element.textContent = text


class Link(Macro):
    """
    A styled link component.

    Features:
    - Hover effects
    - Color variants
    - Underline options
    - Click events

    Usage:
        link = Link("Click here", href="https://example.com")
        DOM.add(link.element)

        @when(link.events.click)
        def handle_click(sender):
            print("Link clicked!")
    """

    def __init__(self, text="", href="#", color="#667eea", underline=True,
                 hover_color="#764ba2", target="_self", **kwargs):
        """
        Initialize a link.

        Args:
            text: Link text
            href: Link URL
            color: Link color
            underline: Whether to show underline
            hover_color: Color on hover
            target: Link target (_self, _blank, etc.)
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="link", **kwargs)

        self._set_state(
            text=text,
            href=href,
            color=color,
            underline=underline,
            hover_color=hover_color,
            target=target
        )

        self._create_event('click')

        self._init_macro()

    def _create_elements(self):
        """Create the link element."""
        link_styles = {
            "color": self._get_state('color'),
            "text_decoration": "underline" if self._get_state('underline') else "none",
            "cursor": "pointer",
            "transition": "color 0.2s ease",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        }

        link = A(
            self._get_state('text'),
            href=self._get_state('href'),
            target=self._get_state('target'),
            style=link_styles
        )

        self._register_element('link', link)
        self._wire_events(link)

        return link

    def _wire_events(self, link):
        """Wire DOM events."""

        @when(link.events.click)
        def on_click(sender, *args):
            self.events.fire('click')

        @when(link.events.mouseenter)
        def on_mouseenter(sender, *args):
            link.style.color = self._get_state('hover_color')

        @when(link.events.mouseleave)
        def on_mouseleave(sender, *args):
            link.style.color = self._get_state('color')

    def set_text(self, text):
        """Update link text."""
        self._set_state(text=text)
        link = self._get_element('link')
        if link:
            link.dom_element.textContent = text

    def set_href(self, href):
        """Update link href."""
        self._set_state(href=href)
        link = self._get_element('link')
        if link:
            link.dom_element.href = href


class Badge(Macro):
    """
    A badge/pill component for labels and counts.

    Features:
    - Color variants
    - Size options
    - Rounded or pill shape
    - Icon support

    Usage:
        badge = Badge("New", variant="success")
        DOM.add(badge.element)
    """

    def __init__(self, text="", variant="primary", size="medium",
                 rounded=True, **kwargs):
        """
        Initialize a badge.

        Args:
            text: Badge text
            variant: Color variant (primary, success, warning, danger, info, secondary)
            size: Badge size (small, medium, large)
            rounded: Whether to use pill shape (fully rounded)
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="badge", **kwargs)

        self._set_state(
            text=text,
            variant=variant,
            size=size,
            rounded=rounded
        )

        self._init_macro()

    def _get_variant_styles(self):
        """Get variant-specific colors."""
        variants = {
            "primary": {
                "background": "#667eea",
                "color": "white"
            },
            "success": {
                "background": "#10b981",
                "color": "white"
            },
            "warning": {
                "background": "#f59e0b",
                "color": "white"
            },
            "danger": {
                "background": "#ef4444",
                "color": "white"
            },
            "info": {
                "background": "#3b82f6",
                "color": "white"
            },
            "secondary": {
                "background": "#e5e7eb",
                "color": "#374151"
            }
        }
        variant = self._get_state('variant')
        return variants.get(variant, variants["primary"])

    def _get_size_styles(self):
        """Get size-specific styles."""
        sizes = {
            "small": {
                "padding": "2px 8px",
                "font_size": "11px"
            },
            "medium": {
                "padding": "4px 12px",
                "font_size": "12px"
            },
            "large": {
                "padding": "6px 16px",
                "font_size": "14px"
            }
        }
        size = self._get_state('size')
        return sizes.get(size, sizes["medium"])

    def _create_elements(self):
        """Create the badge element."""
        variant_styles = self._get_variant_styles()
        size_styles = self._get_size_styles()

        badge_styles = {
            "display": "inline-block",
            "border_radius": "999px" if self._get_state('rounded') else "4px",
            "font_weight": "500",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "line_height": "1",
            "white_space": "nowrap",
            **variant_styles,
            **size_styles
        }

        badge = Span(self._get_state('text'), style=badge_styles)
        self._register_element('badge', badge)

        return badge

    def set_text(self, text):
        """Update badge text."""
        self._set_state(text=text)
        badge = self._get_element('badge')
        if badge:
            badge.dom_element.textContent = text


class Code(Macro):
    """
    An inline code component.

    Features:
    - Monospace font
    - Background color
    - Copy functionality

    Usage:
        code = Code("const x = 10;")
        DOM.add(code.element)
    """

    def __init__(self, text="", background="#f3f4f6", color="#374151", **kwargs):
        """
        Initialize a code component.

        Args:
            text: Code text
            background: Background color
            color: Text color
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="code", **kwargs)

        self._set_state(
            text=text,
            background=background,
            color=color
        )

        self._init_macro()

    def _create_elements(self):
        """Create the code element."""
        code_styles = {
            "font_family": "Monaco, Consolas, 'Courier New', monospace",
            "font_size": "13px",
            "background": self._get_state('background'),
            "color": self._get_state('color'),
            "padding": "2px 6px",
            "border_radius": "4px",
            "display": "inline-block"
        }

        code = CodeElement(self._get_state('text'), style=code_styles)
        self._register_element('code', code)

        return code

    def set_text(self, text):
        """Update code text."""
        self._set_state(text=text)
        code = self._get_element('code')
        if code:
            code.dom_element.textContent = text