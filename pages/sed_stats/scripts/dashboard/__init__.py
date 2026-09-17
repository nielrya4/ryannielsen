"""
Sed/Stats dashboard.

Modules:
    config       - the choices the wizards offer, and shared constants
    example_data - the built-in sample dataset
    dataset      - spreadsheet rows -> per-sample series
    plots        - chart construction shared by the builders
    distributions / matrices / mds_plot - one output builder each
    gallery      - the list of generated outputs
    tools        - a wizard-in-a-modal per toolbar entry
    drive        - Google sign-in, and Drive open/save
    shell        - the page frame
    errors       - rendering exceptions into the page
"""
from .shell import AppShell
from .tools import Tool, build_tools
from .gallery import Gallery
from .errors import error_box

__all__ = [
    'AppShell',
    'Tool',
    'build_tools',
    'Gallery',
    'error_box',
]

__version__ = '0.1.0'
