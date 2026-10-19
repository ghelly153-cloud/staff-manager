"""Central payroll and operational work-day calculations. Pure functions, Decimal money, no I/O.

NON-NEGOTIABLE FINANCIAL POLICY:
  No employee has a fixed, approved compensation rate or payment amount.
  No payment amount is currently represented as authorised, payable, owed, due or outstanding.
  Existing spreadsheet numbers (e.g. ₹100, ₹17,900 totals, workbook balances) are unverified source data,
  not approved financial obligations. Monetary calculations remain deactivated until an authorised
  policy is formally introduced and approved.

Operational days recorded (Sept/Oct legacy counts and date-wise attendance) are tracked accurately.
"""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def D(x):
    return Decimal(str(x))


def money(x):
    return None if x is None else float(x.quantize(CENT, rounding=ROUND_HALF_UP))


def num(x):
    if x is None:
        return None
    return int(x) if x == x.to_integral_value() else float(x)


def _fmt(x):
    return "not recorded" if x.get("state") != "number" else f"{x['value']:g}"


def legacy_pay(e, policy_approved=False):
    """Legacy workbook-period operational attendance and source rate for one employee record."""
    s, o, r = e["sept"], e["octo"], e["rate"]
    out = {
        "path": "legacy", "sept": s["value"], "octo": o["value"],
        "rate": r["value"], "rate_state": r["state"],
        "days": None, "amount": None, "status": None, "reason": None, "steps": [],
        "financial_calculation_available": False,
    }
    if "invalid" in (s["state"], o["state"]):
        out.update(status="invalid_attendance", reason="Sept/Oct present days contain an invalid value")
        return out

    parts = [x for x in (s, o) if x["state"] == "number"]
    days = sum((D(x["value"]) for x in parts), Decimal(0)) if parts else None
    out["days"] = None if days is None else num(days)

    if days is not None:
        out["steps"].append(f"Total present = Sept {_fmt(s)} + Oct {_fmt(o)} = {num(days):g} days")

    if r["state"] == "invalid":
        out.update(status="invalid_rate", reason="Per Day Pay cell in workbook is invalid")
    elif r["state"] == "blank":
        out.update(status="rate_required", reason="Per Day Pay is blank in workbook (a blank rate is not ₹0)")
    elif days is None:
        out.update(status="no_attendance", reason="No attendance recorded in Sept/Oct (not the same as absent)")
    else:
        # Rate cell exists and days exist
        if policy_approved:
            amt = days * D(r["value"])
            out.update(status="confirmed", amount=money(amt), financial_calculation_available=True)
            out["steps"].append(f"Pay = {num(days):g} days × ₹{r['value']:g} = ₹{money(amt):,.2f}")
        else:
            out.update(
                status="rates_unauthorised",
                amount=None,
                reason="Compensation policy not approved — no payment obligation authorised",
                financial_calculation_available=False,
            )
            out["steps"].append(
                f"Source workbook indicates ₹{r['value']:g}/day for reference, but no compensation rate is authorised under current policy."
            )
    return out


def datewise_pay(records, rate, rules, period=None, policy_approved=False):
    """records: list of {date: date, status: str} for ONE employee. period: (from, to) or None."""
    paid = set(rules.get("paid_statuses") or ["Present"])
    cutoff = rules.get("legacy_cutoff_date")
    src_ok = rules.get("daily_rate_source") == "per_day_pay"
    lo, hi = period if period else (None, None)
    inp = [r for r in records if (lo is None or r["date"] >= lo) and (hi is None or r["date"] <= hi)]

    out = {
        "path": "datewise", "days": 0, "amount": None, "status": "none",
        "reason": None, "steps": [], "recorded": len(inp), "excluded_legacy_days": 0,
        "rate": rate["value"], "financial_calculation_available": False,
    }
    if not inp:
        return out

    paid_dates = [r for r in inp if r["status"] in paid]
    if cutoff is None or not src_ok:
        out.update(
            status="rules_required", days=len(paid_dates),
            reason="Confirm the legacy cut-off date and daily-rate rule before date-wise records are partitioned",
        )
        return out

    counted = [r for r in paid_dates if r["date"] > cutoff]
    out["excluded_legacy_days"] = len(paid_dates) - len(counted)
    out["days"] = len(counted)

    if rate["state"] == "invalid":
        out.update(status="invalid_rate", reason="Per Day Pay cell in workbook is invalid")
    elif rate["state"] == "blank":
        out.update(status="rate_required", reason="Per Day Pay is blank (a blank rate is not ₹0)")
    else:
        if policy_approved:
            amt = Decimal(len(counted)) * D(rate["value"])
            out.update(status="confirmed", amount=money(amt), financial_calculation_available=True)
            out["steps"].append(
                f"Date-wise pay = {len(counted)} days after {cutoff.isoformat()} × ₹{rate['value']:g} = ₹{money(amt):,.2f}"
            )
        else:
            out.update(
                status="rates_unauthorised",
                amount=None,
                reason="Compensation policy not approved — no payment obligation authorised",
                financial_calculation_available=False,
            )
            out["steps"].append(
                f"{len(counted)} date-wise days recorded after {cutoff.isoformat()}; rate unapproved under current policy."
            )
    return out


def combine(legacy, dw, policy_approved=False):
    """Overall employee pay evaluation. Under the current policy, amounts are withheld."""
    comps = [legacy] + ([dw] if dw["status"] != "none" else [])
    sts = [c["status"] for c in comps]

    if not policy_approved:
        # Check if there is an explicit problem status to report
        for bad in ("invalid_rate", "rate_required", "invalid_attendance", "rules_required", "no_attendance"):
            if bad in sts:
                return {
                    "status": bad, "amount": None,
                    "reason": next(c["reason"] for c in comps if c["status"] == bad),
                    "financial_calculation_available": False,
                }
        return {
            "status": "rates_unauthorised", "amount": None,
            "reason": "Compensation policy not approved — no payment obligation authorised",
            "financial_calculation_available": False,
        }

    if all(s == "confirmed" for s in sts):
        total = sum((D(c["amount"]) for c in comps), Decimal(0))
        return {"status": "confirmed", "amount": money(total), "reason": None, "financial_calculation_available": True}
    for bad in ("invalid_rate", "rate_required", "invalid_attendance", "rules_required", "no_attendance"):
        if bad in sts:
            return {
                "status": bad, "amount": None,
                "reason": next(c["reason"] for c in comps if c["status"] == bad),
                "financial_calculation_available": False,
            }
    return {"status": "no_attendance", "amount": None, "reason": None, "financial_calculation_available": False}


LABELS = {
    "confirmed": "Rates not authorised (policy unapproved)",
    "rates_unauthorised": "Rates not authorised",
    "rate_required": "Rate not provided",
    "invalid_rate": "Invalid rate cell",
    "no_attendance": "No attendance recorded",
    "invalid_attendance": "Invalid attendance cell",
    "rules_required": "Compensation policy not configured",
    "none": "—",
}


def summarize(rows, policy_approved=False):
    """Summarize operational rows. Under the non-negotiable financial policy, no amount is confirmed payable."""
    by = {}
    days_waiting = Decimal(0)
    pend_dw = 0
    total_legacy_days = Decimal(0)
    total_dw_days = 0
    has_source_rate = 0

    conf = Decimal(0)
    leg = Decimal(0)
    dwt = Decimal(0)

    for r in rows:
        st = r["overall"]["status"]
        by[st] = by.get(st, 0) + 1

        if r["legacy"]["days"] is not None:
            total_legacy_days += D(r["legacy"]["days"])
        if r["datewise"]["days"]:
            total_dw_days += r["datewise"]["days"]

        if r["legacy"].get("rate_state") == "number":
            has_source_rate += 1

        if r["datewise"]["status"] == "rules_required":
            pend_dw += 1
        if st in ("rate_required", "invalid_rate") and r["legacy"]["days"]:
            days_waiting += D(r["legacy"]["days"])

        if policy_approved:
            if r["legacy"]["status"] == "confirmed":
                leg += D(r["legacy"]["amount"])
                conf += D(r["legacy"]["amount"])
            if r["datewise"]["status"] == "confirmed":
                dwt += D(r["datewise"]["amount"])
                conf += D(r["datewise"]["amount"])

    return {
        "confirmed_total": money(conf) if policy_approved else None,
        "legacy_confirmed_total": money(leg) if policy_approved else None,
        "datewise_confirmed_total": money(dwt) if policy_approved else None,
        "by_status": by,
        "confirmed_count": by.get("confirmed", 0) if policy_approved else 0,
        "incomplete_count": sum(v for k, v in by.items() if k != "confirmed") if policy_approved else len(rows),
        "rate_missing_count": by.get("rate_required", 0) + by.get("invalid_rate", 0),
        "employees_with_source_rate": has_source_rate,
        "datewise_pending_rule_count": pend_dw,
        "days_awaiting_rate": num(days_waiting),
        "total_legacy_days": num(total_legacy_days),
        "total_datewise_days": total_dw_days,
        "total_present_days": num(total_legacy_days + Decimal(total_dw_days)),
        "compensation_configured": policy_approved,
        "policy_status": "Rates not authorised" if not policy_approved else "Policy approved",
        "policy_notice": (
            "Compensation not configured — rates not authorised. Financial calculations unavailable."
            if not policy_approved else ""
        ),
    }
