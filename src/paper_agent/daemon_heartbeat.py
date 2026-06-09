"""Daemon liveness heartbeat — a tiny JSON file written by the scheduler.

The web admin dashboard reads this file to tell whether the daemon is
currently up and healthy. The contract is:

- The daemon writes the file once on startup (PID + start time) and
  re-writes it every time a scheduled job fires (ingest or digest), so
  ``last_heartbeat_at`` advances at most every ``ingest_interval_minutes``.
- Health = (PID currently exists) AND (heartbeat younger than
  ``2 * ingest_interval_minutes``). Older heartbeats mean the scheduler
  is wedged even though the process is alive.

We use a plain JSON file instead of a DB table so the admin reader can
work even when SQLite is locked, and because the file is human-readable
for debugging (``cat paper_agent.db.daemon.json``).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Heartbeat lives next to the SQLite DB so deployments that move db_path
# automatically move the heartbeat too — the operator never has a stale
# heartbeat pointing at a daemon for a different DB.
HEARTBEAT_SUFFIX = ".daemon.json"


def heartbeat_path(db_path: str | Path) -> Path:
    """Return the path of the heartbeat file for a given DB path."""
    return Path(str(db_path) + HEARTBEAT_SUFFIX)


def write_heartbeat(
    db_path: str | Path,
    *,
    started_at: str | None = None,
    last_event: str = "tick",
    extra: dict | None = None,
) -> None:
    """Write the heartbeat. Best-effort — never raises.

    ``started_at`` is preserved across ticks: when not given, we try to
    keep the existing one so ``uptime`` stays correct. ``last_event`` is
    a short string like ``"ingest"`` / ``"digest"`` / ``"startup"`` shown
    on the dashboard to indicate what the daemon was last doing.
    """
    path = heartbeat_path(db_path)
    now = datetime.now().isoformat(timespec="seconds")

    # Preserve started_at across heartbeats if not explicitly provided.
    if started_at is None:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            started_at = existing.get("started_at", now)
        except (OSError, json.JSONDecodeError):
            started_at = now

    payload = {
        "pid": os.getpid(),
        "started_at": started_at,
        "last_heartbeat_at": now,
        "last_event": last_event,
    }
    if extra:
        payload.update(extra)

    try:
        # Atomic-ish write: write to temp + rename so a reader can never
        # see a half-written file. On Windows os.replace is atomic.
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("Failed to write daemon heartbeat to %s: %s", path, e)


def read_heartbeat(db_path: str | Path) -> dict | None:
    """Return the heartbeat payload, or None when the file is missing/corrupt."""
    path = heartbeat_path(db_path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def pid_is_alive(pid: int) -> bool:
    """Best-effort check that a PID exists. Works on POSIX and Windows.

    On POSIX, ``os.kill(pid, 0)`` raises ProcessLookupError if no such
    process. On Windows, signal-0 is unsupported, so we fall back to
    opening the process via ctypes (no extra dependency).
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        # Windows path: OpenProcess with PROCESS_QUERY_LIMITED_INFORMATION.
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000  # noqa: N806 — Win32 API constant
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h == 0:
            return False
        try:
            # ExitCode == STILL_ACTIVE (259) means the process hasn't exited.
            exit_code = ctypes.c_ulong(0)
            ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
            return bool(ok) and exit_code.value == 259
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    # POSIX
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it — treat as alive.
        return True
    except OSError:
        return False


def assess_health(db_path: str | Path, ingest_interval_minutes: int) -> dict:
    """Combine heartbeat + PID check into a single status dict for the UI.

    The returned dict always contains the keys the admin template expects,
    even when the daemon has never started. Possible ``status`` values:

    - ``"never_started"``: no heartbeat file present
    - ``"dead"``: PID no longer exists
    - ``"stale"``: PID alive but heartbeat older than 2× ingest interval
                   — scheduler likely wedged
    - ``"running"``: PID alive and heartbeat is recent
    """
    hb = read_heartbeat(db_path)
    if hb is None:
        return {
            "status": "never_started",
            "pid": None,
            "started_at": None,
            "last_heartbeat_at": None,
            "last_event": None,
            "age_seconds": None,
        }

    pid = int(hb.get("pid", 0))
    alive = pid_is_alive(pid)
    last_hb_str = hb.get("last_heartbeat_at")

    age_seconds: float | None = None
    if last_hb_str:
        try:
            age_seconds = (datetime.now() - datetime.fromisoformat(last_hb_str)).total_seconds()
        except (TypeError, ValueError):
            age_seconds = None

    # 2× interval is the staleness threshold: the daemon misses one full
    # cycle before we flag it. A grace of 5 min covers slow API calls.
    stale_after_s = max(120, ingest_interval_minutes * 60 * 2 + 300)

    if not alive:
        status = "dead"
    elif age_seconds is not None and age_seconds > stale_after_s:
        status = "stale"
    else:
        status = "running"

    return {
        "status": status,
        "pid": pid,
        "started_at": hb.get("started_at"),
        "last_heartbeat_at": last_hb_str,
        "last_event": hb.get("last_event"),
        "age_seconds": age_seconds,
        "stale_threshold_seconds": stale_after_s,
    }
