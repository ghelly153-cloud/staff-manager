"""Workbook inventory: python scripts/audit.py /path/to/workbook.xlsx > docs/AUDIT.md   (read-only)"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.adapters.local import LocalAdapter
from app.model import build_snapshot
from app.inventory import build_inventory, to_markdown
a = LocalAdapter(sys.argv[1], "/tmp/_audit_backups")
print(to_markdown(build_inventory(build_snapshot(a.read_all(), a.get_version(), "", __import__("datetime").date.today())), "Workbook inventory (generated, read-only)"))
