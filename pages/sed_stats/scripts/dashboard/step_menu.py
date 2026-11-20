"""
What a right-click on the canvas offers.

Kept apart from the widgets so what each menu says, and when an item is greyed, can be tested
without a browser. An item is (key, label, enabled); None is a divider.
"""


def node_menu(has_output, has_charts, can_save, multiple_charts=False, can_write=False,
              can_view_map=False, has_message=False):
    """
    The menu of a step.

    Args:
        has_output: the step has run and made something to show
        has_charts: that output includes plots, so there is something to download
        can_save: a Google Drive is connected to save to
        multiple_charts: the download is a zip of plots, not one SVG
        can_write: the step has run and made a table, which can replace the spreadsheet
        can_view_map: the step holds a watershed, which the Maps tab can show
        has_message: the step failed or was skipped, and says why
    """
    items = [
        ("edit", "Edit…", True),
        ("run", "Run this step", True),
        None,
        ("output", "Show output", has_output),
        ("download", "Download as zip of SVGs" if multiple_charts else "Download SVG",
         has_output and has_charts),
    ]
    if has_message:
        items.insert(4, ("message", "Show the whole message", True))
    if can_save:
        items.append(("save", "Save to Drive", has_output and has_charts))
    if can_view_map:
        items += [None, ("view_map", "View on the map", True)]
    if can_write:
        items += [None, ("to_sheet", "Replace the spreadsheet with this table…", True)]
    items += [None, ("duplicate", "Duplicate", True), ("delete", "Delete", True)]
    return items


def selection_menu(count):
    """What a right-click offers on several selected blocks at once."""
    return [("run_selected", f"Run {count} blocks", True),
            ("save_tool", f"Save {count} blocks as a tool…", True),
            None,
            ("delete_selected", f"Delete {count} blocks…", True)]


def data_menu():
    """The spreadsheet block has one thing to offer: going to the spreadsheet."""
    return [("view_sheet", "View Spreadsheet", True)]


def edge_menu():
    return [("disconnect", "Disconnect", True)]


def canvas_menu(has_steps):
    return [
        ("run_all", "Run workflow", has_steps),
        ("tidy", "Tidy up the layout", has_steps),
        ("zoom_reset", "Zoom to 100%", True),
        None,
        ("clear", "Remove every step…", has_steps),
    ]
