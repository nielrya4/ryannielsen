"""
Sed/Stats dashboard.

Modules:
    config       - the choices the wizards offer, and shared constants
    example_data - the built-in sample dataset
    dataset      - spreadsheet rows -> per-sample series
    plots        - chart construction shared by the builders
    distributions / matrices / mds_plot - one output builder each
    nodes        - the typed blocks workflows are built from
    toolboxes    - tools (pre-wired chains of blocks) grouped for the menus
    workflow_panel / workflow_canvas - the canvas, where every tool and block is added and
                   every step's output is kept
    output_viewer - the window a block's output expands in
    tool_runner  - running a tool's chain once, outside a workflow
    drive        - Google sign-in, and Drive open/save
    shell        - the page frame
"""
from .shell import AppShell

__all__ = [
    'AppShell',
]

__version__ = '0.1.0'
