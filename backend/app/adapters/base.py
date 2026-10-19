"""Adapter contract: the ONLY place that knows how to talk to a workbook store.
All application logic (parse/calc/validate) is above this line and store-agnostic."""


class WorkbookError(Exception):
    """kind: auth | permission | not_found | throttled | locked | network | structure | conflict | write_failed | unknown"""

    def __init__(self, kind, message, retry_after=None, detail=None):
        super().__init__(message)
        self.kind, self.message, self.retry_after, self.detail = kind, message, retry_after, detail

    def to_dict(self):
        return {"kind": self.kind, "message": self.message, "retry_after": self.retry_after}


class Adapter:
    name = "abstract"
    is_live_production = False     # only the Graph adapter pointed at the real cloud workbook is "live"
    fail_writes = False            # test hook ONLY (never reachable over HTTP)

    def describe(self): raise NotImplementedError          # privacy-safe description for the Sync page
    def get_version(self): raise NotImplementedError       # cheap change token
    def read_all(self): raise NotImplementedError          # {"sheets": {name: {values, formulas, hidden}}}
    def read_sheet(self, name): raise NotImplementedError  # live re-read of one sheet (conflict checks)
    def write_cells(self, sheet, cells): raise NotImplementedError   # {"J5": value, ...}  (date objects allowed)
    def write_block(self, sheet, top_left, rows): raise NotImplementedError
    def append_rows(self, sheet, rows): raise NotImplementedError    # -> first new row number
    def ensure_sheet(self, name, headers): raise NotImplementedError
    def backup(self, label): raise NotImplementedError

    def _check_fail(self):
        if self.fail_writes:
            raise WorkbookError("write_failed", "Simulated write failure")
