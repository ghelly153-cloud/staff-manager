"""LOCAL adapter - an isolated TEST COPY on disk. NOT a live connection.

Used for development and automated tests. It edits the file with openpyxl, which keeps formulas
and most formatting but is not as faithful as Excel itself, so production uses the Graph adapter.
"""
import os, re, shutil, threading
from datetime import date, datetime
from openpyxl import load_workbook, Workbook
from openpyxl.utils import coordinate_to_tuple, get_column_letter
from .base import Adapter, WorkbookError


class LocalAdapter(Adapter):
    name = "local"
    is_live_production = False

    def __init__(self, path, backup_dir):
        self.path, self.backup_dir = path, backup_dir
        self._lock = threading.RLock()
        self._backed_up = False
        self._wb = None
        self._wb_mtime = 0
        self._resolve_path()
        if not os.path.exists(self.path):
            raise WorkbookError("not_found", f"Test workbook not found: {os.path.basename(self.path)}")

    def _resolve_path(self):
        if os.path.exists(self.path):
            return
        candidates = [
            self.path,
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "test_workbook.xlsx")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "text_workbook.xlsx")),
            os.path.abspath("test_workbook.xlsx"),
            os.path.abspath("text_workbook.xlsx"),
            os.path.abspath("../test_workbook.xlsx"),
            os.path.abspath("../text_workbook.xlsx"),
            os.path.abspath("backend/test_workbook.xlsx"),
        ]
        for c in candidates:
            if os.path.exists(c):
                self.path = c
                return

    def describe(self):
        self._resolve_path()
        return {"adapter": "local", "label": "LOCAL TEST COPY (not live)", "file": os.path.basename(self.path)}

    def get_version(self):
        self._resolve_path()
        st = os.stat(self.path)
        return f"{st.st_mtime_ns}-{st.st_size}"

    @staticmethod
    def _grid(ws, ws_v):
        R, C = ws.max_row or 1, ws.max_column or 1
        def rows(w):
            out = []
            for r in w.iter_rows(min_row=1, max_row=R, max_col=C, values_only=True):
                out.append([None if (isinstance(v, str) and v == "") else v for v in r])
            return out
        f = rows(ws)
        v = rows(ws_v)
        # a formula cell without a cached value reads as None; keep None (unknown), never 0
        return {"values": v, "formulas": f, "hidden": ws.sheet_state != "visible"}

    def read_all(self):
        with self._lock:
            ver = self.get_version()
            if getattr(self, "_cache", None) and self._cache[0] == ver:
                return {"sheets": self._cache[1]}
            try:
                wf = load_workbook(self.path)
                wv = load_workbook(self.path, data_only=True)
            except Exception as ex:
                raise WorkbookError("structure", f"Could not open workbook: {type(ex).__name__}")
            sheets = {ws.title: self._grid(ws, wv[ws.title]) for ws in wf.worksheets}
            self._cache = (ver, sheets)
            return {"sheets": sheets}

    def read_sheet(self, name):
        return self.read_all()["sheets"].get(name)

    def _get_open_wb(self):
        mtime = os.path.getmtime(self.path) if os.path.exists(self.path) else 0
        if self._wb is None or getattr(self, "_wb_mtime", 0) != mtime:
            self._wb = load_workbook(self.path)
            self._wb_mtime = mtime
        return self._wb

    def _save(self, wb):
        tmp = self.path + ".tmp"
        wb.save(tmp)
        os.replace(tmp, self.path)
        self._wb_mtime = os.path.getmtime(self.path) if os.path.exists(self.path) else 0

    def _backup_once(self):
        if not self._backed_up:
            self.backup("auto-before-first-write")
            self._backed_up = True

    def _sync_cache_from_wb(self, wb):
        try:
            ver = self.get_version()
            # Generate grid directly from in-memory workbook
            sheets = {ws.title: self._grid(ws, ws) for ws in wb.worksheets}
            self._cache = (ver, sheets)
        except Exception:
            self._cache = None

    def write_cells(self, sheet, cells):
        self._check_fail()
        with self._lock:
            self._backup_once()
            wb = self._get_open_wb()
            if sheet not in wb.sheetnames:
                raise WorkbookError("not_found", f"Sheet “{sheet}” not found")
            ws = wb[sheet]
            for a1, v in cells.items():
                c = ws[a1]
                if isinstance(v, date) and not isinstance(v, datetime):
                    c.value = datetime(v.year, v.month, v.day)
                    c.number_format = "dd-mmm-yyyy"
                else:
                    c.value = v
            self._save(wb)
            self._sync_cache_from_wb(wb)

    def write_block(self, sheet, top_left, rows):
        r0, c0 = coordinate_to_tuple(top_left)
        cells = {}
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                cells[f"{get_column_letter(c0 + j)}{r0 + i}"] = v
        self.write_cells(sheet, cells)

    def append_rows(self, sheet, rows):
        self._check_fail()
        with self._lock:
            self._backup_once()
            wb = self._get_open_wb()
            ws = wb[sheet]
            first = ws.max_row + 1 if any(c.value is not None for c in ws[ws.max_row]) else ws.max_row
            for i, row in enumerate(rows):
                for j, v in enumerate(row):
                    ws.cell(first + i, j + 1).value = v
            self._save(wb)
            self._sync_cache_from_wb(wb)
            return first

    def ensure_sheet(self, name, headers):
        with self._lock:
            wb = self._get_open_wb()
            if name in wb.sheetnames:
                return False
            self._check_fail()
            self._backup_once()
            ws = wb.create_sheet(name)
            for j, h in enumerate(headers):
                ws.cell(1, j + 1).value = h
            # text columns so ISO dates and keys stay text
            for col in ("A", "B"):
                ws.column_dimensions[col].width = 22
            self._save(wb)
            self._sync_cache_from_wb(wb)
            return True

    def backup(self, label):
        os.makedirs(self.backup_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(self.path))[0]
        dst = os.path.join(self.backup_dir, f"{stem}__BACKUP__{label}__{datetime.now():%Y%m%d-%H%M%S-%f}.xlsx")
        shutil.copy2(self.path, dst)
        return os.path.basename(dst)
