"""Runtime settings (from environment) and workbook-stored rule defaults.

Secrets come ONLY from environment variables / a secrets manager - never from code or git.
"""
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo


def _csv(name):
    return [x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip()]


@dataclass
class Settings:
    source: str = "local"                    # "graph" (production) | "local" (isolated test copy)
    local_workbook_path: str = ""
    graph_drive_id: str = ""
    graph_item_id: str = ""
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    public_base_url: str = "http://localhost:8000"
    session_secret: str = ""
    token_encryption_key: str = ""
    sync_interval_seconds: int = 30
    admins: list = field(default_factory=list)
    editors: list = field(default_factory=list)
    viewers: list = field(default_factory=list)
    dev_auth: bool = False
    data_dir: str = "./data"
    auto_assign_ids: bool = True
    webhook_client_state: str = ""
    timezone: str = "Asia/Kolkata"
    enable_webhooks: bool = True

    @property
    def tz(self):
        return ZoneInfo(self.timezone)

    def today(self):
        return datetime.now(self.tz).date()

    def now_iso(self):
        return datetime.now(self.tz).isoformat(timespec="seconds")

    @property
    def https(self):
        return self.public_base_url.startswith("https://")

    def validate(self):
        errs = []
        if self.source not in ("graph", "local"):
            errs.append("SOURCE must be 'graph' or 'local'")
        if self.source == "graph":
            for k in ("graph_drive_id", "graph_item_id", "tenant_id", "client_id", "client_secret",
                      "session_secret", "token_encryption_key", "webhook_client_state"):
                if not getattr(self, k):
                    errs.append(f"{k.upper()} is required when SOURCE=graph")
            if self.dev_auth:
                errs.append("DEV_AUTH must be off when SOURCE=graph (production needs Microsoft sign-in)")
            if not (self.admins or self.editors or self.viewers):
                errs.append("Set at least one of ROLE_ADMINS / ROLE_EDITORS / ROLE_VIEWERS")
        else:
            if not self.local_workbook_path:
                errs.append("LOCAL_WORKBOOK_PATH is required when SOURCE=local")
        if self.dev_auth and self.source != "local":
            errs.append("DEV_AUTH is only allowed with SOURCE=local")
        return errs


def load_settings():
    e = os.getenv
    return Settings(
        source=e("SOURCE", "local").lower(), local_workbook_path=e("LOCAL_WORKBOOK_PATH", ""),
        graph_drive_id=e("GRAPH_DRIVE_ID", ""), graph_item_id=e("GRAPH_ITEM_ID", ""),
        tenant_id=e("AZURE_TENANT_ID", ""), client_id=e("AZURE_CLIENT_ID", ""), client_secret=e("AZURE_CLIENT_SECRET", ""),
        public_base_url=e("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/"),
        session_secret=e("SESSION_SECRET", ""), token_encryption_key=e("TOKEN_ENCRYPTION_KEY", ""),
        sync_interval_seconds=max(10, int(e("SYNC_INTERVAL_SECONDS", "30"))),
        admins=_csv("ROLE_ADMINS"), editors=_csv("ROLE_EDITORS"), viewers=_csv("ROLE_VIEWERS"),
        dev_auth=e("DEV_AUTH", "0") == "1", data_dir=e("DATA_DIR", "./data"),
        auto_assign_ids=e("AUTO_ASSIGN_NEW_IDS", "1") == "1", webhook_client_state=e("WEBHOOK_CLIENT_STATE", ""),
        timezone=e("APP_TIMEZONE", "Asia/Kolkata"), enable_webhooks=e("ENABLE_WEBHOOKS", "1") == "1",
    )


# ---- rules/options stored in the workbook (_App_Config). Nothing payroll-related is pre-confirmed. ----
CONFIG_DEFAULTS = {
    "locations": [],                      # admin-approved extras; established values are also read from the data
    "designations": [],
    "attendance_statuses": ["Present", "Absent"],    # admin may enable "Leave" and "Weekly Off/Holiday"
    "paid_statuses": ["Present"],
    "legacy_cutoff_date": None,           # ISO date. UNSET until an authorised person confirms it.
    "daily_rate_source": None,            # "per_day_pay" once confirmed. UNSET until confirmed.
    "required_fields": ["designation", "location"],
    "block_future_attendance": True,
    "id_migration_done_at": None,
    "recent_departure_days": 30,
    "issue_resolutions": {},              # fingerprint -> {by, at, note}
}
ALL_ATTENDANCE_STATUSES = ["Present", "Absent", "Leave", "Weekly Off/Holiday"]


def config_rules(cfg):
    """Pay rules in the shape calc.py expects."""
    cut = cfg.get("legacy_cutoff_date")
    try:
        cut = date.fromisoformat(cut) if cut else None
    except ValueError:
        cut = None
    return {"paid_statuses": cfg.get("paid_statuses") or ["Present"], "legacy_cutoff_date": cut,
            "daily_rate_source": cfg.get("daily_rate_source")}
