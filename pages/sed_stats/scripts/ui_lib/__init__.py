"""
UI library for Antioch apps.

Components:
    TabView, TabItem    - tabs whose panels stay mounted (display-toggled)
    Wizard, WizardPanel - stepped options panel that generates on demand
    CheckboxGroup       - multi-select list with select-all/none
    set_select_options  - repopulate a Select, keeping the current choice
    labeled             - label + control + hint form row
    Toolbar             - menu bar with nested dropdowns; hamburger on mobile
    Ribbon              - horizontal strip of tool buttons (superseded by Toolbar)
    LoadingOverlay      - full-screen spinner for work that blocks the UI thread
"""
from .tabs import TabView, TabItem
from .wizard import Wizard, WizardPanel
from .fields import CheckboxGroup, labeled, set_select_options
from .ribbon import Ribbon
from .toolbar import Toolbar
from .overlay import LoadingOverlay, next_frame

__all__ = [
    'TabView',
    'TabItem',
    'Wizard',
    'WizardPanel',
    'CheckboxGroup',
    'labeled',
    'set_select_options',
    'Ribbon',
    'Toolbar',
    'LoadingOverlay',
    'next_frame',
]

__version__ = '0.2.0'
