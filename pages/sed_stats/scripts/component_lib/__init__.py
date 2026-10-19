"""
Component Library for Antioch Framework

A comprehensive collection of pre-built, styled UI components.

Categories:
- Buttons: ButtonPrimary, ButtonSuccess, ButtonWarning, ButtonDanger, ButtonInfo, ButtonSecondary
- Inputs: TextInput, TextArea, Checkbox, Radio, Select
- Layout: Grid, Flex, Stack, Divider, Container, Spacer
- Typography: Heading, Text, Link, Badge, Code
- Feedback: Alert, Spinner, ProgressBar, Toast
- Navigation: NavBar, Breadcrumb, SideNav, TabNav
- Display: Card, Panel, ListGroup, Avatar, AvatarGroup

Usage:
    from component_lib import ButtonPrimary, TextInput, Card

    button = ButtonPrimary("Click Me")
    input_field = TextInput(label="Email", placeholder="Enter email")
    card = Card(title="Welcome")
"""

# Button components
from .button import (
    ButtonPrimary,
    ButtonSuccess,
    ButtonWarning,
    ButtonDanger,
    ButtonInfo,
    ButtonSecondary
)

# Input components
from .input import (
    TextInput,
    TextArea,
    Checkbox,
    Radio,
    Select,
    Switch
)

# Layout components
from .layout import (
    Grid,
    Flex,
    Stack,
    Divider,
    Container,
    Spacer
)

# Typography components
from .typography import (
    Heading,
    Text,
    Link,
    Badge,
    Code
)

# Feedback components
from .feedback import (
    Alert,
    Spinner,
    ProgressBar,
    Toast
)

# Navigation components
from .navigation import (
    NavBar,
    Breadcrumb,
    SideNav,
    TabNav
)

# Display components
from .display import (
    Card,
    Panel,
    ListGroup,
    Avatar,
    AvatarGroup
)

# Export all components
__all__ = [
    # Buttons
    'ButtonPrimary',
    'ButtonSuccess',
    'ButtonWarning',
    'ButtonDanger',
    'ButtonInfo',
    'ButtonSecondary',

    # Inputs
    'TextInput',
    'TextArea',
    'Checkbox',
    'Radio',
    'Select',
    'Switch',

    # Layout
    'Grid',
    'Flex',
    'Stack',
    'Divider',
    'Container',
    'Spacer',

    # Typography
    'Heading',
    'Text',
    'Link',
    'Badge',
    'Code',

    # Feedback
    'Alert',
    'Spinner',
    'ProgressBar',
    'Toast',

    # Navigation
    'NavBar',
    'Breadcrumb',
    'SideNav',
    'TabNav',

    # Display
    'Card',
    'Panel',
    'ListGroup',
    'Avatar',
    'AvatarGroup',
]