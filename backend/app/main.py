"""HTTP API + static frontend. Create with create_app(); `app` is built from the environment for uvicorn."""
import asyncio
import json
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

# Ensure Windows recognizes .js and .mjs as JavaScript (prevents browsers from blocking module scripts due to nosniff)
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import queries as Q
from . import reports as R
from .adapters.base import WorkbookError
from .adapters.local import LocalAdapter
from .auth import RANK, role_for
from .config import ALL_ATTENDANCE_STATUSES, load_settings
from .inventory import build_inventory
from .services import ApiError, Services
from .sync import SyncService

log = logging.getLogger("app")
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
PUBLIC_CONFIG = ("attendance_statuses", "paid_statuses", "legacy_cutoff_date", "daily_rate_source", "required_fields",
                 "block_future_attendance", "recent_departure_days", "locations", "designations", "id_migration_done_at")


def create_app(settings=None, adapter=None, token_provider=None, run_background=True):
    settings = settings or load_settings()
    errs = settings.validate()
    if errs:
        raise RuntimeError("Configuration problem:\n - " + "\n - ".join(errs))
    flows = provider = None
    if adapter is None:
        if settings.source == "local":
            adapter = LocalAdapter(settings.local_workbook_path, os.path.join(settings.data_dir, "backups"))
        else:
            from .adapters.graph import GraphAdapter
            from .auth import LoginFlows, MsalTokenProvider
            provider = token_provider or MsalTokenProvider(settings)
            adapter = GraphAdapter(settings.graph_drive_id, settings.graph_item_id, provider)
    if settings.source == "graph":
        from .auth import LoginFlows
        flows = LoginFlows(settings)
        provider = provider or token_provider
    sync = SyncService(settings, adapter)
    svc = Services(settings, adapter, sync)
    sub_state = {"task": None}

    @asynccontextmanager
    async def lifespan(app):
        tasks = []
        if run_background:
            tasks.append(asyncio.create_task(sync.run()))
            if settings.source == "graph" and settings.enable_webhooks and settings.https:
                tasks.append(asyncio.create_task(_subscription_loop(settings, adapter, sync)))
        else:
            sync._loop = asyncio.get_running_loop()
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(title="Employee Management", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    secret = settings.session_secret or "dev-only-not-secret"
    app.add_middleware(SessionMiddleware, secret_key=secret, https_only=settings.https, same_site="lax", max_age=8 * 3600, session_cookie="emp_session")
    app.state.settings, app.state.sync, app.state.svc, app.state.adapter = settings, sync, svc, adapter

    # ---------- security headers + CSRF ----------
    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.url.path.startswith("/webhooks/"):
            if request.headers.get("x-requested-with") != "emp-app":
                return JSONResponse({"code": "csrf", "message": "Blocked: missing request header."}, status_code=403)
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != f"{request.url.scheme}://{request.headers.get('host')}":
                return JSONResponse({"code": "csrf", "message": "Blocked: cross-site request."}, status_code=403)
        resp = await call_next(request)
        resp.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                             "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"})
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.exception_handler(ApiError)
    async def api_err(request, ex: ApiError):
        return JSONResponse({"code": ex.code, "message": ex.message, **ex.extra}, status_code=ex.status)

    # ---------- auth dependencies ----------
    def user_dep(min_role="viewer"):
        def dep(request: Request):
            u = request.session.get("user")
            if not u:
                raise HTTPException(401, "Sign in required")
            role = role_for(settings, u["email"]) if not settings.dev_auth else u["role"]
            if not role:
                request.session.clear()
                raise HTTPException(403, "Your account is not authorised for this app")
            if RANK[role] < RANK[min_role]:
                raise HTTPException(403, f"This needs the {min_role} role")
            return {**u, "role": role}
        return dep

    viewer, editor, admin = user_dep("viewer"), user_dep("editor"), user_dep("admin")

    # ---------- sign-in ----------
    @app.get("/auth/login")
    def login(request: Request):
        if settings.dev_auth:
            return RedirectResponse("/#/dev-login")
        flow = flows.start("signin", f"{settings.public_base_url}/auth/callback")
        request.session["flow"] = flow
        return RedirectResponse(flow["auth_uri"])

    @app.get("/auth/connect")
    def connect(request: Request, u=Depends(admin)):
        if settings.source != "graph":
            raise HTTPException(400, "Local test mode has no Microsoft connection")
        flow = flows.start("connect", f"{settings.public_base_url}/auth/callback")
        request.session["flow"] = flow
        return RedirectResponse(flow["auth_uri"])

    @app.get("/auth/callback")
    def callback(request: Request):
        flow = request.session.pop("flow", None)
        if not flow:
            return RedirectResponse("/#/signin-error")
        res = flows.finish(flow, dict(request.query_params), provider if flow.get("_purpose") == "connect" else None)
        claims = res.get("id_token_claims") or {}
        if "error" in res or claims.get("tid") != settings.tenant_id:
            log.warning("sign-in failed: %s", res.get("error"))
            return RedirectResponse("/#/signin-error")
        email = (claims.get("preferred_username") or claims.get("email") or "").lower()
        role = role_for(settings, email)
        if not role:
            return RedirectResponse("/#/not-authorised")
        request.session["user"] = {"email": email, "name": claims.get("name") or email}
        if flow.get("_purpose") == "connect":
            sync.poke("connected")
            return RedirectResponse("/#/sync")
        return RedirectResponse("/")

    @app.post("/auth/dev-login")
    async def dev_login(request: Request):
        if not settings.dev_auth:
            raise HTTPException(404)
        body = await request.json()
        role = body.get("role", "viewer")
        if role not in RANK:
            raise HTTPException(422, "bad role")
        request.session["user"] = {"email": f"dev-{role}@local.test", "name": f"Local {role}", "role": role}
        return {"ok": True}

    @app.get("/auth/status")
    def auth_status(request: Request):
        u = request.session.get("user")
        return {
            "dev_auth": bool(settings.dev_auth),
            "source": settings.source,
            "source_label": adapter.describe().get("label", settings.source),
            "is_live": bool(adapter.is_live_production),
            "authenticated": bool(u),
            "role": u.get("role") if u else None,
            "email": u.get("email") if u else None,
            "name": u.get("name") if u else None,
        }

    @app.post("/auth/logout")
    def logout(request: Request):
        request.session.clear()
        return {"ok": True}

    # ---------- basics ----------
    @app.get("/healthz")
    @app.get("/health")
    @app.get("/api/v1/health")
    @app.get("/api/health")
    def healthz():
        return {"ok": True, "status": "healthy"}

    @app.get("/api/me")
    def me(u=Depends(viewer)):
        return {"email": u["email"], "name": u["name"], "role": u["role"], "source": adapter.describe(),
                "live": bool(adapter.is_live_production), "dev_auth": settings.dev_auth}

    def _parse_filters(request: Request):
        p = request.query_params
        today = settings.today()
        f = {"date": Q.parse_date(p.get("date"), today), "group": p.get("group") or p.get("sheet") or None, "q": p.get("q"),
             "location": p.get("location") or None, "designation": p.get("designation") or None,
             "status": p.get("status") or None, "att": p.get("att") or None,
             "period_from": Q.parse_date(p.get("from")), "period_to": Q.parse_date(p.get("to")),
             "dep_from": Q.parse_date(p.get("dep_from")), "dep_to": Q.parse_date(p.get("dep_to"))}
        if p.get("dep_days"):
            try:
                f["dep_from"], f["dep_to"] = today - timedelta(days=int(p["dep_days"])), today
            except ValueError:
                pass
        return f, today

    def _period(f):
        return (f["period_from"], f["period_to"]) if (f["period_from"] or f["period_to"]) else None

    @app.get("/api/bootstrap")
    def bootstrap(u=Depends(viewer)):
        sn = svc.snap if sync.snapshot else None
        opts = Q.options(sn) if sn else {}
        return {"today": settings.today().isoformat(), "status": sync.status(),
                "role": u.get("role"), "email": u.get("email"), "name": u.get("name"),
                "locations": opts.get("locations", []), "designations": opts.get("designations", []),
                "options": opts, "all_attendance_statuses": ALL_ATTENDANCE_STATUSES,
                "config": {k: sn.config.get(k) for k in PUBLIC_CONFIG} if sn else None,
                "id_setup_needed": sn.id_setup_needed if sn else None, "groups": sn.groups if sn else [],
                "total_employees": len(sn.employees) if sn else 0,
                "version": sn.version if sn else None}

    @app.get("/api/dashboard")
    def dashboard(request: Request, u=Depends(viewer)):
        sn = svc.snap
        f, today = _parse_filters(request)
        emps = sn.employees
        sm = Q.summary(sn, emps, f["date"], _period(f), today)
        cards = Q.group_cards(sn, f["date"], _period(f), today)
        issues = [i for i in sn.issues if not i["resolution"]]
        by_code = {}
        for i in issues:
            if i["severity"] != "info":
                by_code[i["code"]] = by_code.get(i["code"], 0) + 1
        return {"summary": sm, "groups": cards, "status": sync.status(), "scope": "All employee records in the workbook",
                "quality": {"needs_review": sum(by_code.values()), "by_code": by_code, "errors": sum(1 for i in issues if i["severity"] == "error")},
                "skipped_sheets": sn.skipped, "id_setup_needed": sn.id_setup_needed}

    @app.get("/api/groups/{name}")
    def group(name: str, request: Request, u=Depends(viewer)):
        sn = svc.snap
        if name not in sn.groups:
            raise HTTPException(404, "Group not found")
        f, today = _parse_filters(request)
        card = next(c for c in Q.group_cards(sn, f["date"], _period(f), today) if c["name"] == name)
        return card

    @app.get("/api/employees")
    def employees(request: Request, u=Depends(viewer)):
        sn = svc.snap
        f, today = _parse_filters(request)
        p = request.query_params
        emps = Q.filter_employees(sn, f)
        emps = Q.sort_employees(emps, p.get("sort"), p.get("dir") == "desc")
        sm = Q.summary(sn, emps, f["date"], _period(f), today)
        size = max(1, min(200, int(p.get("page_size", 25))))
        page = max(1, int(p.get("page", 1)))
        total_pages = max(1, (len(emps) + size - 1) // size) if size else 1
        items = [Q.employee_row(sn, e, f["date"], _period(f)) for e in emps[(page - 1) * size: page * size]]
        return {"items": items, "total": len(emps), "total_pages": total_pages, "page": page, "page_size": size, "summary": sm,
                "scope": "Filtered employees", "options": Q.options(sn)}

    @app.get("/api/options")
    def get_options(u=Depends(viewer)):
        sn = svc.snap
        opts = Q.options(sn) if sn else {}
        cfg = sn.config if sn else {}
        return {
            "locations": opts.get("locations", []),
            "designations": opts.get("designations", []),
            "groups": sn.groups if sn else [],
            "attendance_statuses": cfg.get("attendance_statuses") or ALL_ATTENDANCE_STATUSES,
            "auto_assign_ids": settings.auto_assign_ids,
            "timezone": settings.timezone,
        }

    @app.get("/api/employees/{ref:path}")
    def employee(ref: str, request: Request, u=Depends(viewer)):
        sn = svc.snap
        e = sn.by_id.get(ref) or sn.by_key.get(ref.removeprefix("row:"))
        if not e:
            raise HTTPException(404, "Employee not found")
        f, today = _parse_filters(request)
        sp = sn.sheet(e["sheet"])
        pay = Q.pay_for(sn, e, _period(f))
        row = Q.employee_row(sn, e, f["date"], _period(f))
        atts = sorted(({"date": d.isoformat(), "status": r["status"], "notes": r["notes"], "by": r["updated_by"], "at": r["updated_at"]}
                       for d, r in sn.attendance.get(e["id"], {}).items()), key=lambda x: x["date"], reverse=True)[:90] if e["id"] else []
        hist = [a for a in reversed(sn.audit) if e["id"] and a["emp_id"] == e["id"]][:100]
        cols = sp.cols
        from .workbook.schema import ref as a1
        src = lambda k: a1(e["row"], cols[k]) if k in cols else None
        exp = {"name": e["name"], "designation": e["designation"], "location": e["location"],
               "rate": e["rate"]["value"], "sept": e["sept"]["value"], "octo": e["octo"]["value"],
               "from_date": e["from_date"]["value"].isoformat() if e["from_date"]["value"] else None,
               "to_date": e["to_date"]["value"].isoformat() if e["to_date"]["value"] else None}
        return {**row, "title": sp.title, "source": {"sheet": e["sheet"], "row": e["row"],
                "cells": {k: src(k) for k in ("name", "designation", "location", "rate", "sept", "octo", "aadhaar", "mobile", "from_date", "to_date")}},
                "pay": pay, "attendance_history": atts, "history": hist, "expected": exp,
                "dep_reason": e["dep_reason"], "verified_at": e["verified_at"], "rate_year": e["rate_year"],
                "sweet": e["sweet"], "from_date": exp["from_date"], "to_date": exp["to_date"], "staff_marker": e["staff_marker"],
                "issues": [i for i in sn.issues if i["emp_key"] == e["key"]],
                "provenance": {"identity/details": "Workbook (group sheet)", "status": "App (Employment Status column on the same row)",
                               "attendance": "App (_App_Attendance sheet)", "payable amount": "Calculated by the app from the inputs shown"}}

    @app.post("/api/employees/{ref:path}/reveal")
    def reveal(ref: str, u=Depends(admin)):
        return svc.reveal(u["email"], ref)

    @app.post("/api/employees")
    async def add_employee(request: Request, u=Depends(editor)):
        b = await request.json()
        return await asyncio.to_thread(svc.add_employee, u["email"], u["role"], b.get("data") or {}, bool(b.get("confirm_duplicate")))

    @app.patch("/api/employees/{ref:path}")
    @app.put("/api/employees/{ref:path}")
    async def edit_employee(ref: str, request: Request, u=Depends(editor)):
        b = await request.json()
        changes = b.get("changes") or b.get("data") or {k: v for k, v in b.items() if k not in ("expected",)}
        expected = b.get("expected") or {}
        # If status was updated via employee form, route to set_status
        if "status" in changes:
            st = changes["status"]
            if st in ("Active", "Departed"):
                await asyncio.to_thread(svc.set_status, u["email"], [{"ref": ref, "status": st, "dep_date": changes.get("dep_date"), "reason": changes.get("dep_reason") or changes.get("reason")}])
        clean_changes = {k: v for k, v in changes.items() if k not in ("status", "dep_date", "dep_reason", "reason")}
        if clean_changes:
            return await asyncio.to_thread(svc.update_employee, u["email"], u["role"], ref, clean_changes, expected)
        return {"ok": True}

    # ---------- attendance + status ----------
    @app.get("/api/attendance")
    def attendance(request: Request, u=Depends(viewer)):
        sn = svc.snap
        f, today = _parse_filters(request)
        if request.query_params.get("include_departed") == "true" or request.query_params.get("status") == "all":
            f["status"] = "all"
        else:
            f["status"] = f["status"] or "current"
        emps = Q.sort_employees(Q.filter_employees(sn, f), "row", False)
        sm = Q.summary(sn, emps, f["date"], None, today)
        items = [Q.employee_row(sn, e, f["date"], None, with_pay=False) for e in emps]
        has_records = any(bool(r.get("status")) for r in sn.attendance_by_date.get(f["date"], {}).values())
        return {"items": items, "summary": sm, "date": f["date"].isoformat(), "enabled_statuses": sn.config.get("attendance_statuses"),
                "has_any_records": has_records, "read_only": sn.id_setup_needed}

    @app.post("/api/attendance")
    async def mark(request: Request, u=Depends(editor)):
        b = await request.json()
        items = b.get("items")
        if items is None:
            if b.get("ref"):
                items = [{"ref": b["ref"], "date": b.get("date") or str(settings.today()), "status": b.get("status", "Present")}]
            else:
                items = []
        if len(items) > 1 and not b.get("confirmed"):
            raise ApiError(422, "confirm_required", "Bulk changes need confirmation.")
        return await asyncio.to_thread(svc.mark_attendance, u["email"], u["role"], items, bool(b.get("correction")))

    @app.post("/api/attendance/bulk")
    async def mark_bulk(request: Request, u=Depends(editor)):
        b = await request.json()
        date_str = b.get("date") or str(settings.today())
        status_str = b.get("status", "Present")
        items = b.get("items") or [{"ref": r, "date": date_str, "status": status_str} for r in b.get("refs", [])]
        return await asyncio.to_thread(svc.mark_attendance, u["email"], u["role"], items, False)

    @app.post("/api/attendance/{ref:path}")
    async def mark_single(ref: str, request: Request, u=Depends(editor)):
        b = await request.json()
        date_str = b.get("date") or str(settings.today())
        status_str = b.get("status", "Present")
        item = {"ref": ref, "date": date_str, "status": status_str}
        return await asyncio.to_thread(svc.mark_attendance, u["email"], u["role"], [item], False)

    @app.post("/api/status")
    async def status(request: Request, u=Depends(editor)):
        b = await request.json()
        items = b.get("items")
        if items is None:
            if b.get("ref"):
                items = [b]
            else:
                items = []
        if len(items) > 1 and not b.get("confirmed"):
            raise ApiError(422, "confirm_required", "Bulk changes need confirmation.")
        return await asyncio.to_thread(svc.set_status, u["email"], items)

    @app.post("/api/status/{ref:path}")
    async def status_single(ref: str, request: Request, u=Depends(editor)):
        b = await request.json()
        item = {"ref": ref, "status": b.get("status", "Active"), "dep_date": b.get("dep_date"), "reason": b.get("reason")}
        return await asyncio.to_thread(svc.set_status, u["email"], [item])

    # ---------- payroll / departed ----------
    @app.get("/api/payroll")
    def payroll(request: Request, u=Depends(viewer)):
        sn = svc.snap
        f, today = _parse_filters(request)
        f["status"] = f["status"] or "all"
        emps = Q.sort_employees(Q.filter_employees(sn, f), "row", False)
        rows = []
        for e in emps:
            pay = Q.pay_for(sn, e, _period(f))
            rows.append({**Q.employee_row(sn, e, f["date"], _period(f)), "legacy": pay["legacy"], "datewise": pay["datewise"], "overall": pay["overall"]})
        sm = Q.summary(sn, emps, f["date"], _period(f), today)
        groups = []
        for g in sn.groups:
            if f["group"] and g != f["group"]:
                continue
            ge = [e for e in emps if e["sheet"] == g]
            gs = Q.summary(sn, ge, f["date"], _period(f), today)
            groups.append({"name": g, "summary": gs, "amounts": Q.group_amounts(sn, sn.sheet(g), Q.summary(sn, [e for e in sn.employees if e["sheet"] == g], f["date"], _period(f), today))})
        from .config import config_rules
        r = config_rules(sn.config)
        return {"rows": rows, "summary": sm, "groups": groups, "rules": {"legacy_cutoff_date": sn.config.get("legacy_cutoff_date"),
                "daily_rate_source": sn.config.get("daily_rate_source"), "paid_statuses": sn.config.get("paid_statuses"),
                "datewise_ready": bool(r["legacy_cutoff_date"] and r["daily_rate_source"])},
                "note": "Group Advance/Sweets/Balance are shared group figures and are never split across employees."}

    @app.get("/api/departed")
    def departed(request: Request, u=Depends(viewer)):
        sn = svc.snap
        f, today = _parse_filters(request)
        f["status"] = "Departed"
        emps = Q.sort_employees(Q.filter_employees(sn, f), "name", False)
        rd = sn.config.get("recent_departure_days") or 30
        out = []
        for e in emps:
            r = Q.employee_row(sn, e, f["date"], _period(f))
            recs = [d for d, x in sn.attendance.get(e["id"], {}).items() if x["status"]] if e["id"] else []
            r.update(dep_reason=e["dep_reason"], last_att=max(recs).isoformat() if recs else None,
                     recent=bool(e["dep_date"] and today - timedelta(days=rd) <= e["dep_date"] <= today),
                     outstanding="Not available — the workbook has no per-employee payments ledger")
            out.append(r)
        return {"items": out, "total": len(out), "recent_days": rd,
                "active_count": sum(1 for e in sn.employees if e.get("status") != "Departed"),
                "total_staff": len(sn.employees),
                "summary": Q.summary(sn, emps, f["date"], _period(f), today)}

    # ---------- reports ----------
    @app.get("/api/reports")
    def report_list(u=Depends(viewer)):
        return [{"key": k, "title": v} for k, v in R.REPORTS.items()]

    @app.get("/api/reports/{name}")
    def report(name: str, request: Request, format: str = "json", u=Depends(viewer)):
        sn = svc.snap
        f, today = _parse_filters(request)
        if name == "audit" and RANK[u["role"]] < RANK["editor"]:
            raise HTTPException(403, "Audit history needs the editor role")
        rep = R.build(sn, name, f, sync.status()["last_success"], today)
        if not rep:
            raise HTTPException(404, "Unknown report")
        if format == "csv":
            return Response(R.to_csv(rep), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}-{today}.csv"'})
        if format == "xlsx":
            return Response(R.to_xlsx(rep), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f'attachment; filename="{name}-{today}.xlsx"'})
        return rep

    # ---------- data quality / admin ----------
    @app.get("/api/quality")
    def quality(request: Request, u=Depends(viewer)):
        sn = svc.snap
        p = request.query_params
        items = [i for i in sn.issues if (p.get("show") == "all" or not i["resolution"])]
        if p.get("group"):
            items = [i for i in items if i["sheet"] == p["group"]]
        counts = {}
        for i in items:
            counts.setdefault(i["code"], {"count": 0, "severity": i["severity"]})["count"] += 1
        return {"items": items, "counts": counts, "total": len(items)}

    @app.post("/api/quality/resolve")
    async def resolve(request: Request, u=Depends(admin)):
        b = await request.json()
        return await asyncio.to_thread(svc.resolve_issue, u["email"], b.get("fingerprint", ""), b.get("note"), bool(b.get("undo")))

    @app.post("/api/quality/resolve-all")
    async def resolve_all(request: Request, u=Depends(admin)):
        try:
            b = await request.json()
        except Exception:
            b = {}
        fps = b.get("fingerprints")
        if not fps:
            fps = [i["fingerprint"] for i in svc.snap.issues if not i.get("resolution")]
        note = b.get("note") or "Acknowledged"
        res = await asyncio.to_thread(svc.resolve_issues_bulk, u["email"], fps, note)
        return res

    @app.get("/api/config")
    def get_config(u=Depends(viewer)):
        sn = svc.snap
        return {"config": {k: sn.config.get(k) for k in PUBLIC_CONFIG}, "all_attendance_statuses": ALL_ATTENDANCE_STATUSES,
                "roles": {"admins": len(settings.admins), "editors": len(settings.editors), "viewers": len(settings.viewers)} if u["role"] == "admin" else None}

    @app.put("/api/config/{key}")
    async def put_config(key: str, request: Request, u=Depends(admin)):
        b = await request.json()
        return await asyncio.to_thread(svc.set_config, u["email"], key, b.get("value"))

    @app.get("/api/audit")
    def audit(limit: int = 200, u=Depends(editor)):
        return {"items": list(reversed(svc.snap.audit))[:min(limit, 1000)]}

    @app.get("/api/setup/plan")
    def setup_plan(u=Depends(admin)):
        return svc.plan_setup()

    @app.post("/api/setup/run")
    async def setup_run(request: Request, u=Depends(admin)):
        try:
            b = await request.json()
        except Exception:
            b = {"confirmed": True}
        return await asyncio.to_thread(svc.run_setup, u["email"])

    @app.get("/api/inventory")
    def inventory(u=Depends(admin)):
        return build_inventory(svc.snap)

    # ---------- sync ----------
    @app.get("/api/sync/status")
    def sync_status(u=Depends(viewer)):
        s = sync.status()
        if settings.source == "graph" and provider:
            s["account"] = provider.privacy_safe_account()
        s["can_connect"] = u["role"] == "admin" and settings.source == "graph"
        s["file_name"] = adapter.describe().get("file")
        s["support_sheets"] = svc.snap.support_present if sync.snapshot else None
        return s

    last_manual = {"t": 0.0}

    @app.post("/api/sync/refresh")
    async def sync_refresh(u=Depends(viewer)):
        now = datetime.now().timestamp()
        if now - last_manual["t"] < 1:
            return {"ok": True, "changed": False, "status": sync.status(), "note": "Just refreshed"}
        last_manual["t"] = now
        changed = await asyncio.to_thread(sync.refresh, True, "manual")
        return {"ok": sync.state == "connected", "changed": changed, "status": sync.status()}

    @app.get("/api/events")
    async def events(request: Request, u=Depends(viewer)):
        q = sync.subscribe()

        async def gen():
            try:
                yield "retry: 5000\n\n"
                yield f"data: {json.dumps({'type': 'status', 'status': sync.status()})}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=20)
                        yield f"data: {json.dumps(ev)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                sync.unsubscribe(q)
        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---------- Microsoft Graph webhooks (no cookie auth: validated by clientState) ----------
    @app.post("/webhooks/graph")
    @app.post("/webhooks/graph/lifecycle")
    async def graph_hook(request: Request, validationToken: str | None = None):
        if validationToken:                                  # subscription validation handshake (must answer < 10 s)
            return PlainTextResponse(validationToken)
        try:
            body = await request.json()
        except Exception:
            return Response(status_code=400)
        for n in body.get("value", []):
            if n.get("clientState") != settings.webhook_client_state or not settings.webhook_client_state:
                continue
            ev = n.get("lifecycleEvent")
            if ev in ("reauthorizationRequired", "subscriptionRemoved", "missed"):
                sync.webhook["status"] = f"lifecycle: {ev}"
                sub_state["needs_renew"] = True
            sync.poke("webhook")
        return Response(status_code=202)

    app.state.sub_state = sub_state

    # ---------- frontend ----------
    if FRONTEND.exists():
        app.mount("/js", StaticFiles(directory=FRONTEND / "js"), name="js")
        app.mount("/icons", StaticFiles(directory=FRONTEND / "icons"), name="icons")

        @app.get("/")
        def index():
            return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})

        @app.get("/manifest.json", include_in_schema=False)
        def manifest_json():
            return FileResponse(FRONTEND / "manifest.webmanifest", media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})

        for fn in ("index.html", "styles.css", "manifest.webmanifest", "sw.js", "favicon.svg"):
            def _mk(fn=fn):
                def h():
                    return FileResponse(FRONTEND / fn, headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"} if fn == "sw.js" else {"Cache-Control": "no-cache"})
                return h
            app.add_api_route("/" + fn, _mk(), methods=["GET"], include_in_schema=False)
    return app


async def _subscription_loop(settings, adapter, sync):
    """Create the Graph change-notification subscription and keep it alive (renew well before expiry)."""
    path = os.path.join(settings.data_dir, "subscription.json")
    wh = sync.webhook
    wh["enabled"] = True
    state = {}
    if os.path.exists(path):
        try:
            state = json.load(open(path))
        except ValueError:
            state = {}
    while True:
        try:
            exp = state.get("expires")
            soon = (not exp) or datetime.fromisoformat(exp.replace("Z", "+00:00")) < datetime.now().astimezone() + timedelta(days=2)
            if state.get("id") and soon:
                try:
                    j = await asyncio.to_thread(adapter.renew_subscription, state["id"])
                    state["expires"] = j.get("expirationDateTime")
                except WorkbookError:
                    state = {}
            if not state.get("id"):
                j = await asyncio.to_thread(adapter.subscribe, f"{settings.public_base_url}/webhooks/graph",
                                            f"{settings.public_base_url}/webhooks/graph/lifecycle", settings.webhook_client_state)
                state = {"id": j.get("id"), "expires": j.get("expirationDateTime")}
            os.makedirs(settings.data_dir, exist_ok=True)
            json.dump(state, open(path, "w"))
            wh.update(status="active", subscription_id=(state["id"] or "")[:8] + "…", expires=state.get("expires"))
        except WorkbookError as ex:
            wh.update(status=f"not active: {ex.kind} (polling continues)")
        except Exception:
            wh.update(status="not active (polling continues)")
        await asyncio.sleep(3600)


def build_default_app():
    return create_app()
