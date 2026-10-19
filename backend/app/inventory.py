"""Workbook inventory (Phase 1 audit) generated from the live snapshot - used by /api/inventory and scripts/audit.py."""
from .workbook.schema import col_letter


def build_inventory(snap):
    sheets = []
    for sp in snap.sheets:
        d = {"sheet": sp.name, "compatible": sp.compatible, "reason": sp.reason, "hidden": sp.hidden,
             "used_range": f"A1:{col_letter(max(sp.used_cols, 1) - 1)}{sp.used_rows}" if sp.used_rows else "(empty)",
             "formula_cells": sp.formula_count}
        if sp.compatible:
            d.update({
                "header_row": sp.header_row + 1, "title_cell": sp.title,
                "recognised_columns": {k: col_letter(c) for k, c in sp.cols.items()},
                "rate_column_heading": sp.rate_label, "row_counts": sp.row_counts,
                "employees": len(sp.employees),
                "summary_rows": {"total_row": sp.summary.get("total_row"), "advance": (sp.summary.get("advance") or {}).get("ref"),
                                 "sweets": (sp.summary.get("sweets") or {}).get("ref"), "balance": (sp.summary.get("balance") or {}).get("ref"),
                                 "balance_formula": (sp.summary.get("balance") or {}).get("formula"), "formula_verified": sp.summary.get("formula_verified")},
                "missing": {"rate": sum(1 for e in sp.employees if e["rate"]["state"] == "blank"),
                            "designation": sum(1 for e in sp.employees if not e["designation"]),
                            "location": sum(1 for e in sp.employees if not e["location"]),
                            "attendance_both_months": sum(1 for e in sp.employees if e["sept"]["state"] == "blank" and e["octo"]["state"] == "blank"),
                            "aadhaar": sum(1 for e in sp.employees if not e["aadhaar"]), "mobile": sum(1 for e in sp.employees if not e["mobile"]),
                            "from_date": sum(1 for e in sp.employees if e["from_date"]["state"] == "blank")},
                "app_columns_present": sorted(sp.app_cols), "issues": [i["message"] for i in sp.issues if i["severity"] != "info"],
                "info": [i["message"] for i in sp.issues if i["severity"] == "info"],
            })
        sheets.append(d)
    return {"sheets": sheets, "groups": snap.groups, "employee_records": len(snap.employees), "skipped": snap.skipped,
            "support_sheets_present": snap.support_present}


def to_markdown(inv, title="Workbook inventory"):
    L = [f"# {title}", "", f"* Compatible employee-group sheets: **{len(inv['groups'])}**", f"* Employee records (named staff rows): **{inv['employee_records']}**",
         f"* App support sheets present: {inv['support_sheets_present']}", ""]
    L += ["| Sheet | Used range | Title cell | Header row | Employees | Blank formatted rows | Summary rows | Formulas | Compatible |", "|---|---|---|---|---|---|---|---|---|"]
    for s in inv["sheets"]:
        if s["compatible"]:
            rc = s["row_counts"]
            sr = s["summary_rows"]
            L.append(f"| {s['sheet']} | {s['used_range']} | {s['title_cell']} | {s['header_row']} | {s['employees']} | {rc['blank_formatted']} | "
                     f"{'Total r%s' % sr['total_row'] if sr['total_row'] else 'none'} | {s['formula_cells']} | ✔ |")
        else:
            L.append(f"| {s['sheet']} | {s['used_range']} | | | | | | {s['formula_cells']} | ✘ {s['reason']} |")
    L += ["", "## Per-sheet detail", ""]
    for s in inv["sheets"]:
        if not s["compatible"]:
            continue
        L += [f"### {s['sheet']}", f"* Recognised columns: {', '.join(f'{k}={v}' for k, v in s['recognised_columns'].items())}",
              f"* Yearly-rate column heading: “{s['rate_column_heading']}”", f"* Row classification: {s['row_counts']}",
              f"* Group summary cells: {s['summary_rows']}", f"* Missing values (count of employees): {s['missing']}"]
        for m in s["issues"] + s["info"]:
            L.append(f"* ⚠ {m}")
        L.append("")
    return "\n".join(L)
