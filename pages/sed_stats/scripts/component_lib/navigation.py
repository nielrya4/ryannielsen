"""
Navigation component library for Antioch.

Provides navigation components like navbars, breadcrumbs, and side navigation.
"""
import uuid
from antioch import *
from antioch.macros.base import Macro
from antioch.events import Events


class NavBar(Macro):
    """
    A navigation bar component.

    Features:
    - Horizontal navigation
    - Logo/brand support
    - Navigation items
    - Responsive styling

    Usage:
        navbar = NavBar(brand="My App")
        navbar.add_item("Home", "#home")
        navbar.add_item("About", "#about")
        navbar.add_item("Contact", "#contact")
        DOM.add(navbar.element)

        @when(navbar.events.item_click)
        def handle_click(sender, item_id):
            print(f"Clicked: {item_id}")
    """

    def __init__(self, brand="", brand_href="#", background="#667eea",
                 color="white", height="60px", **kwargs):
        """
        Initialize a navbar.

        Args:
            brand: Brand name or logo text
            brand_href: Brand link URL
            background: Navbar background color
            color: Text color
            height: Navbar height
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="navbar", **kwargs)

        self._set_state(
            brand=brand,
            brand_href=brand_href,
            background=background,
            color=color,
            height=height,
            items=[]
        )

        self._create_event('item_click')
        self._create_event('brand_click')

        self._init_macro()

    def _create_elements(self):
        """Create the navbar element."""
        navbar_styles = {
            "display": "flex",
            "align_items": "center",
            "justify_content": "space-between",
            "padding": "0 24px",
            "background": self._get_state('background'),
            "color": self._get_state('color'),
            "height": self._get_state('height'),
            "box_shadow": "0 2px 4px rgba(0, 0, 0, 0.1)",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "position": "sticky",
            "top": "0",
            "z_index": "1000"
        }

        navbar = Div(style=navbar_styles)

        # Brand
        if self._get_state('brand'):
            brand_styles = {
                "font_size": "20px",
                "font_weight": "bold",
                "color": self._get_state('color'),
                "text_decoration": "none",
                "cursor": "pointer"
            }
            brand = A(
                self._get_state('brand'),
                href=self._get_state('brand_href'),
                style=brand_styles
            )
            navbar.add(brand)
            self._register_element('brand', brand)

            @when(brand.events.click)
            def on_brand_click(sender, *args):
                self.events.fire('brand_click')

        # Nav items container
        items_styles = {
            "display": "flex",
            "gap": "24px",
            "align_items": "center"
        }
        items_container = Div(style=items_styles)
        navbar.add(items_container)
        self._register_element('items_container', items_container)

        # Add existing items
        for item in self._get_state('items'):
            self._add_item_element(items_container, item)

        self._register_element('navbar', navbar)
        return navbar

    def _add_item_element(self, container, item):
        """Add a navigation item to the container."""
        item_styles = {
            "color": self._get_state('color'),
            "text_decoration": "none",
            "cursor": "pointer",
            "transition": "opacity 0.2s ease",
            "font_size": "14px"
        }

        item_elem = A(item['label'], href=item['href'], style=item_styles)

        @when(item_elem.events.click)
        def on_click(sender, *args):
            self.events.fire('item_click', item['id'])

        @when(item_elem.events.mouseenter)
        def on_hover(sender, *args):
            item_elem.style.opacity = "0.8"

        @when(item_elem.events.mouseleave)
        def on_leave(sender, *args):
            item_elem.style.opacity = "1"

        container.add(item_elem)

    def add_item(self, label, href="#", item_id=None):
        """Add a navigation item."""
        if item_id is None:
            item_id = label.lower().replace(' ', '_')

        item = {
            'label': label,
            'href': href,
            'id': item_id
        }

        items = self._get_state('items')
        items.append(item)
        self._set_state(items=items)

        items_container = self._get_element('items_container')
        if items_container:
            self._add_item_element(items_container, item)


class Breadcrumb(Macro):
    """
    A breadcrumb navigation component.

    Features:
    - Multiple breadcrumb items
    - Clickable navigation
    - Custom separator
    - Active item styling

    Usage:
        breadcrumb = Breadcrumb()
        breadcrumb.add_item("Home", "#home")
        breadcrumb.add_item("Products", "#products")
        breadcrumb.add_item("Item", "#item", active=True)
        DOM.add(breadcrumb.element)

        @when(breadcrumb.events.item_click)
        def handle_click(sender, item_id):
            print(f"Navigating to: {item_id}")
    """

    def __init__(self, separator="/", **kwargs):
        """
        Initialize a breadcrumb.

        Args:
            separator: Separator between items
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="breadcrumb", **kwargs)

        self._set_state(
            separator=separator,
            items=[]
        )

        self._create_event('item_click')

        self._init_macro()

    def _create_elements(self):
        """Create the breadcrumb element."""
        breadcrumb_styles = {
            "display": "flex",
            "align_items": "center",
            "gap": "8px",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "font_size": "14px",
            "color": "#6b7280"
        }

        breadcrumb = Div(style=breadcrumb_styles)
        self._register_element('breadcrumb', breadcrumb)

        # Add items
        items = self._get_state('items')
        for i, item in enumerate(items):
            # Add separator before all items except the first
            if i > 0:
                sep_styles = {
                    "color": "#9ca3af",
                    "user_select": "none"
                }
                sep = Span(self._get_state('separator'), style=sep_styles)
                breadcrumb.add(sep)

            # Add item
            self._add_item_element(breadcrumb, item)

        return breadcrumb

    def _add_item_element(self, container, item):
        """Add a breadcrumb item element."""
        is_active = item.get('active', False)

        item_styles = {
            "color": "#374151" if is_active else "#667eea",
            "text_decoration": "none" if is_active else "none",
            "cursor": "default" if is_active else "pointer",
            "font_weight": "500" if is_active else "normal"
        }

        if is_active:
            item_elem = Span(item['label'], style=item_styles)
        else:
            item_elem = A(item['label'], href=item['href'], style=item_styles)

            @when(item_elem.events.click)
            def on_click(sender, *args):
                self.events.fire('item_click', item['id'])

            @when(item_elem.events.mouseenter)
            def on_hover(sender, *args):
                item_elem.style.text_decoration = "underline"

            @when(item_elem.events.mouseleave)
            def on_leave(sender, *args):
                item_elem.style.text_decoration = "none"

        container.add(item_elem)

    def add_item(self, label, href="#", item_id=None, active=False):
        """Add a breadcrumb item."""
        if item_id is None:
            item_id = label.lower().replace(' ', '_')

        item = {
            'label': label,
            'href': href,
            'id': item_id,
            'active': active
        }

        items = self._get_state('items')
        items.append(item)
        self._set_state(items=items)

        breadcrumb = self._get_element('breadcrumb')
        if breadcrumb:
            # Rebuild breadcrumb
            breadcrumb.dom_element.innerHTML = ""

            all_items = self._get_state('items')
            for i, itm in enumerate(all_items):
                if i > 0:
                    sep_styles = {
                        "color": "#9ca3af",
                        "user_select": "none"
                    }
                    sep = Span(self._get_state('separator'), style=sep_styles)
                    breadcrumb.add(sep)

                self._add_item_element(breadcrumb, itm)


class SideNav(Macro):
    """
    A side navigation component.

    Features:
    - Vertical navigation menu
    - Collapsible groups
    - Active item highlighting
    - Icon support

    Usage:
        sidenav = SideNav(width="250px")
        sidenav.add_item("Dashboard", "#dashboard", icon="📊")
        sidenav.add_item("Settings", "#settings", icon="⚙")
        DOM.add(sidenav.element)

        @when(sidenav.events.item_click)
        def handle_click(sender, item_id):
            print(f"Navigate to: {item_id}")
    """

    def __init__(self, width="250px", background="#f9fafb",
                 active_color="#667eea", **kwargs):
        """
        Initialize a side navigation.

        Args:
            width: Side nav width
            background: Background color
            active_color: Active item color
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="sidenav", **kwargs)

        self._set_state(
            width=width,
            background=background,
            active_color=active_color,
            items=[],
            active_item=None
        )

        self._create_event('item_click')

        self._init_macro()

    def _create_elements(self):
        """Create the side navigation element."""
        sidenav_styles = {
            "width": self._get_state('width'),
            "background": self._get_state('background'),
            "padding": "20px 0",
            "display": "flex",
            "flex_direction": "column",
            "gap": "4px",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "height": "100vh",
            "position": "sticky",
            "top": "0",
            "overflow_y": "auto"
        }

        sidenav = Div(style=sidenav_styles)
        self._register_element('sidenav', sidenav)

        # Add items
        for item in self._get_state('items'):
            self._add_item_element(sidenav, item)

        return sidenav

    def _add_item_element(self, container, item):
        """Add a navigation item element."""
        is_active = item['id'] == self._get_state('active_item')

        item_styles = {
            "display": "flex",
            "align_items": "center",
            "gap": "12px",
            "padding": "12px 20px",
            "color": self._get_state('active_color') if is_active else "#374151",
            "background": f"{self._get_state('active_color')}15" if is_active else "transparent",
            "border_left": f"3px solid {self._get_state('active_color')}" if is_active else "3px solid transparent",
            "cursor": "pointer",
            "transition": "all 0.2s ease",
            "text_decoration": "none",
            "font_size": "14px",
            "font_weight": "500" if is_active else "normal"
        }

        item_elem = A(style=item_styles, href=item['href'])

        # Icon
        if item.get('icon'):
            icon = Span(item['icon'], style={"font_size": "18px"})
            item_elem.add(icon)

        # Label
        label = Span(item['label'])
        item_elem.add(label)

        @when(item_elem.events.click)
        def on_click(sender, *args):
            self.set_active(item['id'])
            self.events.fire('item_click', item['id'])

        @when(item_elem.events.mouseenter)
        def on_hover(sender, *args):
            if not is_active:
                item_elem.style.background = "#f3f4f6"

        @when(item_elem.events.mouseleave)
        def on_leave(sender, *args):
            if not is_active:
                item_elem.style.background = "transparent"

        container.add(item_elem)

    def add_item(self, label, href="#", item_id=None, icon=None):
        """Add a navigation item."""
        if item_id is None:
            item_id = label.lower().replace(' ', '_')

        item = {
            'label': label,
            'href': href,
            'id': item_id,
            'icon': icon
        }

        items = self._get_state('items')
        items.append(item)
        self._set_state(items=items)

        sidenav = self._get_element('sidenav')
        if sidenav:
            self._add_item_element(sidenav, item)

    def set_active(self, item_id):
        """Set the active navigation item."""
        self._set_state(active_item=item_id)

        # Rebuild the navigation
        sidenav = self._get_element('sidenav')
        if sidenav:
            sidenav.dom_element.innerHTML = ""
            for item in self._get_state('items'):
                self._add_item_element(sidenav, item)


class TabNav(Macro):
    """
    A tab navigation component with integrated content management.

    Features:
    - Multiple tabs with content
    - Active tab highlighting
    - Automatic content switching
    - Horizontal layout on desktop
    - Mobile-responsive hamburger menu
    - Click events

    Usage:
        tabs = TabNav()

        # Create content for each tab
        overview_content = Div("Overview content here")
        details_content = Div("Details content here")

        # Add tabs with content
        tabs.add_tab("Overview", "overview", content=overview_content, active=True)
        tabs.add_tab("Details", "details", content=details_content)

        DOM.add(tabs.element)

        @when(tabs.events.tab_change)
        def handle_change(sender, tab_id):
            print(f"Switched to: {tab_id}")
    """

    def __init__(self, content_spacing="30px", mobile_breakpoint="768px", **kwargs):
        """
        Initialize a tab navigation.

        Args:
            content_spacing: Spacing between tabs and content area
            mobile_breakpoint: Screen width below which mobile menu appears
            **kwargs: Additional arguments
        """
        super().__init__(macro_type="tabnav", **kwargs)

        self._set_state(
            tabs=[],
            active_tab=None,
            content_spacing=content_spacing,
            mobile_breakpoint=mobile_breakpoint,
            mobile_menu_open=False
        )

        self._create_event('tab_change')

        self._init_macro()

    def _create_elements(self):
        """Create the tab navigation element."""
        # Main container
        main_container = Div(style={"width": "100%", "position": "relative"})

        # Header container (holds both desktop tabs and mobile menu button)
        header_container = Div(style={
            "border_bottom": "2px solid #e5e7eb",
            "position": "relative"
        })

        # Hamburger menu button (visible on mobile only)
        hamburger_styles = {
            "display": "none",  # Hidden on desktop
            "flex_direction": "column",
            "gap": "4px",
            "padding": "12px",
            "cursor": "pointer",
            "background": "transparent",
            "border": "none",
            "user_select": "none"
        }
        hamburger_btn = Div(style=hamburger_styles)

        # Three lines of hamburger icon
        for _ in range(3):
            line = Div(style={
                "width": "24px",
                "height": "3px",
                "background": "#374151",
                "border_radius": "2px",
                "transition": "all 0.3s ease"
            })
            hamburger_btn.add(line)

        self._register_element('hamburger', hamburger_btn)
        header_container.add(hamburger_btn)

        # Wire hamburger click event
        @when(hamburger_btn.events.click)
        def toggle_mobile_menu(sender, *args):
            is_open = not self._get_state('mobile_menu_open')
            self._set_state(mobile_menu_open=is_open)
            mobile_menu = self._get_element('mobile_menu')
            if mobile_menu:
                if is_open:
                    mobile_menu.style.display = "flex"
                    # Add click outside listener when menu opens
                    Events.add_listener('click', self._handle_click_outside, owner=self)
                else:
                    mobile_menu.style.display = "none"
                    # Remove click outside listener when menu closes
                    Events.remove_listener('click', self._handle_click_outside)

        # Desktop tabs container
        tabs_styles = {
            "display": "flex",
            "gap": "0",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        }
        tabs_container = Div(style=tabs_styles)
        self._register_element('tabs_container', tabs_container)

        # Add tab buttons
        for tab in self._get_state('tabs'):
            self._add_tab_element(tabs_container, tab)

        header_container.add(tabs_container)

        # Mobile dropdown menu
        mobile_menu_styles = {
            "display": "none",
            "flex_direction": "column",
            "position": "absolute",
            "top": "100%",
            "left": "0",
            "right": "0",
            "background": "white",
            "border": "1px solid #e5e7eb",
            "border_top": "none",
            "box_shadow": "0 4px 6px rgba(0, 0, 0, 0.1)",
            "z_index": "1000"
        }
        mobile_menu = Div(style=mobile_menu_styles)
        self._register_element('mobile_menu', mobile_menu)

        # Add mobile menu items
        for tab in self._get_state('tabs'):
            self._add_mobile_tab_element(mobile_menu, tab)

        header_container.add(mobile_menu)
        main_container.add(header_container)
        self._register_element('header_container', header_container)

        # Generate unique IDs for CSS targeting
        unique_id = str(uuid.uuid4())[:8]
        tabs_container_id = f"tabnav-tabs-{unique_id}"
        hamburger_id = f"tabnav-hamburger-{unique_id}"
        mobile_menu_id = f"tabnav-mobile-{unique_id}"

        # Set id attributes on DOM elements
        tabs_container.set_attribute('id', tabs_container_id)
        hamburger_btn.set_attribute('id', hamburger_id)
        mobile_menu.set_attribute('id', mobile_menu_id)

        # Add responsive CSS via style tag
        from js import document
        style_id = f"tabnav-responsive-{unique_id}"
        if not document.getElementById(style_id):
            style = document.createElement('style')
            style.id = style_id
            style.textContent = f"""
                @media (max-width: 768px) {{
                    /* Hide desktop tabs on mobile */
                    #{tabs_container_id} {{
                        display: none !important;
                    }}
                    /* Show hamburger on mobile */
                    #{hamburger_id} {{
                        display: flex !important;
                    }}
                }}
                @media (min-width: 769px) {{
                    /* Hide mobile menu on desktop */
                    #{mobile_menu_id} {{
                        display: none !important;
                    }}
                }}
            """
            document.head.appendChild(style)

        # Content area
        content_area_styles = {
            "margin_top": self._get_state('content_spacing')
        }
        content_area = Div(style=content_area_styles)
        self._register_element('content_area', content_area)

        # Add initial content
        active_tab_id = self._get_state('active_tab')
        if active_tab_id:
            for tab in self._get_state('tabs'):
                if tab['id'] == active_tab_id and tab.get('content'):
                    content_area.add(tab['content'])
                    break

        main_container.add(content_area)
        self._register_element('container', main_container)

        return main_container

    def _add_tab_element(self, container, tab):
        """Add a tab element."""
        is_active = tab['id'] == self._get_state('active_tab')

        tab_styles = {
            "padding": "12px 24px",
            "color": "#667eea" if is_active else "#6b7280",
            "border_bottom": "2px solid #667eea" if is_active else "2px solid transparent",
            "cursor": "pointer",
            "transition": "all 0.2s ease",
            "font_size": "14px",
            "font_weight": "500" if is_active else "normal",
            "margin_bottom": "-2px",
            "user_select": "none"
        }

        tab_elem = Div(tab['label'], style=tab_styles)

        @when(tab_elem.events.click)
        def on_click(sender, *args):
            self.set_active(tab['id'])
            self.events.fire('tab_change', tab['id'])

        @when(tab_elem.events.mouseenter)
        def on_hover(sender, *args):
            if not is_active:
                tab_elem.style.color = "#374151"

        @when(tab_elem.events.mouseleave)
        def on_leave(sender, *args):
            if not is_active:
                tab_elem.style.color = "#6b7280"

        container.add(tab_elem)

    def _add_mobile_tab_element(self, container, tab):
        """Add a mobile menu tab element."""
        is_active = tab['id'] == self._get_state('active_tab')

        mobile_tab_styles = {
            "padding": "16px 20px",
            "color": "#667eea" if is_active else "#374151",
            "background": "#f9fafb" if is_active else "transparent",
            "cursor": "pointer",
            "transition": "all 0.2s ease",
            "font_size": "14px",
            "font_weight": "500" if is_active else "normal",
            "border_left": f"3px solid #667eea" if is_active else "3px solid transparent",
            "user_select": "none",
            "font_family": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        }

        mobile_tab_elem = Div(tab['label'], style=mobile_tab_styles)

        @when(mobile_tab_elem.events.click)
        def on_mobile_click(sender, *args):
            # Close mobile menu
            self._set_state(mobile_menu_open=False)
            mobile_menu = self._get_element('mobile_menu')
            if mobile_menu:
                mobile_menu.style.display = "none"

            # Remove click outside listener
            Events.remove_listener('click', self._handle_click_outside)

            # Switch tab
            self.set_active(tab['id'])
            self.events.fire('tab_change', tab['id'])

        @when(mobile_tab_elem.events.mouseenter)
        def on_mobile_hover(sender, *args):
            if not is_active:
                mobile_tab_elem.style.background = "#f3f4f6"

        @when(mobile_tab_elem.events.mouseleave)
        def on_mobile_leave(sender, *args):
            if not is_active:
                mobile_tab_elem.style.background = "transparent"

        container.add(mobile_tab_elem)

    def add_tab(self, label, tab_id=None, content=None, active=False):
        """
        Add a tab with content.

        Args:
            label: Tab label text
            tab_id: Unique tab identifier (auto-generated from label if not provided)
            content: Content element to display when tab is active
            active: Whether this tab should be active initially
        """
        if tab_id is None:
            tab_id = label.lower().replace(' ', '_')

        tab = {
            'label': label,
            'id': tab_id,
            'content': content
        }

        tabs = self._get_state('tabs')
        tabs.append(tab)
        self._set_state(tabs=tabs)

        if active or self._get_state('active_tab') is None:
            self._set_state(active_tab=tab_id)
            # Show this tab's content
            content_area = self._get_element('content_area')
            if content_area and content:
                content_area.clear()
                content_area.add(content)

        tabs_container = self._get_element('tabs_container')
        if tabs_container:
            # Rebuild tabs
            tabs_container.clear()
            for t in self._get_state('tabs'):
                self._add_tab_element(tabs_container, t)

        # Also rebuild mobile menu
        mobile_menu = self._get_element('mobile_menu')
        if mobile_menu:
            mobile_menu.clear()
            for t in self._get_state('tabs'):
                self._add_mobile_tab_element(mobile_menu, t)

    def set_active(self, tab_id):
        """
        Set the active tab and switch content.

        Args:
            tab_id: The ID of the tab to activate
        """
        old_tab_id = self._get_state('active_tab')
        if old_tab_id == tab_id:
            return  # Already active

        self._set_state(active_tab=tab_id)

        # Rebuild tabs to update styling
        tabs_container = self._get_element('tabs_container')
        if tabs_container:
            tabs_container.clear()
            for tab in self._get_state('tabs'):
                self._add_tab_element(tabs_container, tab)

        # Also rebuild mobile menu
        mobile_menu = self._get_element('mobile_menu')
        if mobile_menu:
            mobile_menu.clear()
            for tab in self._get_state('tabs'):
                self._add_mobile_tab_element(mobile_menu, tab)

        # Switch content
        content_area = self._get_element('content_area')
        if content_area:
            # Clear current content
            content_area.clear()

            # Find and add new content
            for tab in self._get_state('tabs'):
                if tab['id'] == tab_id and tab.get('content'):
                    content_area.add(tab['content'])
                    break

    def _handle_click_outside(self, event):
        """Handle clicks outside the header to close the mobile menu."""
        # Only close if mobile menu is open
        if not self._get_state('mobile_menu_open'):
            return

        # Get the header container element (not the main container)
        header_container = self._get_element('header_container')
        if not header_container:
            return

        # Check if click target is outside the header container
        # This will close the menu when clicking on content area or outside the component
        if not header_container._dom_element.contains(event.target):
            # Close the mobile menu
            self._set_state(mobile_menu_open=False)
            mobile_menu = self._get_element('mobile_menu')
            if mobile_menu:
                mobile_menu.style.display = "none"
            # Remove the click outside listener
            Events.remove_listener('click', self._handle_click_outside)