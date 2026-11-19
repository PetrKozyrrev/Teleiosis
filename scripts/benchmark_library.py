"""Bounded local pilot baseline on a migrated disposable PostgreSQL database.

Requires APP_ENV=dev and a database name starting teleiosis_pilot_test_.
Starts its own loopback API, seeds fictional accounts, and cleans them up.
Never targets a supplied HTTP origin or staging.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import socket
import sys
from threading import Thread
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
import uvicorn

from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Content, User
from app.sessions import create_session


def bounded(low, high):
    def parse(value):
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"Value must be between {low} and {high}")
        return number
    return parse


def percentile(values, fraction):
    return round(sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)], 2)


def check_target():
    database = make_url(settings.database_url).database or ""
    if settings.app_env != "dev" or not database.startswith("teleiosis_pilot_test_"):
        raise SystemExit("Refusing target: APP_ENV=dev and teleiosis_pilot_test_ database required")
    if settings.push_enabled or settings.email_backend != "console":
        raise SystemExit("Refusing target: push must be disabled and email backend must be console")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", type=bounded(2, 20), default=5)
    parser.add_argument("--materials", type=bounded(20, 5000), default=200)
    parser.add_argument("--requests", type=bounded(20, 10000), default=300)
    parser.add_argument("--workers", type=bounded(1, 20), default=5)
    parser.add_argument("--max-p95-ms", type=bounded(1, 60000), default=2000)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    check_target()
    owners = []
    accounts = []
    server = None
    thread = None
    listener = socket.socket()
    try:
        with SessionLocal() as db:
            if db.scalar(select(func.count()).select_from(User)):
                raise SystemExit("Refusing target: disposable database must contain no accounts")
            for index in range(args.accounts):
                user = User(email=f"pilot-{uuid4().hex}@example.com", reminders_enabled=False)
                db.add(user)
                db.flush()
                owners.append(user.id)
                rows = [Content(user_id=user.id, title=f"Pilot material {item:05}", note="Fictional pilot fixture")
                        for item in range(args.materials)]
                db.add_all(rows)
                db.flush()
                token, _ = create_session(db, user, client_type="mobile")
                accounts.append((token, {row.id for row in rows}))
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False, log_level="critical"))
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        deadline = monotonic() + 10
        while not server.started and thread.is_alive() and monotonic() < deadline:
            sleep(0.02)
        if not server.started:
            raise RuntimeError("Local API failed to start")

        def request(index):
            token, owned = accounts[index % len(accounts)]
            mode = (index // len(accounts)) % 4
            if mode == 0:
                path, expected = "/contents?limit=20&sort=newest", 200
            elif mode == 1:
                path, expected = "/contents?q=Pilot&sort=title&limit=20&offset=10", 200
            elif mode == 2:
                path, expected = "/contents?q=missing-search-phrase&limit=20", 200
            else:
                other_ids = accounts[(index + 1) % len(accounts)][1]
                path, expected = f"/contents/{min(other_ids)}", 404
            started = monotonic()
            try:
                # A fresh local connection per request, no environment proxy.
                opener = build_opener(ProxyHandler({}))
                try:
                    response = opener.open(Request(origin + path, headers={"Authorization": "Bearer " + token}), timeout=10)
                except HTTPError as error:
                    response = error
                with response:
                    status = response.code
                    data = json.loads(response.read())
                valid = status == expected
                if expected == 200:
                    total = 0 if mode == 2 else args.materials
                    expected_items = 0 if mode == 2 else min(20, args.materials - (10 if mode == 1 else 0))
                    valid = valid and data["total"] == total and len(data["items"]) == expected_items
                    valid = valid and all(item["id"] in owned for item in data["items"])
            except Exception:
                # Exception and response text can contain credentials or data.
                valid = False
            return ((monotonic() - started) * 1000, valid)

        # Warm each scenario/account once; include failures in the final result.
        warmup = [request(index) for index in range(args.accounts * 4)]
        started = monotonic()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(request, range(args.requests)))
        elapsed = monotonic() - started
        latencies = [latency for latency, _ in results]
        failures = sum(not valid for _, valid in results)
        warmup_failures = sum(not valid for _, valid in warmup)
        p95 = percentile(latencies, 0.95)
        result = {
            "report_version": 1, "measured_at": datetime.now(timezone.utc).isoformat(),
            "scope": "disposable PostgreSQL + single loopback API, read requests only",
            "accounts": args.accounts, "materials_per_account": args.materials,
            "requests": args.requests, "workers": args.workers, "warmup_requests": len(warmup),
            "failures": failures, "warmup_failures": warmup_failures,
            "elapsed_seconds": round(elapsed, 3), "requests_per_second": round(args.requests / elapsed, 2),
            "latency_ms": {"p50": percentile(latencies, 0.5), "p95": p95,
                           "p99": percentile(latencies, 0.99), "max": round(max(latencies), 2)},
            "max_p95_ms": args.max_p95_ms, "passed": failures == warmup_failures == 0 and p95 <= args.max_p95_ms,
            "python": platform.python_version(), "logical_cpus": os.cpu_count(),
            "limitations": ["Not staging capacity or an SLA", "No HTTPS/proxy/mobile radio",
                            "No metadata fetching, writes, email, push or device runtime"],
        }
    finally:
        if server:
            server.should_exit = True
        if thread:
            thread.join(timeout=15)
        listener.close()
        if owners:
            with SessionLocal() as db:
                db.execute(delete(User).where(User.id.in_(owners)))
                db.commit()
                if db.scalar(select(func.count()).select_from(User).where(User.id.in_(owners))):
                    raise RuntimeError("Synthetic fixture cleanup incomplete")
    result["fixture_cleanup"] = True
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        raise SystemExit("Pilot benchmark failed. Check the isolated database and local API; no credentials logged.") from None
