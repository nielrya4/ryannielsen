"""
Display component library for Antioch.

Provides display components like cards, panels, lists, and avatars.
"""
from antioch import *
from antioch.macros.base import Macro


class Card(Macro):
    """
    A card container component.

    Features:
    - Header, body, and footer sections
    - Elevation/shadow options
    - Hover effects
    - Padding control

    Usage:
        card = Card(title="Card Title", subtitle="Subtitle")
        card.set_body(P("Card content here"))
        card.set_footer(Button("Action"))
        DOM.add(card)
    """

    def __init__(self, title="", subtitle="", elevation="medium",
                 hover=False, padding="20px", **kwargs):
        """
        Initialize a card.

        Args:
            title: Card title
            subtitle: Card subtitle
            elevation: Shadow elevation (none, small, medium, large)
            hover: Whether to show hover effect
            padding: Card padding
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="card", **kwargs)

        self._set_state(
            title=title,
            subtitle=subtitle,
            elevation=elevation,
            hover=hover,
            padding=padding,
            body_content=None,
            footer_content=None
        )

        self._init_macro()

    def _get_elevation_shadow(self):
        """Get shadow based on elevation."""
        shadows = {
            "none": "none",
            "small": "0 1px 3px rgba(0, 0, 0, 0.12)",
            "medium": "0 4px 6px rgba(0, 0, 0, 0.1)",
            "large": "0 10px 15px rgba(0, 0, 0, 0.1)"
        }
        elevation = self._get_state('elevation')
        return shadows.get(elevation, shadows["medium"])

    def _create_elements(self):
        """Create the card element."""
        card_styles = {
            "background": "white",
            "border_radius": "8px",
            "border": "1px solid #e5e7eb",
            "box_shadow": self._get_elevation_shadow(),
            "overflow": "hidden",
            "transition": "box-shadow 0.2s ease, transform 0.2s ease",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        }

        card = Div(style=card_styles)
        self._register_element('card', card)

        # Hover effect
        if self._get_state('hover'):
            @when(card.events.mouseenter)
            def on_hover(sender, *args):
                card.style.transform = "translateY(-4px)"
                card.style.box_shadow = "0 12px 20px rgba(0, 0, 0, 0.15)"

            @when(card.events.mouseleave)
            def on_leave(sender, *args):
                card.style.transform = "translateY(0)"
                card.style.box_shadow = self._get_elevation_shadow()

        # Header
        title = self._get_state('title')
        subtitle = self._get_state('subtitle')

        if title or subtitle:
            header_styles = {
                "padding": self._get_state('padding'),
                "border_bottom": "1px solid #e5e7eb"
            }
            header = Div(style=header_styles)

            if title:
                title_styles = {
                    "font_size": "18px",
                    "font_weight": "600",
                    "color": "#111827",
                    "margin": "0 0 4px 0"
                }
                title_elem = H3(title, style=title_styles)
                header.add(title_elem)
                self._register_element('title', title_elem)

            if subtitle:
                subtitle_styles = {
                    "font_size": "14px",
                    "color": "#6b7280",
                    "margin": "0"
                }
                subtitle_elem = P(subtitle, style=subtitle_styles)
                header.add(subtitle_elem)
                self._register_element('subtitle', subtitle_elem)

            card.add(header)
            self._register_element('header', header)

        # Body
        body_styles = {
            "padding": self._get_state('padding')
        }
        body = Div(style=body_styles)
        card.add(body)
        self._register_element('body', body)

        # Add body content if provided
        body_content = self._get_state('body_content')
        if body_content:
            if hasattr(body_content, 'element'):
                body.add(body_content)
            else:
                body.add(body_content)

        # Footer (initially empty)
        footer_styles = {
            "padding": self._get_state('padding'),
            "border_top": "1px solid #e5e7eb",
            "display": "none"
        }
        footer = Div(style=footer_styles)
        card.add(footer)
        self._register_element('footer', footer)

        return card

    def set_body(self, content):
        """Set the card body content."""
        self._set_state(body_content=content)
        body = self._get_element('body')
        if body:
            body.dom_element.innerHTML = ""
            if hasattr(content, 'element'):
                body.add(content)
            else:
                body.add(content)

    def set_footer(self, content):
        """Set the card footer content."""
        self._set_state(footer_content=content)
        footer = self._get_element('footer')
        if footer:
            footer.style.display = "block"
            footer.dom_element.innerHTML = ""
            if hasattr(content, 'element'):
                footer.add(content)
            else:
                footer.add(content)


class Panel(Macro):
    """
    A simple panel container component.

    Features:
    - Border and background options
    - Padding control
    - Rounded corners

    Usage:
        panel = Panel(background="#f9fafb")
        panel.add(H3("Panel Title"), P("Panel content"))
        DOM.add(panel)
    """

    def __init__(self, background="white", border_color="#e5e7eb",
                 padding="20px", rounded=True, **kwargs):
        """
        Initialize a panel.

        Args:
            background: Background color
            border_color: Border color
            padding: Panel padding
            rounded: Whether to round corners
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="panel", **kwargs)

        self._set_state(
            background=background,
            border_color=border_color,
            padding=padding,
            rounded=rounded,
            children=[]
        )

        self._init_macro()

    def _create_elements(self):
        """Create the panel element."""
        panel_styles = {
            "background": self._get_state('background'),
            "border": f"1px solid {self._get_state('border_color')}",
            "border_radius": "8px" if self._get_state('rounded') else "0",
            "padding": self._get_state('padding'),
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        }

        panel = Div(style=panel_styles)
        self._register_element('panel', panel)

        # Add children
        for child in self._get_state('children'):
            if hasattr(child, 'element'):
                panel.add(child)
            else:
                panel.add(child)

        return panel

    def add(self, *children):
        """Add children to the panel."""
        current_children = self._get_state('children')
        current_children.extend(children)
        self._set_state(children=current_children)

        panel = self._get_element('panel')
        if panel:
            for child in children:
                if hasattr(child, 'element'):
                    panel.add(child)
                else:
                    panel.add(child)


class ListGroup(Macro):
    """
    A list group component for displaying lists of items.

    Features:
    - Multiple list items
    - Clickable items
    - Active item highlighting
    - Badge support

    Usage:
        list_group = ListGroup()
        list_group.add_item("Item 1", item_id="1")
        list_group.add_item("Item 2", item_id="2", badge="New")
        list_group.add_item("Item 3", item_id="3", active=True)
        DOM.add(list_group)

        @when(list_group.events.item_click)
        def handle_click(sender, item_id):
            print(f"Clicked: {item_id}")
    """

    def __init__(self, **kwargs):
        """Initialize a list group."""
        super().__init__(macro_type="list_group", **kwargs)

        self._set_state(
            items=[],
            active_item=None
        )

        self._create_event('item_click')

        self._init_macro()

    def _create_elements(self):
        """Create the list group element."""
        list_styles = {
            "border": "1px solid #e5e7eb",
            "border_radius": "8px",
            "overflow": "hidden",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        }

        list_container = Div(style=list_styles)
        self._register_element('list_container', list_container)

        # Add items
        for item in self._get_state('items'):
            self._add_item_element(list_container, item)

        return list_container

    def _add_item_element(self, container, item):
        """Add a list item element."""
        is_active = item['id'] == self._get_state('active_item') or item.get('active', False)

        item_styles = {
            "display": "flex",
            "align_items": "center",
            "justify_content": "space-between",
            "padding": "12px 16px",
            "border_bottom": "1px solid #e5e7eb",
            "background": "#667eea" if is_active else "white",
            "color": "white" if is_active else "#374151",
            "cursor": "pointer",
            "transition": "background 0.2s ease"
        }

        item_elem = Div(style=item_styles)

        # Label
        label = Span(item['label'])
        item_elem.add(label)

        # Badge
        if item.get('badge'):
            badge_styles = {
                "background": "#e5e7eb" if not is_active else "rgba(255, 255, 255, 0.3)",
                "color": "#374151" if not is_active else "white",
                "padding": "2px 8px",
                "border_radius": "999px",
                "font_size": "12px",
                "font_weight": "500"
            }
            badge = Span(item['badge'], style=badge_styles)
            item_elem.add(badge)

        @when(item_elem.events.click)
        def on_click(sender, *args):
            self.set_active(item['id'])
            self.events.fire('item_click', item['id'])

        @when(item_elem.events.mouseenter)
        def on_hover(sender, *args):
            if not is_active:
                item_elem.style.background = "#f9fafb"

        @when(item_elem.events.mouseleave)
        def on_leave(sender, *args):
            if not is_active:
                item_elem.style.background = "white"

        container.add(item_elem)

    def add_item(self, label, item_id=None, badge=None, active=False):
        """Add a list item."""
        if item_id is None:
            item_id = label.lower().replace(' ', '_')

        item = {
            'label': label,
            'id': item_id,
            'badge': badge,
            'active': active
        }

        items = self._get_state('items')
        items.append(item)
        self._set_state(items=items)

        if active:
            self._set_state(active_item=item_id)

        list_container = self._get_element('list_container')
        if list_container:
            # Rebuild list
            list_container.dom_element.innerHTML = ""
            for itm in self._get_state('items'):
                self._add_item_element(list_container, itm)

    def set_active(self, item_id):
        """Set the active list item."""
        self._set_state(active_item=item_id)

        # Rebuild list
        list_container = self._get_element('list_container')
        if list_container:
            list_container.dom_element.innerHTML = ""
            for item in self._get_state('items'):
                self._add_item_element(list_container, item)


class Avatar(Macro):
    """
    An avatar component for user profile images or initials.

    Features:
    - Image support
    - Initials fallback
    - Multiple sizes
    - Status indicator option

    Usage:
        avatar = Avatar(name="John Doe", size="large")
        DOM.add(avatar)

        # With image
        avatar_img = Avatar(image_url="https://example.com/avatar.jpg")
        DOM.add(avatar_img)
    """

    def __init__(self, name="", image_url="", size="medium",
                 status=None, background="#667eea", **kwargs):
        """
        Initialize an avatar.

        Args:
            name: Name for initials (used if no image)
            image_url: Avatar image URL
            size: Avatar size (small, medium, large, xlarge)
            status: Status indicator (online, offline, away, busy)
            background: Background color for initials
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="avatar", **kwargs)

        self._set_state(
            name=name,
            image_url=image_url,
            size=size,
            status=status,
            background=background
        )

        self._init_macro()

    def _get_size_value(self):
        """Get size value in pixels."""
        sizes = {
            "small": "32px",
            "medium": "48px",
            "large": "64px",
            "xlarge": "96px"
        }
        size = self._get_state('size')
        return sizes.get(size, sizes["medium"])

    def _get_initials(self):
        """Get initials from name."""
        name = self._get_state('name')
        if not name:
            return "?"

        parts = name.strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        elif len(parts) == 1:
            return parts[0][0].upper()
        return "?"

    def _get_status_color(self):
        """Get status indicator color."""
        colors = {
            "online": "#10b981",
            "offline": "#6b7280",
            "away": "#f59e0b",
            "busy": "#ef4444"
        }
        status = self._get_state('status')
        return colors.get(status, colors["offline"])

    def _create_elements(self):
        """Create the avatar element."""
        size = self._get_size_value()

        container_styles = {
            "position": "relative",
            "display": "inline-block"
        }
        container = Div(style=container_styles)

        avatar_styles = {
            "width": size,
            "height": size,
            "border_radius": "50%",
            "display": "flex",
            "align_items": "center",
            "justify_content": "center",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "font_weight": "600",
            "color": "white",
            "overflow": "hidden"
        }

        image_url = self._get_state('image_url')

        if image_url:
            # Image avatar
            avatar_styles["background"] = "#f3f4f6"
            avatar = Div(style=avatar_styles)

            img_styles = {
                "width": "100%",
                "height": "100%",
                "object_fit": "cover"
            }
            img = Img(src=image_url, alt=self._get_state('name'), style=img_styles)
            avatar.add(img)
        else:
            # Initials avatar
            avatar_styles["background"] = self._get_state('background')
            avatar_styles["font_size"] = f"{int(size[:-2]) // 2}px"

            initials = self._get_initials()
            avatar = Div(initials, style=avatar_styles)

        container.add(avatar)
        self._register_element('avatar', avatar)

        # Status indicator
        status = self._get_state('status')
        if status:
            status_size = f"{int(size[:-2]) // 4}px"
            status_styles = {
                "position": "absolute",
                "bottom": "0",
                "right": "0",
                "width": status_size,
                "height": status_size,
                "background": self._get_status_color(),
                "border": "2px solid white",
                "border_radius": "50%"
            }
            status_indicator = Div(style=status_styles)
            container.add(status_indicator)
            self._register_element('status', status_indicator)

        self._register_element('container', container)
        return container


class AvatarGroup(Macro):
    """
    A group of overlapping avatars.

    Features:
    - Multiple avatars
    - Overlapping layout
    - Max count with overflow indicator

    Usage:
        group = AvatarGroup(max_count=3)
        group.add_avatar("John Doe")
        group.add_avatar("Jane Smith")
        group.add_avatar("Bob Johnson")
        group.add_avatar("Alice Williams")
        DOM.add(group)
    """

    def __init__(self, max_count=5, size="medium", **kwargs):
        """
        Initialize an avatar group.

        Args:
            max_count: Maximum avatars to display
            size: Avatar size
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="avatar_group", **kwargs)

        self._set_state(
            max_count=max_count,
            size=size,
            avatars=[]
        )

        self._init_macro()

    def _create_elements(self):
        """Create the avatar group element."""
        group_styles = {
            "display": "flex",
            "align_items": "center"
        }
        group = Div(style=group_styles)
        self._register_element('group', group)

        avatars = self._get_state('avatars')
        max_count = self._get_state('max_count')

        # Show avatars up to max_count
        visible_avatars = avatars[:max_count]
        for i, avatar_data in enumerate(visible_avatars):
            avatar_container = Div(style={
                "margin_left": "-8px" if i > 0 else "0",
                "position": "relative",
                "z_index": str(len(visible_avatars) - i)
            })

            avatar = Avatar(
                name=avatar_data.get('name', ''),
                image_url=avatar_data.get('image_url', ''),
                size=self._get_state('size'),
                background=avatar_data.get('background', '#667eea')
            )

            # Add border for overlap visibility
            avatar.element.style.border = "2px solid white"

            avatar_container.add(avatar)
            group.add(avatar_container)

        # Overflow indicator
        if len(avatars) > max_count:
            overflow_count = len(avatars) - max_count
            overflow_container = Div(style={
                "margin_left": "-8px",
                "position": "relative",
                "z_index": "0"
            })

            overflow_avatar = Avatar(
                name=f"+{overflow_count}",
                size=self._get_state('size'),
                background="#6b7280"
            )
            overflow_avatar.element.style.border = "2px solid white"

            overflow_container.add(overflow_avatar)
            group.add(overflow_container)

        return group

    def add_avatar(self, name="", image_url="", background="#667eea"):
        """Add an avatar to the group."""
        avatar_data = {
            'name': name,
            'image_url': image_url,
            'background': background
        }

        avatars = self._get_state('avatars')
        avatars.append(avatar_data)
        self._set_state(avatars=avatars)

        # Rebuild group
        group = self._get_element('group')
        if group:
            group.dom_element.innerHTML = ""

            visible_avatars = avatars[:self._get_state('max_count')]
            for i, av_data in enumerate(visible_avatars):
                avatar_container = Div(style={
                    "margin_left": "-8px" if i > 0 else "0",
                    "position": "relative",
                    "z_index": str(len(visible_avatars) - i)
                })

                avatar = Avatar(
                    name=av_data.get('name', ''),
                    image_url=av_data.get('image_url', ''),
                    size=self._get_state('size'),
                    background=av_data.get('background', '#667eea')
                )
                avatar.element.style.border = "2px solid white"

                avatar_container.add(avatar)
                group.add(avatar_container)

            if len(avatars) > self._get_state('max_count'):
                overflow_count = len(avatars) - self._get_state('max_count')
                overflow_container = Div(style={
                    "margin_left": "-8px",
                    "position": "relative",
                    "z_index": "0"
                })

                overflow_avatar = Avatar(
                    name=f"+{overflow_count}",
                    size=self._get_state('size'),
                    background="#6b7280"
                )
                overflow_avatar.element.style.border = "2px solid white"

                overflow_container.add(overflow_avatar)
                group.add(overflow_container)