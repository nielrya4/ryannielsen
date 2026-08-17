"""
Input component library for Antioch.

Provides form input components with consistent styling and validation.
"""
from antioch import *
from antioch.elements import Select as SelectElement
from antioch.macros.base import Macro


class TextInput(Macro):
    """
    A styled text input field component.

    Features:
    - Pre-styled with consistent design
    - Placeholder support
    - Disabled state
    - Error state with message
    - Label support
    - Value change events
    - Size variants

    Usage:
        input_field = TextInput(
            label="Username",
            placeholder="Enter your username",
            value=""
        )
        DOM.add(input_field.element)

        @when(input_field.events.change)
        def handle_change(sender, value):
            print(f"Value changed to: {value}")
    """

    def __init__(self, label="", placeholder="", value="", disabled=False,
                 error="", size="medium", input_type="text", **kwargs):
        """
        Initialize a text input.

        Args:
            label: Input label text
            placeholder: Placeholder text
            value: Initial value
            disabled: Whether input is disabled
            error: Error message to display
            size: Input size - "small", "medium", or "large"
            input_type: HTML input type (text, email, password, etc.)
            **kwargs: Additional arguments passed to Macro
        """
        super().__init__(macro_type="text_input", **kwargs)

        self._set_state(
            label=label,
            placeholder=placeholder,
            value=value,
            disabled=disabled,
            error=error,
            size=size,
            input_type=input_type
        )

        self._create_event('change')
        self._create_event('focus')
        self._create_event('blur')
        self._create_event('input')

        self._init_macro()

    def _get_size_styles(self):
        """Get size-specific styles."""
        sizes = {
            "small": {
                "padding": "6px 12px",
                "font_size": "12px",
                "height": "32px"
            },
            "medium": {
                "padding": "10px 14px",
                "font_size": "14px",
                "height": "40px"
            },
            "large": {
                "padding": "12px 16px",
                "font_size": "16px",
                "height": "48px"
            }
        }
        size = self._get_state('size')
        return sizes.get(size, sizes["medium"])

    def _create_elements(self):
        """Create the input UI elements."""
        container_styles = {
            "display": "flex",
            "flex_direction": "column",
            "gap": "6px",
            "width": "100%"
        }
        container = Div(style=container_styles)

        # Label
        label_text = self._get_state('label')
        if label_text:
            label_styles = {
                "font_size": "14px",
                "font_weight": "500",
                "color": "#374151",
                "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            }
            label = Label(label_text, style=label_styles)
            container.add(label)
            self._register_element('label', label)

        # Input field
        size_styles = self._get_size_styles()
        has_error = bool(self._get_state('error'))

        input_styles = {
            "width": "100%",
            "border": f"2px solid {'#ef4444' if has_error else '#d1d5db'}",
            "border_radius": "6px",
            "outline": "none",
            "transition": "all 0.2s ease",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "box_sizing": "border-box",
            **size_styles
        }

        if self._get_state('disabled'):
            input_styles["background"] = "#f3f4f6"
            input_styles["cursor"] = "not-allowed"
            input_styles["opacity"] = "0.6"

        # Create input element - only pass disabled if True
        input_params = {
            'type': self._get_state('input_type'),
            'placeholder': self._get_state('placeholder'),
            'value': self._get_state('value'),
            'style': input_styles
        }

        # Only add disabled attribute if actually disabled
        if self._get_state('disabled'):
            input_params['disabled'] = True

        input_elem = Input(**input_params)
        container.add(input_elem)
        self._register_element('input', input_elem)

        # Error message
        error_msg = self._get_state('error')
        if error_msg:
            error_styles = {
                "font_size": "12px",
                "color": "#ef4444",
                "margin_top": "2px",
                "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            }
            error_label = Span(error_msg, style=error_styles)
            container.add(error_label)
            self._register_element('error', error_label)

        # Wire events
        if not self._get_state('disabled'):
            self._wire_events(input_elem)

        self._register_element('container', container)
        return container

    def _wire_events(self, input_elem):
        """Wire DOM events to unified event system."""

        @when(input_elem.events.input)
        def on_input(sender, *args):
            value = input_elem.dom_element.value
            self._set_state(value=value)
            self.events.fire('input', value)

        @when(input_elem.events.change)
        def on_change(sender, *args):
            value = input_elem.dom_element.value
            self._set_state(value=value)
            self.events.fire('change', value)

        @when(input_elem.events.focus)
        def on_focus(sender, *args):
            if not self._get_state('error'):
                input_elem.style.border_color = "#667eea"
                input_elem.style.box_shadow = "0 0 0 3px rgba(102, 126, 234, 0.1)"
            self.events.fire('focus')

        @when(input_elem.events.blur)
        def on_blur(sender, *args):
            if not self._get_state('error'):
                input_elem.style.border_color = "#d1d5db"
                input_elem.style.box_shadow = "none"
            self.events.fire('blur')

    def get_value(self):
        """Get the current input value."""
        return self._get_state('value')

    def set_value(self, value):
        """Set the input value."""
        self._set_state(value=value)
        input_elem = self._get_element('input')
        if input_elem:
            input_elem.dom_element.value = value

    def set_error(self, error):
        """Set error message."""
        self._set_state(error=error)
        input_elem = self._get_element('input')
        if input_elem:
            if error:
                input_elem.style.border_color = "#ef4444"
            else:
                input_elem.style.border_color = "#d1d5db"


class TextArea(Macro):
    """
    A styled multi-line text area component.

    Features:
    - Multi-line text input
    - Auto-resize option
    - Row count control
    - All TextInput features

    Usage:
        textarea = TextArea(
            label="Description",
            placeholder="Enter description...",
            rows=4
        )
        DOM.add(textarea.element)
    """

    def __init__(self, label="", placeholder="", value="", disabled=False,
                 error="", rows=3, resize=True, **kwargs):
        """Initialize a text area."""
        super().__init__(macro_type="text_area", **kwargs)

        self._set_state(
            label=label,
            placeholder=placeholder,
            value=value,
            disabled=disabled,
            error=error,
            rows=rows,
            resize=resize
        )

        self._create_event('change')
        self._create_event('focus')
        self._create_event('blur')
        self._create_event('input')

        self._init_macro()

    def _create_elements(self):
        """Create the textarea UI elements."""
        container_styles = {
            "display": "flex",
            "flex_direction": "column",
            "gap": "6px",
            "width": "100%"
        }
        container = Div(style=container_styles)

        # Label
        label_text = self._get_state('label')
        if label_text:
            label_styles = {
                "font_size": "14px",
                "font_weight": "500",
                "color": "#374151",
                "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            }
            label = Label(label_text, style=label_styles)
            container.add(label)
            self._register_element('label', label)

        # TextArea
        has_error = bool(self._get_state('error'))

        textarea_styles = {
            "width": "100%",
            "padding": "10px 14px",
            "border": f"2px solid {'#ef4444' if has_error else '#d1d5db'}",
            "border_radius": "6px",
            "font_size": "14px",
            "outline": "none",
            "transition": "all 0.2s ease",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "resize": "vertical" if self._get_state('resize') else "none",
            "box_sizing": "border-box"
        }

        if self._get_state('disabled'):
            textarea_styles["background"] = "#f3f4f6"
            textarea_styles["cursor"] = "not-allowed"
            textarea_styles["opacity"] = "0.6"

        # Create textarea element - only pass disabled if True
        textarea_params = {
            'placeholder': self._get_state('placeholder'),
            'rows': self._get_state('rows'),
            'style': textarea_styles
        }

        if self._get_state('disabled'):
            textarea_params['disabled'] = True

        textarea_elem = Textarea(self._get_state('value'), **textarea_params)

        container.add(textarea_elem)
        self._register_element('textarea', textarea_elem)

        # Error message
        error_msg = self._get_state('error')
        if error_msg:
            error_styles = {
                "font_size": "12px",
                "color": "#ef4444",
                "margin_top": "2px",
                "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            }
            error_label = Span(error_msg, style=error_styles)
            container.add(error_label)
            self._register_element('error', error_label)

        if not self._get_state('disabled'):
            self._wire_events(textarea_elem)

        self._register_element('container', container)
        return container

    def _wire_events(self, textarea_elem):
        """Wire DOM events."""

        @when(textarea_elem.events.input)
        def on_input(sender, *args):
            value = textarea_elem.dom_element.value
            self._set_state(value=value)
            self.events.fire('input', value)

        @when(textarea_elem.events.change)
        def on_change(sender, *args):
            value = textarea_elem.dom_element.value
            self._set_state(value=value)
            self.events.fire('change', value)

        @when(textarea_elem.events.focus)
        def on_focus(sender, *args):
            if not self._get_state('error'):
                textarea_elem.style.border_color = "#667eea"
                textarea_elem.style.box_shadow = "0 0 0 3px rgba(102, 126, 234, 0.1)"
            self.events.fire('focus')

        @when(textarea_elem.events.blur)
        def on_blur(sender, *args):
            if not self._get_state('error'):
                textarea_elem.style.border_color = "#d1d5db"
                textarea_elem.style.box_shadow = "none"
            self.events.fire('blur')

    def get_value(self):
        """Get the current value."""
        return self._get_state('value')

    def set_value(self, value):
        """Set the value."""
        self._set_state(value=value)
        elem = self._get_element('textarea')
        if elem:
            elem.dom_element.value = value


class Checkbox(Macro):
    """
    A styled checkbox component.

    Features:
    - Custom styling
    - Label support
    - Checked/unchecked states
    - Disabled state
    - Change events

    Usage:
        checkbox = Checkbox(label="I agree to terms", checked=False)
        DOM.add(checkbox.element)

        @when(checkbox.events.change)
        def handle_change(sender, checked):
            print(f"Checked: {checked}")
    """

    def __init__(self, label="", checked=False, disabled=False, **kwargs):
        """Initialize a checkbox."""
        super().__init__(macro_type="checkbox", **kwargs)

        self._set_state(
            label=label,
            checked=checked,
            disabled=disabled
        )

        self._create_event('change')

        self._init_macro()

    def _create_elements(self):
        """Create the checkbox UI elements."""
        container_styles = {
            "display": "flex",
            "align_items": "center",
            "gap": "8px",
            "cursor": "pointer" if not self._get_state('disabled') else "not-allowed",
            "user_select": "none"
        }
        container = Label(style=container_styles)

        # Checkbox input
        checkbox_styles = {
            "width": "18px",
            "height": "18px",
            "cursor": "pointer" if not self._get_state('disabled') else "not-allowed",
            "accent_color": "#667eea"
        }

        # Create checkbox element - only pass boolean attrs if True
        checkbox_params = {
            'style': checkbox_styles
        }

        if self._get_state('checked'):
            checkbox_params['checked'] = True
        if self._get_state('disabled'):
            checkbox_params['disabled'] = True

        checkbox_elem = Input('checkbox', **checkbox_params)

        container.add(checkbox_elem)
        self._register_element('checkbox', checkbox_elem)

        # Label text
        label_text = self._get_state('label')
        if label_text:
            label_styles = {
                "font_size": "14px",
                "color": "#374151",
                "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            }
            if self._get_state('disabled'):
                label_styles["opacity"] = "0.6"

            label_span = Span(label_text, style=label_styles)
            container.add(label_span)
            self._register_element('label', label_span)

        if not self._get_state('disabled'):
            self._wire_events(checkbox_elem)

        self._register_element('container', container)
        return container

    def _wire_events(self, checkbox_elem):
        """Wire DOM events."""

        @when(checkbox_elem.events.change)
        def on_change(sender, *args):
            checked = checkbox_elem.dom_element.checked
            self._set_state(checked=checked)
            self.events.fire('change', checked)

    def is_checked(self):
        """Check if checkbox is checked."""
        return self._get_state('checked')

    def set_checked(self, checked):
        """Set checked state."""
        self._set_state(checked=checked)
        elem = self._get_element('checkbox')
        if elem:
            elem.dom_element.checked = checked


class Radio(Macro):
    """
    A styled radio button component.

    Features:
    - Custom styling
    - Label support
    - Radio group support
    - Disabled state
    - Change events

    Usage:
        radio1 = Radio(label="Option 1", name="choice", value="1")
        radio2 = Radio(label="Option 2", name="choice", value="2")
        DOM.add(radio1.element, radio2.element)

        @when(radio1.events.change)
        def handle_change(sender, checked):
            if checked:
                print("Option 1 selected")
    """

    def __init__(self, label="", name="", value="", checked=False, disabled=False, **kwargs):
        """Initialize a radio button."""
        super().__init__(macro_type="radio", **kwargs)

        self._set_state(
            label=label,
            name=name,
            value=value,
            checked=checked,
            disabled=disabled
        )

        self._create_event('change')

        self._init_macro()

    def _create_elements(self):
        """Create the radio button UI elements."""
        container_styles = {
            "display": "flex",
            "align_items": "center",
            "gap": "8px",
            "cursor": "pointer" if not self._get_state('disabled') else "not-allowed",
            "user_select": "none"
        }
        container = Label(style=container_styles)

        # Radio input
        radio_styles = {
            "width": "18px",
            "height": "18px",
            "cursor": "pointer" if not self._get_state('disabled') else "not-allowed",
            "accent_color": "#667eea"
        }

        # Create radio element - only pass boolean attrs if True
        radio_params = {
            'name': self._get_state('name'),
            'value': self._get_state('value'),
            'style': radio_styles
        }

        if self._get_state('checked'):
            radio_params['checked'] = True
        if self._get_state('disabled'):
            radio_params['disabled'] = True

        radio_elem = Input('radio', **radio_params)

        container.add(radio_elem)
        self._register_element('radio', radio_elem)

        # Label text
        label_text = self._get_state('label')
        if label_text:
            label_styles = {
                "font_size": "14px",
                "color": "#374151",
                "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            }
            if self._get_state('disabled'):
                label_styles["opacity"] = "0.6"

            label_span = Span(label_text, style=label_styles)
            container.add(label_span)
            self._register_element('label', label_span)

        if not self._get_state('disabled'):
            self._wire_events(radio_elem)

        self._register_element('container', container)
        return container

    def _wire_events(self, radio_elem):
        """Wire DOM events."""

        @when(radio_elem.events.change)
        def on_change(sender, *args):
            checked = radio_elem.dom_element.checked
            self._set_state(checked=checked)
            self.events.fire('change', checked)

    def is_checked(self):
        """Check if radio is selected."""
        return self._get_state('checked')


class Select(Macro):
    """
    A styled select dropdown component.

    Features:
    - Custom styling
    - Multiple options
    - Disabled state
    - Label support
    - Change events

    Usage:
        select = Select(
            label="Country",
            options=[
                {"value": "us", "label": "United States"},
                {"value": "uk", "label": "United Kingdom"},
                {"value": "ca", "label": "Canada"}
            ],
            value="us"
        )
        DOM.add(select.element)

        @when(select.events.change)
        def handle_change(sender, value):
            print(f"Selected: {value}")
    """

    def __init__(self, label="", options=None, value="", disabled=False,
                 size="medium", **kwargs):
        """Initialize a select dropdown."""
        super().__init__(macro_type="select", **kwargs)

        if options is None:
            options = []

        self._set_state(
            label=label,
            options=options,
            value=value,
            disabled=disabled,
            size=size
        )

        self._create_event('change')
        self._create_event('focus')
        self._create_event('blur')

        self._init_macro()

    def _get_size_styles(self):
        """Get size-specific styles."""
        sizes = {
            "small": {
                "padding": "6px 32px 6px 12px",
                "font_size": "12px",
                "height": "32px"
            },
            "medium": {
                "padding": "10px 36px 10px 14px",
                "font_size": "14px",
                "height": "40px"
            },
            "large": {
                "padding": "12px 40px 12px 16px",
                "font_size": "16px",
                "height": "48px"
            }
        }
        size = self._get_state('size')
        return sizes.get(size, sizes["medium"])

    def _create_elements(self):
        """Create the select UI elements."""
        container_styles = {
            "display": "flex",
            "flex_direction": "column",
            "gap": "6px",
            "width": "100%"
        }
        container = Div(style=container_styles)

        # Label
        label_text = self._get_state('label')
        if label_text:
            label_styles = {
                "font_size": "14px",
                "font_weight": "500",
                "color": "#374151",
                "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            }
            label = Label(label_text, style=label_styles)
            container.add(label)
            self._register_element('label', label)

        # Select wrapper for custom arrow
        wrapper_styles = {
            "position": "relative",
            "width": "100%"
        }
        wrapper = Div(style=wrapper_styles)

        # Select element
        size_styles = self._get_size_styles()

        select_styles = {
            "width": "100%",
            "border": "2px solid #d1d5db",
            "border_radius": "6px",
            "outline": "none",
            "transition": "all 0.2s ease",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "background": "white",
            "appearance": "none",
            "cursor": "pointer",
            "box_sizing": "border-box",
            **size_styles
        }

        if self._get_state('disabled'):
            select_styles["background"] = "#f3f4f6"
            select_styles["cursor"] = "not-allowed"
            select_styles["opacity"] = "0.6"

        # Create select element - only pass disabled if True
        select_params = {
            'style': select_styles
        }

        if self._get_state('disabled'):
            select_params['disabled'] = True

        select_elem = SelectElement(**select_params)

        # Add options
        for option in self._get_state('options'):
            opt_value = option.get('value', '')
            opt_label = option.get('label', opt_value)
            opt_selected = opt_value == self._get_state('value')

            opt_elem = Option(opt_label, value=opt_value, selected=opt_selected)
            select_elem.add(opt_elem)

        wrapper.add(select_elem)
        self._register_element('select', select_elem)

        # Custom dropdown arrow
        arrow_styles = {
            "position": "absolute",
            "right": "12px",
            "top": "50%",
            "transform": "translateY(-50%)",
            "pointer_events": "none",
            "color": "#6b7280"
        }
        arrow = Span("▼", style=arrow_styles)
        wrapper.add(arrow)

        container.add(wrapper)

        if not self._get_state('disabled'):
            self._wire_events(select_elem)

        self._register_element('container', container)
        return container

    def _wire_events(self, select_elem):
        """Wire DOM events."""

        @when(select_elem.events.change)
        def on_change(sender, *args):
            value = select_elem.dom_element.value
            self._set_state(value=value)
            self.events.fire('change', value)

        @when(select_elem.events.focus)
        def on_focus(sender, *args):
            select_elem.style.border_color = "#667eea"
            select_elem.style.box_shadow = "0 0 0 3px rgba(102, 126, 234, 0.1)"
            self.events.fire('focus')

        @when(select_elem.events.blur)
        def on_blur(sender, *args):
            select_elem.style.border_color = "#d1d5db"
            select_elem.style.box_shadow = "none"
            self.events.fire('blur')

    def get_value(self):
        """Get the selected value."""
        return self._get_state('value')

    def set_value(self, value):
        """Set the selected value."""
        self._set_state(value=value)
        elem = self._get_element('select')
        if elem:
            elem.dom_element.value = value


class Switch(Macro):
    """
    A modern toggle switch component.

    Features:
    - Smooth toggle animation
    - On/off states
    - Disabled state
    - Label support
    - Color customization
    - Change events

    Usage:
        switch = Switch(label="Enable notifications", checked=True)
        DOM.add(switch.element)

        @when(switch.events.change)
        def handle_change(sender, checked):
            print(f"Switch is: {'On' if checked else 'Off'}")
    """

    def __init__(self, label="", checked=False, disabled=False,
                 color="#667eea", **kwargs):
        """
        Initialize a switch.

        Args:
            label: Switch label text
            checked: Whether switch is on
            disabled: Whether switch is disabled
            color: Color when switch is on
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="switch", **kwargs)

        self._set_state(
            label=label,
            checked=checked,
            disabled=disabled,
            color=color
        )

        self._create_event('change')

        self._init_macro()

    def _create_elements(self):
        """Create the switch UI elements."""
        container_styles = {
            "display": "flex",
            "align_items": "center",
            "gap": "12px",
            "cursor": "pointer" if not self._get_state('disabled') else "not-allowed",
            "user_select": "none",
            "padding-top": "2px",
            "padding-bottom": "2px"
        }
        container = Label(style=container_styles)

        # Hidden checkbox input for accessibility
        checkbox_styles = {
            "position": "absolute",
            "opacity": "0",
            "width": "0",
            "height": "0"
        }

        checkbox_params = {
            'style': checkbox_styles
        }

        if self._get_state('checked'):
            checkbox_params['checked'] = True
        if self._get_state('disabled'):
            checkbox_params['disabled'] = True

        checkbox_elem = Input('checkbox', **checkbox_params)
        container.add(checkbox_elem)
        self._register_element('checkbox', checkbox_elem)

        # Switch track
        is_checked = self._get_state('checked')
        is_disabled = self._get_state('disabled')

        track_styles = {
            "position": "relative",
            "width": "40px",
            "height": "20px",
            "background": self._get_state('color') if is_checked else "#d1d5db",
            "border_radius": "12px",
            "transition": "background 0.2s ease",
            "cursor": "pointer" if not is_disabled else "not-allowed"
        }

        if is_disabled:
            track_styles["opacity"] = "0.5"

        track = Div(style=track_styles)
        self._register_element('track', track)

        # Switch thumb (sliding circle)
        thumb_styles = {
            "position": "absolute",
            "top": "2px",
            "left": "22px" if is_checked else "2px",
            "width": "16px",
            "height": "16px",
            "background": "white",
            "border_radius": "50%",
            "transition": "left 0.2s ease",
            "box_shadow": "0 2px 4px rgba(0, 0, 0, 0.2)"
        }

        thumb = Div(style=thumb_styles)
        track.add(thumb)
        self._register_element('thumb', thumb)

        container.add(track)

        # Label text
        label_text = self._get_state('label')
        if label_text:
            label_styles = {
                "font_size": "14px",
                "color": "#374151",
                "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            }
            if is_disabled:
                label_styles["opacity"] = "0.6"

            label_span = Span(label_text, style=label_styles)
            container.add(label_span)
            self._register_element('label', label_span)

        if not is_disabled:
            self._wire_events(checkbox_elem)

        self._register_element('container', container)
        return container

    def _wire_events(self, checkbox_elem):
        """Wire DOM events."""

        @when(checkbox_elem.events.change)
        def on_change(sender, *args):
            checked = checkbox_elem.dom_element.checked
            self._set_state(checked=checked)

            # Update visual elements
            track = self._get_element('track')
            thumb = self._get_element('thumb')

            if track:
                track.style.background = self._get_state('color') if checked else "#d1d5db"

            if thumb:
                thumb.style.left = "22px" if checked else "2px"

            self.events.fire('change', checked)

    def is_checked(self):
        """Check if switch is on."""
        return self._get_state('checked')

    def set_checked(self, checked):
        """Set switch state."""
        self._set_state(checked=checked)

        checkbox = self._get_element('checkbox')
        if checkbox:
            checkbox.dom_element.checked = checked

        track = self._get_element('track')
        if track:
            track.style.background = self._get_state('color') if checked else "#d1d5db"

        thumb = self._get_element('thumb')
        if thumb:
            thumb.style.left = "22px" if checked else "2px"