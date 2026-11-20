"""Tabulator-backed spreadsheet macro."""
import asyncio
import json

import js

from antioch.elements import Div
from antioch.macros.js_library import JSLibraryMacro

from . import edits

# What the page has to do for the sheet runs in JS: reading the selection, keyboard handling and
# the menus. Tabulator's row, cell and column components must never reach Python: Pyodide probes an
# incoming object for `next`, `get`, `has` and friends to decide how to wrap it, and Tabulator's
# components warn loudly on every unknown property. So this hands back only strings and numbers
# (positions and field names, as JSON), and Python makes every change to the data.
_SHEET_ID = "spreadsheet-lib-sheet-js"
_SHEET_NAME = "__sedStatsSheet"
_SHEET_JS = """
window.__sedStatsSheet = {
  // Where a row is in the data (1-based, in the order getData() returns). Not getPosition():
  // that is the row's place on screen, which differs as soon as the table is sorted, and acting
  // on the wrong row would lose data.
  rowIndex: function (table, row) {
    var all = table.rowManager && table.rowManager.rows;
    var self = row._getSelf ? row._getSelf() : null;
    var at = all && self ? all.indexOf(self) : -1;
    return at >= 0 ? at + 1 : row.getPosition();
  },
  // Positions (1-based, in the data's order) of every row a selection touches.
  positions: function (table) {
    var found = {}, sheet = window.__sedStatsSheet;
    (table.getRanges() || []).forEach(function (range) {
      (range.getRows() || []).forEach(function (row) { found[sheet.rowIndex(table, row)] = true; });
    });
    return JSON.stringify(Object.keys(found).map(Number).sort(function (a, b) { return a - b; }));
  },
  // Fields of every column a selection touches.
  fields: function (table) {
    var found = [];
    (table.getRanges() || []).forEach(function (range) {
      (range.getColumns() || []).forEach(function (column) {
        var field = column.getField();
        if (field && found.indexOf(field) < 0) { found.push(field); }
      });
    });
    return JSON.stringify(found);
  },
  // Every selected block: its rows (0-based, in the data's order) and its column names.
  selection: function (table) {
    var sheet = window.__sedStatsSheet, out = [];
    (table.getRanges() || []).forEach(function (range) {
      var rows = (range.getRows() || []).map(function (row) { return sheet.rowIndex(table, row) - 1; });
      var fields = (range.getColumns() || []).map(function (c) { return c.getField(); }).filter(Boolean);
      if (rows.length && fields.length) { out.push({ rows: rows, fields: fields }); }
    });
    return out;
  },
  // The values of the first selected block, a list of rows, for the clipboard.
  lines: function (table) {
    var ranges = table.getRanges() || [];
    if (!ranges.length) { return []; }
    var fields = (ranges[0].getColumns() || []).map(function (c) { return c.getField(); }).filter(Boolean);
    return (ranges[0].getRows() || []).map(function (row) {
      var data = row.getData();
      return fields.map(function (f) { return data[f] === undefined ? '' : data[f]; });
    });
  },
  // Drop every selection (the table has addRange but no clear, so each is removed in turn).
  clearRanges: function (table) {
    (table.getRanges() || []).slice().forEach(function (range) { range.remove(); });
  },
  // Select every cell.
  selectAll: function (table) {
    var rows = table.getRows('active');
    var fields = table.getColumns().map(function (c) { return c.getField(); }).filter(Boolean);
    if (!rows.length || !fields.length) { return; }
    window.__sedStatsSheet.clearRanges(table);
    // Cells, not rows (addRange takes cells); a row off-screen still has them.
    table.addRange(rows[0].getCell(fields[0]), rows[rows.length - 1].getCell(fields[fields.length - 1]));
  },
  // Put text on the clipboard: the modern call where there is one, else a hidden field and a copy
  // command, either of which is allowed from a key press.
  write: function (text) {
    var fallback = function () {
      var held = document.activeElement;
      var box = document.createElement('textarea');
      box.value = text;
      box.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';
      document.body.appendChild(box);
      box.select();
      try { document.execCommand('copy'); } catch (e) { /* nothing more can be done */ }
      document.body.removeChild(box);
      if (held && held.focus) { held.focus(); }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(fallback);
    } else { fallback(); }
  },
  // The first selection: its top-left cell, and how many rows and columns it covers.
  active: function (table) {
    var ranges = table.getRanges() || [];
    if (!ranges.length) { return null; }
    var grid = ranges[0].getStructuredCells ? ranges[0].getStructuredCells() : ranges[0].getCells();
    if (!grid.length || !grid[0].length) { return null; }
    var cell = grid[0][0];
    return { cell: cell, info: { row: window.__sedStatsSheet.rowIndex(table, cell.getRow()), field: cell.getField(),
                                 rows: grid.length, cols: grid[0].length } };
  },
  // Show new data, keeping the scroll position, and select a block of cells if asked.
  replace: function (table, columns, rows, select) {
    var holder = table.rowManager && table.rowManager.getElement ? table.rowManager.getElement() : null;
    var top = holder ? holder.scrollTop : 0;
    if (columns) { table.setColumns(columns); }
    var done = table.setData(rows);
    var finish = function () {
      if (holder) { holder.scrollTop = top; }
      if (!select || !select.field) { return; }
      try {
        var all = table.getRows();
        var fields = table.getColumns().map(function (c) { return c.getField(); }).filter(Boolean);
        var first = all[select.row - 1];
        var last = all[select.row - 1 + Math.max(select.rows, 1) - 1] || first;
        var at = fields.indexOf(select.field);
        var endField = fields[at + Math.max(select.cols, 1) - 1] || select.field;
        if (first && at >= 0) {
          window.__sedStatsSheet.clearRanges(table);
          table.addRange(first.getCell(select.field), last.getCell(endField));
        }
      } catch (e) { /* a selection that cannot be restored is not worth an error */ }
    };
    if (done && done.then) { done.then(finish); } else { finish(); }
  },
  // Menus and the header double-click, which Tabulator takes as options.
  options: function (emit) {
    var send = function (kind, data) { emit(kind, JSON.stringify(data || {})); };
    var here = function (row) { return window.__sedStatsSheet.rowIndex(row.getTable(), row); };
    var rowsOf = function (row) {
      var table = row.getTable(), here = window.__sedStatsSheet.rowIndex(table, row);
      var chosen = JSON.parse(window.__sedStatsSheet.positions(table));
      return chosen.indexOf(here) >= 0 ? chosen : [here];
    };
    var columnsOf = function (column) {
      var table = column.getTable(), here = column.getField();
      var chosen = JSON.parse(window.__sedStatsSheet.fields(table));
      return chosen.indexOf(here) >= 0 ? chosen : [here];
    };
    return {
      columnDefaults: {
        headerDblClick: function (e, column) { send('rename', { field: column.getField() }); },
        headerContextMenu: [
          { label: 'Rename column…', action: function (e, column) { send('rename', { field: column.getField() }); } },
          { label: 'Insert column left…', action: function (e, column) { send('add_column', { field: column.getField(), side: 'left' }); } },
          { label: 'Insert column right…', action: function (e, column) { send('add_column', { field: column.getField(), side: 'right' }); } },
          { separator: true },
          { label: 'Delete column(s)', action: function (e, column) { send('delete_columns', { fields: columnsOf(column) }); } }
        ]
      },
      rowContextMenu: [
        { label: 'Insert row above', action: function (e, row) { send('insert_rows', { position: here(row), below: false, count: 1 }); } },
        { label: 'Insert row below', action: function (e, row) { send('insert_rows', { position: here(row), below: true, count: 1 }); } },
        { label: 'Duplicate row(s)', action: function (e, row) { send('duplicate_rows', { positions: rowsOf(row) }); } },
        { separator: true },
        { label: 'Delete row(s)', action: function (e, row) { send('delete_rows', { positions: rowsOf(row) }); } }
      ]
    };
  },
  // Keyboard and clipboard behaviour a spreadsheet has and Tabulator's range selection lacks:
  // typing on a selected cell replaces its contents, Ctrl+Z / Ctrl+Y undo and redo, and paste
  // is handled here so that a block bigger than the table grows it instead of being cut off.
  install: function (table, holder, emit) {
    var sheet = window.__sedStatsSheet;
    var inside = false;
    var typing = function () {
      var a = document.activeElement;
      return !!a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT' || a.isContentEditable);
    };
    document.addEventListener('mousedown', function (e) { inside = holder.contains(e.target); }, true);
    holder.addEventListener('keydown', function (e) {
      if (typing()) { return; }
      var key = e.key, mod = e.ctrlKey || e.metaKey;
      if (mod && !e.altKey && (key === 'z' || key === 'Z')) {
        e.preventDefault(); e.stopPropagation(); emit(e.shiftKey ? 'redo' : 'undo', '{}'); return;
      }
      if (mod && !e.altKey && (key === 'y' || key === 'Y')) {
        e.preventDefault(); e.stopPropagation(); emit('redo', '{}'); return;
      }
      var selected = (table.getRanges() || []).length > 0;
      if (mod && !e.altKey && (key === 'a' || key === 'A')) {
        e.preventDefault(); e.stopPropagation(); sheet.selectAll(table); return;
      }
      if (selected && !mod && !e.altKey && (key === 'Delete' || key === 'Backspace')) {
        e.preventDefault(); e.stopPropagation();
        emit('clear', JSON.stringify({ ranges: sheet.selection(table) })); return;
      }
      if (selected && mod && !e.altKey && (key === 'c' || key === 'C' || key === 'x' || key === 'X')) {
        e.preventDefault(); e.stopPropagation();
        sheet.write(emit('format', JSON.stringify({ lines: sheet.lines(table) })));
        if (key === 'x' || key === 'X') { emit('clear', JSON.stringify({ ranges: sheet.selection(table), cut: true })); }
        return;
      }
      if (!mod && !e.altKey && key.length === 1) {
        var active = sheet.active(table);
        if (!active) { return; }
        e.preventDefault(); e.stopPropagation();
        active.cell.edit(true);
        var input = active.cell.getElement().querySelector('input');
        if (input) { input.value = key; input.setSelectionRange(key.length, key.length); }
      }
    }, true);
    // Copy and cut chosen from a menu rather than the keyboard.
    ['copy', 'cut'].forEach(function (name) {
      window.addEventListener(name, function (e) {
        if (!inside && !holder.contains(document.activeElement)) { return; }
        if (typing() || !(table.getRanges() || []).length || !e.clipboardData) { return; }
        e.preventDefault(); e.stopImmediatePropagation();
        e.clipboardData.setData('text/plain', emit('format', JSON.stringify({ lines: sheet.lines(table) })));
        if (name === 'cut') { emit('clear', JSON.stringify({ ranges: sheet.selection(table), cut: true })); }
      }, true);
    });
    window.addEventListener('paste', function (e) {
      if (!inside && !holder.contains(document.activeElement)) { return; }
      if (typing()) { return; }
      var data = e.clipboardData;
      var text = data ? data.getData('text/plain') : null;
      if (text === null || text === undefined) { return; }
      e.preventDefault(); e.stopImmediatePropagation();
      var active = sheet.active(table);
      emit('paste', JSON.stringify(Object.assign({ text: text }, active ? active.info : {})));
    }, true);
  }
};
"""


def _ensure_sheet_js():
    # Not `is None`: Pyodide represents JS null as a `jsnull` sentinel, which
    # is not Python None, so `is None` is always False and the script would
    # never be injected. Truthiness is correct for both null and a real node.
    if not js.document.getElementById(_SHEET_ID):
        script = js.document.createElement("script")
        script.id = _SHEET_ID
        script.textContent = _SHEET_JS
        js.document.head.appendChild(script)

    if not hasattr(js.window, _SHEET_NAME):
        raise RuntimeError(
            "the spreadsheet helper script did not run — "
            "check the browser console for a script error")


def _sheet_js():
    """
    The shim, fetched by name.

    Not `js.window.__sedStatsSheet`: inside a class body Python mangles any
    leading-double-underscore attribute, so that expression silently becomes
    `js.window._TabulatorSheet__sedStatsSheet`. getattr sidesteps the rewrite.
    """
    return getattr(js.window, _SHEET_NAME)


class TabulatorSheet(JSLibraryMacro):
    """
    Editable spreadsheet backed by the Tabulator JS library.

    Everything a spreadsheet lets you do to its cells is here: type to replace a cell, double-click
    or Enter to edit, Delete to clear, arrow keys and Tab to move, paste that grows the sheet,
    insert, duplicate and delete rows and columns, rename a column, undo and redo. Every change
    goes through `edits` and is kept so it can be undone.

    Usage:
        sheet = TabulatorSheet(data=[{"a": 1, "b": 2}], height="400px")
        DOM.add(sheet.element)

        @when(sheet.events.data_change)
        def on_change(sender, data):
            ...

    Two hooks the page sets: `prompt`, `async (title, label, value) -> text or None`, asks for a
    column's name; `on_message`, `(text)`, hears what an edit did or why it could not.
    """

    UNDO_LIMIT = 40

    def __init__(self, data=None, columns=None, height="400px", options=None,
                 editable=True, sortable=True, **kwargs):
        """
        Args:
            data: List of row dicts
            columns: Tabulator column definitions; if None, columns are
                     auto-generated from the data (and regenerate on set_data)
            height: CSS height of the table; falsy sizes to content
            options: Extra Tabulator options merged over the defaults
            editable: Whether auto-generated columns accept typing
            sortable: Whether auto-generated columns sort on their header
        """
        super().__init__(macro_type="tabulator_sheet", **kwargs)

        self._set_state(
            data=data or [],
            columns=columns,
            height=height,
            options=options or {},
            editable=editable,
            sortable=sortable,
        )

        self._create_event('data_change')

        # Tabulator's constructor returns before the table exists: it builds
        # asynchronously and announces itself with `tableBuilt`. Anything that
        # touches the rendered table has to wait for that, so a redraw asked
        # for too early is remembered rather than thrown at a half-built table.
        self._built = False
        self._pending_redraw = False

        # The column order is kept apart from the rows, so a sheet with no rows still has columns
        # and a column with nothing in it is not lost. Rows and order are never changed in place:
        # each edit makes new ones, so a snapshot for undo is just a reference.
        self._order = edits.columns_of(
            data or [], [c["field"] for c in (columns or []) if "field" in c])
        self._current = (data or [], list(self._order))
        self._undo = []
        self._redo = []
        self.prompt = None
        self.on_message = None

        self._init_macro()

    def _get_library_dependencies(self):
        return {
            'scripts': ['antioch/lib/vendor/tabulator.min.js'],
            'stylesheets': ['antioch/lib/vendor/tabulator.min.css'],
        }

    def _get_library_global_name(self):
        return 'Tabulator'

    def _create_elements(self):
        container = self._register_element(
            'container', self._create_container({"width": "100%"})
        )
        holder = self._register_element('holder', Div())
        holder.set_attribute("id", f"tabulator_{self._id}")
        container.add(holder)
        return container

    def _column_definitions(self):
        columns = self._get_state('columns')
        if columns:
            return columns
        column = {'headerSort': self._get_state('sortable'), 'minWidth': 110}
        if self._get_state('editable'):
            column['editor'] = 'input'
            # Open with the existing value selected, so typing replaces it.
            column['editorParams'] = {'selectContents': True}
        return [{'title': field, 'field': field, **column}
                for field in edits.columns_of(self._get_state('data'), self._order)]

    def _build_options(self):
        options = {
            'data': self._get_state('data'),
            'layout': 'fitColumns',
            'columns': self._column_definitions(),
            # A row-number gutter, as a spreadsheet has. With row selection on,
            # Tabulator's range module otherwise claims the first visible
            # column as its row header — skipping it in every range and
            # dropping it from the copy. Its own column keeps the first data
            # column being data.
            'rowHeader': {
                'formatter': 'rownum',
                'hozAlign': 'center',
                'headerSort': False,
                'resizable': False,
                'frozen': True,
                'width': 44,
            },
            'nestedFieldSeparator': False,
            'selectableRange': True,
            'selectableRangeColumns': True,
            'selectableRangeRows': True,
            'selectableRangeClearCells': self._get_state('editable'),
            # An emptied cell is "", as a cell that was never filled is.
            'selectableRangeClearCellsValue': '',
            'clipboard': True,
            'clipboardCopyRowRange': 'range',
            # Cells as they are, so what is copied can be pasted straight back; a header row
            # would land in the data. (Pasting is handled by the shim, which can grow the sheet.)
            'clipboardCopyConfig': {'columnHeaders': False, 'rowHeaders': False},
            # Single click selects, so editing needs the second one — the
            # spreadsheet convention, and the only way both gestures fit. Typing on a
            # selected cell also starts an edit (see the shim).
            'editTriggerEvent': 'dblclick',
            'editorEmptyValue': '',
            # Tabulator warns that a sortable header and column range selection
            # fight over the same click; confining sorting to the icon is the
            # resolution it recommends.
            'headerSortClickElement': 'icon',
        }
        height = self._get_state('height')
        if height:
            options['height'] = height
        options.update(self._get_state('options'))
        return options

    def _create_js_instance(self):
        _ensure_sheet_js()
        holder = self._get_element('holder')
        self._emit_proxy = self._create_proxy(self._handle_emit)
        options = self._to_js(self._build_options())
        js.Object.assign(options, _sheet_js().options(self._emit_proxy))
        table = js.Tabulator.new(holder._dom_element, options)
        # dataChanged passes the plain data array; Tabulator components (cell,
        # row) must never cross into Python — Pyodide's capability probes
        # trigger Tabulator's unknown-property warnings.
        table.on('dataChanged', self._create_proxy(self._handle_data_changed))
        table.on('tableBuilt', self._create_proxy(self._handle_table_built))
        _sheet_js().install(table, holder._dom_element, self._emit_proxy)
        return table

    def _handle_table_built(self, *args):
        self._built = True
        if self._pending_redraw:
            self._pending_redraw = False
            self.redraw()

    def _handle_data_changed(self, data):
        """Tabulator changed a cell (the user typed, cleared or pasted over it)."""
        rows = [{k: ("" if v is None else v) for k, v in row.items()} for row in data.to_py()]
        if rows == self._current[0]:
            return                      # nothing differs: an echo of a change already taken
        self._remember_for_undo()
        self._set_state(data=rows)
        self._current = (rows, list(self._order))
        self._fire_event('data_change', rows)

    # ========== Public API ==========

    def get_data(self):
        """Current table contents as a list of row dicts."""
        if not self.is_initialized:
            return list(self._get_state('data'))
        return self.js_instance.getData().to_py()

    @property
    def columns(self):
        """The column names, in order."""
        return list(self._order)

    def set_data(self, data, columns=None):
        """
        Replace table contents, regenerating auto columns from the new data. A new document:
        what could be undone belongs to the old one, so the history starts over.
        """
        self._undo.clear()
        self._redo.clear()
        self._order = edits.columns_of(data, columns if columns is not None else [])
        self._set_state(data=data)
        self._current = (data, list(self._order))
        self._show(data)
        self._fire_event('data_change', data)
        return self

    # ---- editing: each of these makes a new state, which can be undone

    def add_row(self):
        """Insert a blank row below the selection, or at the end if none."""
        if not self.is_initialized:
            return self
        rows = self._rows()
        positions = self._selected_positions()
        index = max(positions) if positions else len(rows)
        self._apply(edits.insert_rows(rows, self._order, index),
                    select=self._cell(index + 1, 0))
        return self

    def delete_selected_rows(self):
        """
        Remove every row touched by the current selection.

        Returns the number deleted, so a caller can say nothing was selected
        rather than silently doing nothing.
        """
        if not self.is_initialized:
            return 0
        positions = self._selected_positions()
        if not positions:
            return 0
        self._apply(edits.delete_rows(self._rows(), [p - 1 for p in positions]))
        return len(positions)

    def delete_selected_columns(self):
        """Remove every column touched by the current selection; the number removed."""
        if not self.is_initialized:
            return 0
        fields = [f for f in json.loads(str(_sheet_js().fields(self.js_instance))) if f in self._order]
        if not fields:
            return 0
        rows, order = edits.delete_columns(self._rows(), self._order, fields)
        self._apply(rows, order)
        return len(fields)

    def undo(self):
        """Undo the last change; False when there is nothing to undo."""
        return self._travel(self._undo, self._redo)

    def redo(self):
        """Redo what was undone; False when there is nothing to redo."""
        return self._travel(self._redo, self._undo)

    async def request_add_column(self, field=None, side="right"):
        """Ask for a name and add a column beside `field` (the selected column, else the end)."""
        name = await self._ask_name("New column", "")
        if name is None:
            return None
        if field is None:
            chosen = [f for f in json.loads(str(_sheet_js().fields(self.js_instance)))
                      if f in self._order] if self.is_initialized else []
            field = chosen[-1] if chosen else None
        index = None
        if field in self._order:
            index = self._order.index(field) + (1 if side == "right" else 0)
        rows, order, used = edits.add_column(self._rows(), self._order, name, index)
        self._apply(rows, order, select=self._cell(1, order.index(used)) if rows else None)
        self._say(f"Added the column '{used}'.")
        return used

    async def request_rename(self, field):
        """Ask for a new name for a column and rename it."""
        if field not in self._order:
            return None
        name = await self._ask_name("Rename column", field)
        if name is None or name.strip() == field:
            return None
        try:
            rows, order = edits.rename_column(self._rows(), self._order, field, name)
        except ValueError as error:
            self._say(str(error))
            return None
        self._apply(rows, order)
        self._say(f"Renamed '{field}' to '{name.strip()}'.")
        return name.strip()

    # ---- the rest

    def redraw(self):
        """Recompute layout. Needed after the table becomes visible again:
        Tabulator sizes itself on render and measures zero while hidden."""
        if not self.is_initialized:
            return self
        if not self._built:
            self._pending_redraw = True
            return self
        try:
            self.js_instance.redraw(True)
        except Exception:
            # A table torn down between the request and the call has nothing
            # to redraw, and a failed relayout is never worth an error box.
            pass
        return self

    @property
    def is_ready(self):
        return self.is_initialized and self._built

    # ========== internals ==========

    def _rows(self):
        return list(self._get_state('data'))

    def _cell(self, row, column_index, rows=1, cols=1):
        """A block of cells to select afterwards: 1-based row, 0-based column."""
        if not self._order:
            return None
        column_index = max(0, min(column_index, len(self._order) - 1))
        return {"row": row, "field": self._order[column_index], "rows": rows, "cols": cols}

    def _selected_positions(self):
        return json.loads(str(_sheet_js().positions(self.js_instance)))

    def _say(self, text):
        if self.on_message:
            self.on_message(text)

    async def _ask_name(self, title, value):
        if self.prompt is None:
            return value or None
        return await self.prompt(title, "Column name", value)

    def _remember_for_undo(self):
        self._undo.append(self._current)
        del self._undo[:-self.UNDO_LIMIT]
        self._redo.clear()

    def _show(self, rows, select=None):
        """Put rows (and the columns) on the page."""
        if not self.is_initialized:
            return
        columns = None if self._get_state('columns') else self._to_js(self._column_definitions())
        _sheet_js().replace(self.js_instance, columns, self._to_js(rows),
                            self._to_js(select) if select else None)

    def _apply(self, rows, columns=None, select=None):
        """Make an edit: new rows (and columns), shown, kept for undo, announced."""
        self._remember_for_undo()
        if columns is not None:
            self._order = list(columns)
        self._set_state(data=rows)
        self._current = (rows, list(self._order))
        self._show(rows, select)
        self._fire_event('data_change', rows)

    def _travel(self, source, sink):
        if not source:
            return False
        sink.append(self._current)
        rows, order = source.pop()
        self._order = list(order)
        self._set_state(data=rows)
        self._current = (rows, list(order))
        self._show(rows)
        self._fire_event('data_change', rows)
        return True

    def _handle_emit(self, kind, payload):
        """What the shim reports: a key, a paste or a menu choice, as text."""
        kind = str(kind)
        try:
            data = json.loads(str(payload) or "{}")
        except ValueError:
            return ""
        rows, order = self._rows(), self._order
        if kind == "format":
            # The clipboard's text for some cells: one place decides how they are written.
            return edits.to_clipboard(data.get("lines", []))
        if kind == "undo":
            if not self.undo():
                self._say("Nothing to undo.")
        elif kind == "redo":
            if not self.redo():
                self._say("Nothing to redo.")
        elif kind == "paste":
            self._paste(data)
        elif kind == "clear":
            self._clear(data)
        elif kind == "rename":
            asyncio.ensure_future(self.request_rename(data.get("field")))
        elif kind == "add_column":
            asyncio.ensure_future(self.request_add_column(data.get("field"), data.get("side", "right")))
        elif kind == "delete_columns":
            fields = [f for f in data.get("fields", []) if f in order]
            if fields:
                new_rows, new_order = edits.delete_columns(rows, order, fields)
                self._apply(new_rows, new_order)
                self._say(f"Deleted {len(fields)} column{'s' if len(fields) != 1 else ''}.")
        elif kind == "insert_rows":
            # `position` is the clicked row, 1-based: above it is that index less one, below it is
            # the index just after.
            at = int(data.get("position", 1)) - (0 if data.get("below") else 1)
            count = max(1, int(data.get("count", 1)))
            self._apply(edits.insert_rows(rows, order, at, count), select=self._cell(at + 1, 0))
        elif kind == "duplicate_rows":
            positions = [int(p) - 1 for p in data.get("positions", [])]
            self._apply(edits.duplicate_rows(rows, positions))
        elif kind == "delete_rows":
            positions = [int(p) - 1 for p in data.get("positions", [])]
            self._apply(edits.delete_rows(rows, positions))
            self._say(f"Deleted {len(positions)} row{'s' if len(positions) != 1 else ''}.")

    def _clear(self, data):
        """Empty the selected cells (Delete, Backspace, or the second half of a cut): one undo step."""
        blocks = data.get("ranges", [])
        rows, count = edits.clear_cells(self._rows(), blocks)
        if count:
            first = blocks[0]
            span = sorted(first["rows"])
            contiguous = span == list(range(span[0], span[0] + len(span)))
            select = (self._cell(span[0] + 1, self._order.index(first["fields"][0]), len(span), len(first["fields"]))
                      if contiguous and first["fields"][0] in self._order else None)
            self._apply(rows, select=select)
        self._say(f"{'Cut' if data.get('cut') else 'Cleared'} {count:,} cell{'s' if count != 1 else ''}."
                  if count else "Nothing to clear.")

    def _paste(self, data):
        cells = edits.parse_clipboard(data.get("text", ""))
        if not cells:
            return
        order = self._order
        field = data.get("field")
        column_index = order.index(field) if field in order else 0
        row = max(0, int(data.get("row", 1)) - 1)
        before = (len(self._rows()), len(order))
        rows, new_order, written = edits.paste_block(
            self._rows(), order, cells, row, column_index,
            int(data.get("rows", 1)), int(data.get("cols", 1)))
        self._apply(rows, new_order, select=self._cell(written[0] + 1, written[1], written[2], written[3]))
        grown = []
        if len(rows) > before[0]:
            grown.append(f"{len(rows) - before[0]} row{'s' if len(rows) - before[0] != 1 else ''}")
        if len(new_order) > before[1]:
            grown.append(f"{len(new_order) - before[1]} column{'s' if len(new_order) - before[1] != 1 else ''}")
        self._say(f"Pasted {written[2]} × {written[3]} cells" + (f", adding {' and '.join(grown)}." if grown else "."))
