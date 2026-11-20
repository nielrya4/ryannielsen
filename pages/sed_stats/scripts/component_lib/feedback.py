"""
Feedback component library for Antioch.

Provides user feedback components like alerts, toasts, spinners, and progress bars.
"""
from antioch import *
from antioch.macros.base import Macro
from .utils import inject_keyframes


class Alert(Macro):
    """
    An alert message component.

    Features:
    - Multiple variants (success, warning, danger, info)
    - Dismissible option
    - Icon support
    - Custom styling

    Usage:
        alert = Alert(
            "Operation successful!",
            variant="success",
            dismissible=True
        )
        DOM.add(alert.element)

        @when(alert.events.dismiss)
        def handle_dismiss(sender):
            print("Alert dismissed")
    """

    def __init__(self, message="", variant="info", dismissible=False,
                 show_icon=True, **kwargs):
        """
        Initialize an alert.

        Args:
            message: Alert message text
            variant: Alert variant (success, warning, danger, info)
            dismissible: Whether alert can be dismissed
            show_icon: Whether to show icon
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="alert", **kwargs)

        self._set_state(
            message=message,
            variant=variant,
            dismissible=dismissible,
            show_icon=show_icon,
            visible=True
        )

        self._create_event('dismiss')

        self._init_macro()

    def _get_variant_styles(self):
        """Get variant-specific styles."""
        variants = {
            "success": {
                "background": "#d1fae5",
                "border_color": "#10b981",
                "color": "#065f46",
                "icon": "✓"
            },
            "warning": {
                "background": "#fef3c7",
                "border_color": "#f59e0b",
                "color": "#92400e",
                "icon": "⚠"
            },
            "danger": {
                "background": "#fee2e2",
                "border_color": "#ef4444",
                "color": "#991b1b",
                "icon": "✕"
            },
            "info": {
                "background": "#dbeafe",
                "border_color": "#3b82f6",
                "color": "#1e40af",
                "icon": "ℹ"
            }
        }
        variant = self._get_state('variant')
        return variants.get(variant, variants["info"])

    def _create_elements(self):
        """Create the alert element."""
        if not self._get_state('visible'):
            empty = Div(style={"display": "none"})
            self._register_element('container', empty)
            return empty

        variant_styles = self._get_variant_styles()

        alert_styles = {
            "display": "flex",
            "align_items": "center",
            "gap": "12px",
            "padding": "12px 16px",
            "border": f"1px solid {variant_styles['border_color']}",
            "border_radius": "6px",
            "background": variant_styles['background'],
            "color": variant_styles['color'],
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "font_size": "14px"
        }

        container = Div(style=alert_styles)

        # Icon
        if self._get_state('show_icon'):
            icon_styles = {
                "font_size": "18px",
                "font_weight": "bold"
            }
            icon = Span(variant_styles['icon'], style=icon_styles)
            container.add(icon)

        # Message
        message_styles = {
            "flex": "1"
        }
        message = Span(self._get_state('message'), style=message_styles)
        container.add(message)
        self._register_element('message', message)

        # Dismiss button
        if self._get_state('dismissible'):
            close_styles = {
                "cursor": "pointer",
                "font_size": "18px",
                "font_weight": "bold",
                "padding": "0 4px",
                "opacity": "0.7",
                "transition": "opacity 0.2s ease"
            }
            close_btn = Span("×", style=close_styles)
            container.add(close_btn)
            self._register_element('close_btn', close_btn)

            @when(close_btn.events.click)
            def on_close(sender, *args):
                self.dismiss()

            @when(close_btn.events.mouseenter)
            def on_hover(sender, *args):
                close_btn.style.opacity = "1"

            @when(close_btn.events.mouseleave)
            def on_leave(sender, *args):
                close_btn.style.opacity = "0.7"

        self._register_element('container', container)
        return container

    def dismiss(self):
        """Dismiss the alert."""
        self._set_state(visible=False)
        container = self._get_element('container')
        if container:
            container.style.display = "none"
        self.events.fire('dismiss')

    def show(self):
        """Show the alert."""
        self._set_state(visible=True)
        container = self._get_element('container')
        if container:
            container.style.display = "flex"

    def set_message(self, message):
        """Update the alert message."""
        self._set_state(message=message)
        msg_elem = self._get_element('message')
        if msg_elem:
            msg_elem.dom_element.textContent = message


class Spinner(Macro):
    """
    A loading spinner component.

    Features:
    - Multiple sizes
    - Color customization
    - CSS animation

    Usage:
        spinner = Spinner(size="large", color="#667eea")
        DOM.add(spinner.element)
    """

    def __init__(self, size="medium", color="#667eea", **kwargs):
        """
        Initialize a spinner.

        Args:
            size: Spinner size (small, medium, large)
            color: Spinner color
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="spinner", **kwargs)

        self._set_state(
            size=size,
            color=color
        )

        self._init_macro()

    def _get_size_value(self):
        """Get size value in pixels."""
        sizes = {
            "small": "16px",
            "medium": "32px",
            "large": "48px"
        }
        size = self._get_state('size')
        return sizes.get(size, sizes["medium"])

    def _create_elements(self):
        """Create the spinner element."""
        size = self._get_size_value()

        # Inject spinner keyframes using Pythonic approach
        inject_keyframes('component-lib-spinner', {
            'spinner-spin': {
                '0%': {'transform': 'rotate(0deg)'},
                '100%': {'transform': 'rotate(360deg)'}
            }
        })

        spinner_styles = {
            "width": size,
            "height": size,
            "border": f"3px solid {self._get_state('color')}33",
            "border_top": f"3px solid {self._get_state('color')}",
            "border_radius": "50%",
            "animation": "spinner-spin 1s linear infinite",
            "display": "inline-block"
        }

        container = Div(style={"display": "inline-block"})

        spinner = Div(style=spinner_styles)
        container.add(spinner)

        self._register_element('spinner', spinner)
        self._register_element('container', container)

        return container


class ProgressBar(Macro):
    """
    A progress bar component.

    Features:
    - Configurable progress value (0-100)
    - Color variants
    - Animated or static
    - Label support

    Usage:
        progress = ProgressBar(value=50, variant="success")
        DOM.add(progress.element)
    """

    def __init__(self, value=0, variant="primary", height="8px",
                 show_label=False, animated=False, **kwargs):
        """
        Initialize a progress bar.

        Args:
            value: Progress value (0-100)
            variant: Color variant (primary, success, warning, danger, info)
            height: Progress bar height
            show_label: Whether to show percentage label
            animated: Whether to animate the bar
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="progress_bar", **kwargs)

        self._set_state(
            value=min(max(value, 0), 100),  # Clamp between 0-100
            variant=variant,
            height=height,
            show_label=show_label,
            animated=animated
        )

        self._init_macro()

    def _get_variant_color(self):
        """Get variant color."""
        colors = {
            "primary": "#667eea",
            "success": "#10b981",
            "warning": "#f59e0b",
            "danger": "#ef4444",
            "info": "#3b82f6"
        }
        variant = self._get_state('variant')
        return colors.get(variant, colors["primary"])

    def _create_elements(self):
        """Create the progress bar element."""
        container = Div(style={"width": "100%"})

        # Background track
        track_styles = {
            "width": "100%",
            "height": self._get_state('height'),
            "background": "#e5e7eb",
            "border_radius": "999px",
            "overflow": "hidden",
            "position": "relative"
        }
        track = Div(style=track_styles)

        # Progress fill
        fill_styles = {
            "width": f"{self._get_state('value')}%",
            "height": "100%",
            "background": self._get_variant_color(),
            "transition": "width 0.3s ease",
            "border_radius": "999px"
        }

        if self._get_state('animated'):
            # Inject progress bar keyframes using Pythonic approach
            inject_keyframes('component-lib-progress', {
                'progress-slide': {
                    '0%': {'background-position': '0 0'},
                    '100%': {'background-position': '40px 0'}
                }
            })

            fill_styles["background_image"] = f"linear-gradient(45deg, rgba(255,255,255,.2) 25%, transparent 25%, transparent 50%, rgba(255,255,255,.2) 50%, rgba(255,255,255,.2) 75%, transparent 75%, transparent)"
            fill_styles["background_size"] = "40px 40px"
            fill_styles["animation"] = "progress-slide 1s linear infinite"

        fill = Div(style=fill_styles)
        track.add(fill)
        self._register_element('fill', fill)

        container.add(track)

        # Label
        if self._get_state('show_label'):
            label_styles = {
                "text_align": "center",
                "margin_top": "4px",
                "font_size": "12px",
                "color": "#6b7280",
                "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            }
            label = Div(f"{self._get_state('value')}%", style=label_styles)
            container.add(label)
            self._register_element('label', label)

        self._register_element('container', container)
        return container

    def set_value(self, value):
        """Update progress value."""
        value = min(max(value, 0), 100)
        self._set_state(value=value)

        fill = self._get_element('fill')
        if fill:
            fill.style.width = f"{value}%"

        if self._get_state('show_label'):
            label = self._get_element('label')
            if label:
                label.dom_element.textContent = f"{value}%"


class Toast(Macro):
    """
    A toast notification component.

    Features:
    - Auto-dismiss with timer
    - Position options
    - Color variants
    - Click to dismiss

    Usage:
        toast = Toast(
            "Changes saved!",
            variant="success",
            duration=3000
        )
        DOM.add(toast.element)

        @when(toast.events.dismiss)
        def handle_dismiss(sender):
            print("Toast dismissed")
    """

    def __init__(self, message="", variant="info", duration=3000,
                 position="top-right", dismissible=True, **kwargs):
        """
        Initialize a toast notification.

        Args:
            message: Toast message
            variant: Color variant (success, warning, danger, info)
            duration: Auto-dismiss duration in ms (0 = no auto-dismiss)
            position: Toast position (top-right, top-left, bottom-right, bottom-left, top-center, bottom-center)
            dismissible: Whether toast can be dismissed
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="toast", **kwargs)

        self._set_state(
            message=message,
            variant=variant,
            duration=duration,
            position=position,
            dismissible=dismissible,
            visible=True
        )

        self._create_event('dismiss')

        self._init_macro()

    def _get_position_styles(self):
        """Get position-specific styles."""
        positions = {
            "top-right": {"top": "20px", "right": "20px"},
            "top-left": {"top": "20px", "left": "20px"},
            "bottom-right": {"bottom": "20px", "right": "20px"},
            "bottom-left": {"bottom": "20px", "left": "20px"},
            "top-center": {"top": "20px", "left": "50%", "transform": "translateX(-50%)"},
            "bottom-center": {"bottom": "20px", "left": "50%", "transform": "translateX(-50%)"}
        }
        position = self._get_state('position')
        return positions.get(position, positions["top-right"])

    def _get_variant_styles(self):
        """Get variant-specific styles."""
        variants = {
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
            }
        }
        variant = self._get_state('variant')
        return variants.get(variant, variants["info"])

    def _create_elements(self):
        """Create the toast element."""
        if not self._get_state('visible'):
            empty = Div(style={"display": "none"})
            self._register_element('container', empty)
            return empty

        position_styles = self._get_position_styles()
        variant_styles = self._get_variant_styles()

        toast_styles = {
            "position": "fixed",
            "display": "flex",
            "align_items": "center",
            "gap": "12px",
            "padding": "12px 16px",
            "border_radius": "8px",
            "box_shadow": "0 4px 12px rgba(0, 0, 0, 0.15)",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "font_size": "14px",
            "z_index": "9999",
            "min_width": "250px",
            "max_width": "400px",
            "animation": "slideIn 0.3s ease",
            **position_styles,
            **variant_styles
        }

        # Inject toast keyframes using Pythonic approach
        inject_keyframes('component-lib-toast', {
            'toast-slideIn': {
                'from': {
                    'opacity': '0',
                    'transform': 'translateY(-20px)'
                },
                'to': {
                    'opacity': '1',
                    'transform': 'translateY(0)'
                }
            }
        })

        # Update animation name to match injected keyframe
        toast_styles["animation"] = "toast-slideIn 0.3s ease"

        container = Div(style={"display": "inline-block"})

        toast = Div(style=toast_styles)

        # Message
        message_styles = {
            "flex": "1"
        }
        message = Span(self._get_state('message'), style=message_styles)
        toast.add(message)
        self._register_element('message', message)

        # Dismiss button
        if self._get_state('dismissible'):
            close_styles = {
                "cursor": "pointer",
                "font_size": "18px",
                "font_weight": "bold",
                "opacity": "0.8",
                "padding": "0 4px",
                "transition": "opacity 0.2s ease"
            }
            close_btn = Span("×", style=close_styles)
            toast.add(close_btn)

            @when(close_btn.events.click)
            def on_close(sender, *args):
                self.dismiss()

            @when(close_btn.events.mouseenter)
            def on_hover(sender, *args):
                close_btn.style.opacity = "1"

            @when(close_btn.events.mouseleave)
            def on_leave(sender, *args):
                close_btn.style.opacity = "0.8"

        container.add(toast)
        self._register_element('toast', toast)
        self._register_element('container', container)

        # Auto-dismiss timer
        duration = self._get_state('duration')
        if duration > 0:
            from js import setTimeout
            setTimeout(lambda: self.dismiss(), duration)

        return container

    def dismiss(self):
        """Dismiss the toast."""
        self._set_state(visible=False)
        container = self._get_element('container')
        if container:
            container.style.display = "none"
        self.events.fire('dismiss')