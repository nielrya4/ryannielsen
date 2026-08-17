"""
Layout component library for Antioch.

Provides layout components for structuring page content.
"""
from antioch import *
from antioch.macros.base import Macro


class Grid(Macro):
    """
    A responsive grid layout component.

    Features:
    - Configurable columns
    - Gap control
    - Responsive breakpoints
    - Alignment options

    Usage:
        grid = Grid(columns=3, gap="20px")
        grid.add(Card("Item 1"), Card("Item 2"), Card("Item 3"))
        DOM.add(grid.element)
    """

    def __init__(self, columns=1, gap="16px", align_items="stretch",
                 justify_items="stretch", **kwargs):
        """
        Initialize a grid layout.

        Args:
            columns: Number of columns or custom template (e.g., "1fr 2fr 1fr")
            gap: Gap between grid items
            align_items: Vertical alignment (start, end, center, stretch)
            justify_items: Horizontal alignment (start, end, center, stretch)
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="grid", **kwargs)

        self._set_state(
            columns=columns,
            gap=gap,
            align_items=align_items,
            justify_items=justify_items,
            children=[]
        )

        self._init_macro()

    def _create_elements(self):
        """Create the grid container."""
        columns = self._get_state('columns')

        # Handle columns as number or template string
        if isinstance(columns, int):
            grid_template = f"repeat({columns}, 1fr)"
        else:
            grid_template = columns

        grid_styles = {
            "display": "grid",
            "grid_template_columns": grid_template,
            "gap": self._get_state('gap'),
            "align_items": self._get_state('align_items'),
            "justify_items": self._get_state('justify_items'),
            "width": "100%"
        }

        container = Div(style=grid_styles)
        self._register_element('container', container)

        # Add children
        for child in self._get_state('children'):
            if hasattr(child, 'element'):
                container.add(child.element)
            else:
                container.add(child)

        return container

    def add(self, *children):
        """Add children to the grid."""
        current_children = self._get_state('children')
        current_children.extend(children)
        self._set_state(children=current_children)

        container = self._get_element('container')
        if container:
            for child in children:
                if hasattr(child, 'element'):
                    container.add(child.element)
                else:
                    container.add(child)


class Flex(Macro):
    """
    A flexible box layout component.

    Features:
    - Horizontal or vertical direction
    - Gap control
    - Alignment and justification
    - Wrap control

    Usage:
        flex = Flex(direction="row", gap="12px", align="center")
        flex.add(Button("First"), Button("Second"), Button("Third"))
        DOM.add(flex.element)
    """

    def __init__(self, direction="row", gap="0px", align="stretch",
                 justify="flex-start", wrap="nowrap", **kwargs):
        """
        Initialize a flex layout.

        Args:
            direction: Flex direction (row, column, row-reverse, column-reverse)
            gap: Gap between flex items
            align: Cross-axis alignment (flex-start, flex-end, center, stretch, baseline)
            justify: Main-axis justification (flex-start, flex-end, center, space-between, space-around, space-evenly)
            wrap: Flex wrap (nowrap, wrap, wrap-reverse)
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="flex", **kwargs)

        self._set_state(
            direction=direction,
            gap=gap,
            align=align,
            justify=justify,
            wrap=wrap,
            children=[]
        )

        self._init_macro()

    def _create_elements(self):
        """Create the flex container."""
        flex_styles = {
            "display": "flex",
            "flex_direction": self._get_state('direction'),
            "gap": self._get_state('gap'),
            "align_items": self._get_state('align'),
            "justify_content": self._get_state('justify'),
            "flex_wrap": self._get_state('wrap')
        }

        container = Div(style=flex_styles)
        self._register_element('container', container)

        # Add children
        for child in self._get_state('children'):
            if hasattr(child, 'element'):
                container.add(child.element)
            else:
                container.add(child)

        return container

    def add(self, *children):
        """Add children to the flex container."""
        current_children = self._get_state('children')
        current_children.extend(children)
        self._set_state(children=current_children)

        container = self._get_element('container')
        if container:
            for child in children:
                if hasattr(child, 'element'):
                    container.add(child.element)
                else:
                    container.add(child)


class Stack(Macro):
    """
    A vertical or horizontal stack layout component.

    Features:
    - Vertical or horizontal stacking
    - Consistent spacing between items
    - Alignment options
    - Dividers between items

    Usage:
        stack = Stack(spacing="16px", dividers=True)
        stack.add(Card("Item 1"), Card("Item 2"), Card("Item 3"))
        DOM.add(stack.element)
    """

    def __init__(self, spacing="12px", direction="vertical", align="stretch",
                 dividers=False, **kwargs):
        """
        Initialize a stack layout.

        Args:
            spacing: Space between stacked items
            direction: Stack direction (vertical or horizontal)
            align: Cross-axis alignment
            dividers: Whether to show dividers between items
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="stack", **kwargs)

        self._set_state(
            spacing=spacing,
            direction=direction,
            align=align,
            dividers=dividers,
            children=[]
        )

        self._init_macro()

    def _create_elements(self):
        """Create the stack container."""
        is_vertical = self._get_state('direction') == 'vertical'

        stack_styles = {
            "display": "flex",
            "flex_direction": "column" if is_vertical else "row",
            "gap": self._get_state('spacing'),
            "align_items": self._get_state('align')
        }

        container = Div(style=stack_styles)
        self._register_element('container', container)

        # Add children with optional dividers
        children = self._get_state('children')
        show_dividers = self._get_state('dividers')

        for i, child in enumerate(children):
            if hasattr(child, 'element'):
                container.add(child.element)
            else:
                container.add(child)

            # Add divider between items (not after last)
            if show_dividers and i < len(children) - 1:
                divider = Divider(orientation='horizontal' if is_vertical else 'vertical')
                container.add(divider.element)

        return container

    def add(self, *children):
        """Add children to the stack."""
        current_children = self._get_state('children')
        current_children.extend(children)
        self._set_state(children=current_children)

        # Rebuild container to handle dividers properly
        container = self._get_element('container')
        if container:
            # Clear and rebuild
            container.dom_element.innerHTML = ""

            show_dividers = self._get_state('dividers')
            all_children = self._get_state('children')

            for i, child in enumerate(all_children):
                if hasattr(child, 'element'):
                    container.add(child.element)
                else:
                    container.add(child)

                # Add divider between items
                if show_dividers and i < len(all_children) - 1:
                    is_vertical = self._get_state('direction') == 'vertical'
                    divider = Divider(orientation='horizontal' if is_vertical else 'vertical')
                    container.add(divider.element)


class Divider(Macro):
    """
    A visual divider/separator component.

    Features:
    - Horizontal or vertical orientation
    - Customizable color and thickness
    - Spacing control

    Usage:
        divider = Divider(orientation="horizontal", color="#e5e7eb")
        DOM.add(divider.element)
    """

    def __init__(self, orientation="horizontal", color="#e5e7eb",
                 thickness="1px", spacing="12px", **kwargs):
        """
        Initialize a divider.

        Args:
            orientation: Divider orientation (horizontal or vertical)
            color: Divider color
            thickness: Divider thickness
            spacing: Margin around divider
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="divider", **kwargs)

        self._set_state(
            orientation=orientation,
            color=color,
            thickness=thickness,
            spacing=spacing
        )

        self._init_macro()

    def _create_elements(self):
        """Create the divider element."""
        is_horizontal = self._get_state('orientation') == 'horizontal'

        divider_styles = {
            "background": self._get_state('color'),
            "margin": f"{self._get_state('spacing')} 0" if is_horizontal else f"0 {self._get_state('spacing')}",
            "border": "none"
        }

        if is_horizontal:
            divider_styles["width"] = "100%"
            divider_styles["height"] = self._get_state('thickness')
        else:
            divider_styles["width"] = self._get_state('thickness')
            divider_styles["height"] = "100%"
            divider_styles["display"] = "inline-block"

        hr_elem = Hr(style=divider_styles)
        self._register_element('divider', hr_elem)

        return hr_elem


class Container(Macro):
    """
    A centered container with max-width for content.

    Features:
    - Max-width control
    - Centered alignment
    - Responsive padding

    Usage:
        container = Container(max_width="1200px")
        container.add(H1("Welcome"), P("Content here"))
        DOM.add(container.element)
    """

    def __init__(self, max_width="1200px", padding="20px", **kwargs):
        """
        Initialize a container.

        Args:
            max_width: Maximum container width
            padding: Container padding
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="container", **kwargs)

        self._set_state(
            max_width=max_width,
            padding=padding,
            children=[]
        )

        self._init_macro()

    def _create_elements(self):
        """Create the container element."""
        container_styles = {
            "max_width": self._get_state('max_width'),
            "margin": "0 auto",
            "padding": self._get_state('padding'),
            "width": "100%",
            "box_sizing": "border-box"
        }

        container = Div(style=container_styles)
        self._register_element('container', container)

        # Add children
        for child in self._get_state('children'):
            if hasattr(child, 'element'):
                container.add(child.element)
            else:
                container.add(child)

        return container

    def add(self, *children):
        """Add children to the container."""
        current_children = self._get_state('children')
        current_children.extend(children)
        self._set_state(children=current_children)

        container = self._get_element('container')
        if container:
            for child in children:
                if hasattr(child, 'element'):
                    container.add(child.element)
                else:
                    container.add(child)


class Spacer(Macro):
    """
    A flexible spacer for pushing items in flex layouts.

    Usage:
        flex = Flex(direction="row")
        flex.add(Button("Left"), Spacer(), Button("Right"))
        DOM.add(flex.element)
    """

    def __init__(self, **kwargs):
        """Initialize a spacer."""
        super().__init__(macro_type="spacer", **kwargs)
        self._init_macro()

    def _create_elements(self):
        """Create the spacer element."""
        spacer_styles = {
            "flex": "1"
        }

        spacer = Div(style=spacer_styles)
        self._register_element('spacer', spacer)

        return spacer