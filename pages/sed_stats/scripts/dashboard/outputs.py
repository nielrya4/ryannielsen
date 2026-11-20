"""Assembling a step's output: tabs for a batch, and lining batches up."""
from antioch.event import when

from ui_lib import TabItem, TabView
from workflow_lib import NodeProblem


def tabbed(charts, titles, contents):
    """
    One body for a batch of results: the result itself when there is one, else a
    tab view with a tab each (plots sized while their tab was hidden are re-fit
    when it is shown).

    Returns:
        (body, tabview) — tabview is None for a single result
    """
    if len(contents) == 1:
        return contents[0], None
    tabview = TabView(tabs=[TabItem(title, content)
                            for title, content in zip(titles, contents)])

    @when(tabview.events.change)
    def on_tab(sender, *args):
        for _, chart in charts:
            chart.resize()

    return tabview.element, tabview


def aligned(batches):
    """
    Pair up the items of several batches, index by index.

    A graph with several inputs draws their i-th items together. A batch of one
    is repeated against a longer one, so a single hull can sit over every
    dimension's scatter; otherwise the batches must be the same length.

    Returns:
        [(item_from_batch_0, item_from_batch_1, ...), ...]
    """
    if not batches:
        return []
    size = max(len(batch) for batch in batches)
    for batch in batches:
        if len(batch) not in (1, size):
            raise NodeProblem(
                f"The inputs have {sorted({len(b) for b in batches})} items; "
                "they can only be drawn together when they match or one has a "
                "single item.")
    if any(len(batch) == 0 for batch in batches):
        return []
    return [tuple(batch[i if len(batch) > 1 else 0] for batch in batches)
            for i in range(size)]
