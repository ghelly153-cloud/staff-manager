"""Column schema for the employee-group worksheets.

Columns are located by HEADER TEXT, never by fixed letter, so a sheet whose
columns are shifted still works and an incompatible sheet is reported, not guessed.
"""
import re
from datetime import date, datetime, timedelta

SUPPORT_PREFIX = "_App_"          # sheets the app creates; never shown as employee groups
SHEET_ATTENDANCE = "_App_Attendance"
SHEET_AUDIT = "_App_Audit"
SHEET_CONFIG = "_App_Config"

ATTENDANCE_HEADERS = ["Key", "Date", "Employee ID", "Group", "Status", "Notes", "Updated At", "Updated By"]
AUDIT_HEADERS = ["Timestamp", "Actor", "Action", "Employee ID", "Group", "Field", "Before", "After", "Note"]
CONFIG_HEADERS = ["Key", "Value (JSON)", "Updated At", "Updated By"]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower()) if s is not None else ""


# source columns (header text -> key)
ALIASES = {
    "no": ["no"], "name": ["staffname", "name"], "designation": ["designation"],
    "location": ["loctation", "location"], "staff": ["staff"],
    "sept": ["septpresent", "septemberpresent"], "octo": ["octopresent", "octpresent", "octoberpresent"],
    "total": ["totalpresent"], "rate": ["perdaypay"], "net": ["netpay"],
    "sweet": ["sweetkg"], "aadhaar": ["aadhar", "aadhaar"], "mobile": ["mobile"],
    "from_date": ["fromdate"], "to_date": ["todate"],
}
# columns the app adds (documented one-time structural change, backed up first)
APP_COLUMNS = [("emp_id", "App ID"), ("status", "Employment Status"), ("dep_date", "Departure Date"),
               ("dep_reason", "Departure Reason"), ("verified_at", "Status Verified")]
APP_ALIASES = {"emp_id": ["appid", "appemployeeid"], "status": ["employmentstatus"],
               "dep_date": ["departuredate"], "dep_reason": ["departurereason"], "verified_at": ["statusverified"]}
CORE_FOR_COMPAT = ["name", "designation", "location", "sept", "octo", "total", "rate", "net"]
SUMMARY_LABELS = {"total", "advance", "sweets", "balance", "grandtotal", "subtotal"}


def col_letter(i):  # 0-based -> A, B, ..., AA
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def ref(row1, col0):  # (1-based row, 0-based col) -> "J5"
    return f"{col_letter(col0)}{row1}"


# ---- value normalisation: blank / number / invalid are DIFFERENT states ----
def blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def to_number(v):
    """-> (state, value). state: blank | number | invalid | text_number"""
    if blank(v):
        return "blank", None
    if isinstance(v, bool):
        return "invalid", None
    if isinstance(v, (int, float)):
        return "number", v
    if isinstance(v, str):
        t = v.strip().replace(",", "").replace("₹", "")
        try:
            return "text_number", float(t) if "." in t else int(t)
        except ValueError:
            return "invalid", None
    return "invalid", None


_EPOCH = datetime(1899, 12, 30)


def to_date(v):
    """-> (state, date). state: blank | date | invalid. Day-first for text (India)."""
    if blank(v):
        return "blank", None
    if isinstance(v, datetime):
        return "date", v.date()
    if isinstance(v, date):
        return "date", v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 < v < 80000:
            return "date", (_EPOCH + timedelta(days=float(v))).date()
        return "invalid", None
    if isinstance(v, str):
        t = v.strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d.%m.%Y"):
            try:
                return "date", datetime.strptime(t, fmt).date()
            except ValueError:
                pass
    return "invalid", None


def serial_from_date(d):
    return (datetime(d.year, d.month, d.day) - _EPOCH).days
