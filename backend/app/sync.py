"""Keeps the in-memory snapshot in step with the workbook.

* Fallback check every SYNC_INTERVAL_SECONDS (cheap metadata request; the workbook is only re-read if its
  change token moved), plus instant triggers from Graph webhooks and a manual "Refresh now".
* Honest status: connected / syncing / changes_detected / stale / sync_failed / auth_required / not_connected.
* Back-off on throttling and repeated failures. Never shows success it did not get.
"""
import asyncio
import logging
import threading
from datetime import datetime

from .adapters.base import WorkbookError
from .model import build_snapshot

log = logging.getLogger("sync")

LABELS = {
    "connected": "Connected", "syncing": "Syncing…", "changes_detected": "Changes detected",
    "stale": "Stale data", "sync_failed": "Sync failed", "auth_required": "Sign-in needed",
    "not_connected": "Not connected",
}


class SyncService:
    def __init__(self, settings, adapter):
        self.s, self.adapter = settings, adapter
        self.lock = threading.RLock()            # serialises refreshes AND writes
        self.snapshot = None
        self.state = "not_connected"
        self.last_success = None
        self.last_attempt = None
        self.last_error = None
        self.last_change_at = None
        self.consecutive_failures = 0
        self.retry_after_until = 0.0
        self.webhook = {"enabled": False, "status": "not configured", "subscription_id": None, "expires": None, "last_notification": None}
        self.listeners = []                      # [(loop, asyncio.Queue)]
        self.post_sync_hook = None               # set by Services (auto-assign IDs)
        self._wake = None
        self._loop = None
        self.manual_note = None

    # ---------- state ----------
    def _stale(self):
        if not self.last_success:
            return False
        age = (datetime.now() - self.last_success).total_seconds()
        return age > max(90, self.s.sync_interval_seconds * 3)

    def status(self):
        st = self.state
        if st == "connected" and self._stale():
            st = "stale"
        is_live = bool(self.adapter.is_live_production)
        base_label = LABELS.get(st, st)
        if not is_live and st == "connected":
            base_label = "Local Test Copy (Connected)"
        return {
            "state": st, "label": base_label,
            "last_success": self.last_success.isoformat(timespec="seconds") if self.last_success else None,
            "last_attempt": self.last_attempt.isoformat(timespec="seconds") if self.last_attempt else None,
            "last_change": self.last_change_at.isoformat(timespec="seconds") if self.last_change_at else None,
            "last_error": self.last_error, "interval_seconds": self.s.sync_interval_seconds,
            "version": self.snapshot.version if self.snapshot else None, "webhook": self.webhook,
            "source": self.adapter.describe(), "live": is_live,
            "consecutive_failures": self.consecutive_failures,
        }

    # ---------- events to browsers ----------
    def subscribe(self):
        loop = self._loop or asyncio.get_event_loop()
        q = asyncio.Queue(maxsize=50)
        self.listeners.append((loop, q))
        return q

    def unsubscribe(self, q):
        self.listeners = [(l, x) for (l, x) in self.listeners if x is not q]

    def _emit(self, kind, extra=None):
        ev = {"type": kind, "status": self.status(), **(extra or {})}
        for loop, q in list(self.listeners):
            try:
                loop.call_soon_threadsafe(self._put, q, ev)
            except RuntimeError:
                pass

    @staticmethod
    def _put(q, ev):
        try:
            q.put_nowait(ev)
        except asyncio.QueueFull:
            pass

    # ---------- core ----------
    def refresh(self, force=False, reason="poll"):
        """Returns True if the snapshot changed. Never raises."""
        with self.lock:
            self.last_attempt = datetime.now()
            prev_state = self.state
            try:
                ver = self.adapter.get_version()
                if not force and self.snapshot and ver == self.snapshot.version:
                    self._ok(False)
                    return False
                if self.snapshot and ver != self.snapshot.version:
                    self.state = "changes_detected"
                    self._emit("status")
                self.state = "syncing"
                self._emit("status")
                raw = self.adapter.read_all()
                snap = build_snapshot(raw, ver, self.s.now_iso(), self.s.today())
                self.snapshot = snap
                self.last_change_at = datetime.now()
                self._ok(True, reason)
            except WorkbookError as ex:
                self._fail(ex)
                return False
            except Exception as ex:                      # malformed workbook etc. - never crash the loop
                log.exception("sync error")
                self._fail(WorkbookError("structure", f"Workbook could not be processed ({type(ex).__name__})"))
                return False
        if self.post_sync_hook:
            try:
                self.post_sync_hook()
            except Exception:
                log.exception("post-sync hook failed")
        return True

    def _ok(self, changed, reason=None):
        self.state = "connected"
        self.last_success = datetime.now()
        self.last_error = None
        self.consecutive_failures = 0
        self.retry_after_until = 0
        self._emit("data" if changed else "status", {"reason": reason})

    def _fail(self, ex):
        self.consecutive_failures += 1
        self.last_error = {**ex.to_dict(), "at": datetime.now().isoformat(timespec="seconds")}
        self.state = "auth_required" if ex.kind == "auth" else "sync_failed"
        if ex.kind == "throttled" and ex.retry_after:
            self.retry_after_until = datetime.now().timestamp() + ex.retry_after
        log.warning("sync failed: %s", ex.kind)
        self._emit("status")

    def delay(self):
        """Seconds to wait before the next poll: normal interval, or back-off after failures / throttling."""
        base = self.s.sync_interval_seconds
        if self.consecutive_failures:
            base = min(300, base * (2 ** min(self.consecutive_failures, 4)))
        wait = max(base, self.retry_after_until - datetime.now().timestamp())
        return wait

    def poke(self, reason="webhook"):
        """Thread-safe: ask the loop to check now (used by webhook handler)."""
        self.webhook["last_notification"] = datetime.now().isoformat(timespec="seconds")
        if self._loop and self._wake:
            self._loop.call_soon_threadsafe(self._wake.set)

    async def run(self):
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        while True:
            await asyncio.to_thread(self.refresh, False, "poll")
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.delay())
            except asyncio.TimeoutError:
                pass
            self._wake.clear()
