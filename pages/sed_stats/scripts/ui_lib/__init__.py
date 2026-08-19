"""
UI library for Antioch apps.

Components:
    TabView, TabItem    - tabs whose panels stay mounted (display-toggled)
    Wizard, WizardPanel - stepped options panel that generates on demand
    CheckboxGroup       - multi-select list with select-all/none
    labeled             - label + control + hint form row
    Ribbon              - horizontal toolbar of tool buttons
    LoadingOverlay      - full-screen spinner for work that blocks the UI thread
"""
from .tabs import TabView, TabItem
from .wizard import Wizard, WizardPanel
from .fields import CheckboxGroup, labeled
from .ribbon import Ribbon
from .overlay import LoadingOverlay, next_frame

__all__ = [
    'TabView',
    'TabItem',
    'Wizard',
    'WizardPanel',
    'CheckboxGroup',
    'labeled',
    'Ribbon',
    'LoadingOverlay',
    'next_frame',
]

__version__ = '0.2.0'
