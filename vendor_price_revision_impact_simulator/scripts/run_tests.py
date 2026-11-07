#!/usr/bin/env python3
"""Safely run a configured Odoo addon test selection and append honest evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "TEST_REPORT.json"
MODES = ("quick", "targeted", "milestone", "full")
SUMMARY_RE = re.compile(
    r"(?P<failed>\d+)\s+failed,\s+(?P<errors>\d+)\s+error\(s\)\s+of\s+(?P<total>\d+)\s+tests",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"^[A-Za-z0-9_./,:*+\- ]+$")
MODULE_RE = re.compile(r"^[A-Za-z0-9_]+$")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run one configured Odoo test selection after database safety checks.",
        epilog=(
            "Requires a local JSON config, dedicated_test database role, exact allowlist match, "
            "pg_isready, a module manifest and at least one Python test file."
        ),
    )
    result.add_argument("--mode", choices=MODES, required=True, help="test level to run")
    result.add_argument("--config", type=Path, required=True, help="private local runner JSON config")
    result.add_argument("--timeout", type=int, default=7200, help="maximum Odoo runtime in seconds (default: 7200)")
    return result


def read_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid JSON configuration: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Configuration root must be a JSON object")
    return data


def require_path(config: dict[str, Any], key: str, label: str, *, executable: bool = False) -> Path:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip() or value.startswith("<"):
        raise ValueError(f"{label} must be an explicitly configured absolute path")
    path = Path(value).expanduser().resolve()
    if not path.is_absolute() or not path.exists() or not path.is_file():
        raise ValueError(f"{label} does not exist as a file: {path}")
    if executable and os.name != "nt" and not os.access(path, os.X_OK):
        raise ValueError(f"{label} is not executable: {path}")
    return path


def validate(config: dict[str, Any], mode: str) -> tuple[list[str], Path, Path, str, str, dict[str, Any]]:
    prompt_id = config.get("prompt_id", "PR-00")
    if not isinstance(prompt_id, str) or not re.fullmatch(r"PR-\d{2}", prompt_id):
        raise ValueError("prompt_id must identify the active prompt, for example PR-01")
    phase = config.get("phase", "DEV-00" if prompt_id == "PR-00" else None)
    if not isinstance(phase, str) or not re.fullmatch(r"DEV-\d{2}", phase):
        raise ValueError("phase must identify the active development phase, for example DEV-01")
    if config.get("edition") != "Community":
        raise ValueError("edition must explicitly be Community")
    version = config.get("odoo_version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+", version):
        raise ValueError("odoo_version must be explicitly configured as MAJOR.MINOR")

    module = config.get("module")
    if not isinstance(module, str) or not MODULE_RE.fullmatch(module):
        raise ValueError("module must be an actual technical addon name")
    module_path_value = config.get("module_path")
    if not isinstance(module_path_value, str) or not module_path_value.strip() or module_path_value.startswith("<"):
        raise ValueError("module_path must be explicitly configured")
    module_path = Path(module_path_value).expanduser().resolve()
    if not module_path.is_dir():
        raise ValueError(f"Addon directory does not exist: {module_path}")
    if not any((module_path / name).is_file() for name in ("__manifest__.py", "__openerp__.py")):
        raise ValueError("Addon manifest is missing")
    tests_dir = module_path / "tests"
    test_files = sorted(tests_dir.glob("test_*.py")) if tests_dir.is_dir() else []
    if not test_files:
        raise LookupError(f"No tests discovered in {tests_dir}")

    database = config.get("database")
    allowlist = config.get("allowed_test_databases")
    if config.get("database_role") != "dedicated_test":
        raise ValueError("database_role must be explicitly attested as dedicated_test")
    side_effects = config.get("side_effects")
    required_disabled = ("outgoing_email", "external_api_mutations", "cron", "real_payments", "live_accounting")
    if not isinstance(side_effects, dict) or any(side_effects.get(key) is not False for key in required_disabled):
        raise ValueError("side_effects must explicitly disable outgoing_email, external_api_mutations, cron, real_payments, and live_accounting")
    if not isinstance(database, str) or not database.strip() or database.startswith("<"):
        raise ValueError("database must be explicitly configured")
    if not isinstance(allowlist, list) or not allowlist or database not in allowlist:
        raise ValueError("database must exactly match an entry in allowed_test_databases")
    if any(not isinstance(name, str) or not name.strip() or name.startswith("<") for name in allowlist):
        raise ValueError("allowed_test_databases must contain explicit database names only")

    action = config.get("action")
    if action not in ("install", "update"):
        raise ValueError("action must be explicitly set to install or update")
    tags_map = config.get("tags")
    tags = tags_map.get(mode) if isinstance(tags_map, dict) else None
    if not isinstance(tags, str) or not tags.strip() or tags.startswith("<") or not TAG_RE.fullmatch(tags):
        raise ValueError(f"A verified tag expression for mode {mode!r} is required")

    python = require_path(config, "python", "Python interpreter")
    odoo_bin = require_path(config, "odoo_bin", "odoo-bin")
    odoo_config = require_path(config, "odoo_config", "Odoo config")

    postgres = config.get("postgres")
    if not isinstance(postgres, dict):
        raise ValueError("postgres connection details must be explicit")
    host = postgres.get("host")
    user = postgres.get("user")
    port = postgres.get("port")
    timeout = postgres.get("timeout_seconds", 3)
    if not isinstance(host, str) or not host.strip() or not isinstance(user, str) or not user.strip():
        raise ValueError("PostgreSQL host and test role must be explicit")
    if not isinstance(port, int) or not 1 <= port <= 65535 or not isinstance(timeout, int) or not 1 <= timeout <= 30:
        raise ValueError("PostgreSQL port/timeout are invalid")
    addons = config.get("addons_path")
    if not isinstance(addons, list) or not addons:
        raise ValueError("addons_path must list the verified Odoo addon paths")
    for addon in addons:
        if not isinstance(addon, str) or not Path(addon).expanduser().is_dir():
            raise ValueError(f"Invalid or unavailable addon path: {addon}")
    log_dir_value = config.get("log_directory")
    if not isinstance(log_dir_value, str) or not log_dir_value.strip() or log_dir_value.startswith("<"):
        raise ValueError("log_directory must be explicitly configured outside the source repository")
    log_dir = Path(log_dir_value).expanduser().resolve()
    if log_dir == ROOT or ROOT in log_dir.parents:
        raise ValueError("log_directory must be outside the project source tree")
    return [str(python), str(odoo_bin)], odoo_config, module_path, module, database, {
        "action": action, "tags": tags, "postgres": postgres, "version": version,
        "log_dir": log_dir, "test_files": test_files, "prompt_id": prompt_id, "phase": phase,
    }


def check_postgres(database: str, postgres: dict[str, Any]) -> str | None:
    configured_utility = postgres.get("pg_isready")
    if configured_utility is not None:
        utility_path = Path(str(configured_utility)).expanduser().resolve()
        utility = str(utility_path) if utility_path.is_file() else None
    else:
        utility = shutil.which("pg_isready")
    if utility is None:
        return "pg_isready is unavailable at the configured path or on PATH; PostgreSQL readiness cannot be verified"
    command = [
        utility, "-h", str(postgres["host"]), "-p", str(postgres["port"]),
        "-U", str(postgres["user"]), "-d", database, "-t", str(postgres.get("timeout_seconds", 3)),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=35, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"PostgreSQL readiness check could not complete: {exc.__class__.__name__}"
    if result.returncode != 0:
        return "PostgreSQL did not report the configured dedicated test database as ready"
    return None


def detect_version(command: list[str]) -> tuple[str | None, str | None]:
    try:
        result = subprocess.run(command + ["--version"], capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"Could not query Odoo version: {exc.__class__.__name__}"
    output = (result.stdout + "\n" + result.stderr).strip()
    match = re.search(r"\b(\d+\.\d+)\b", output)
    if result.returncode != 0 or not match:
        return None, "Odoo version could not be verified from odoo-bin --version"
    return match.group(1), None


def initial_report() -> dict[str, Any]:
    if REPORT_PATH.exists():
        try:
            report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            if isinstance(report, dict) and isinstance(report.get("history"), list):
                return report
        except (OSError, json.JSONDecodeError):
            pass
    return {"schema_version": 1, "latest_run": None, "history": []}


def record(run: dict[str, Any]) -> None:
    report = initial_report()
    report["schema_version"] = 1
    report["latest_run"] = run
    report["history"].append(run)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    args = parser().parse_args()
    started = now()
    run: dict[str, Any] = {
        "prompt_id": "PR-00", "environment": {"os": os.name, "platform": sys.platform},
        "odoo_version": None, "module": None, "test_level": args.mode.upper(),
        "invocation": "python scripts/run_tests.py --mode <mode> --config <private-config>",
        "started_at": started, "completed_at": None, "exit_status": None,
        "passed": None, "failed": None, "skipped": None, "result_status": "BLOCKED",
        "evidence_reference": None, "blocking_reason": None,
    }
    command: list[str] | None = None
    try:
        config = read_config(args.config)
        run["module"] = config.get("module")
        command, odoo_config, _module_path, module, database, settings = validate(config, args.mode)
        run["prompt_id"] = settings["prompt_id"]
        run["phase"] = settings["phase"]
        run["module_action"] = settings["action"]
        run["invocation"] = f"python scripts/run_tests.py --mode {args.mode} --config <private-config> ({settings['action']} {module})"
        run["odoo_version"] = settings["version"]
        run["environment"].update({"database": database, "edition": config.get("edition")})
        postgres_problem = check_postgres(database, settings["postgres"])
        if postgres_problem:
            run["blocking_reason"] = postgres_problem
        else:
            actual_version, version_problem = detect_version(command)
            if version_problem:
                run["blocking_reason"] = version_problem
            elif actual_version != settings["version"]:
                run["blocking_reason"] = f"Configured Odoo {settings['version']} does not match executable version {actual_version}"
                run["odoo_version"] = actual_version
            else:
                settings["log_dir"].mkdir(parents=True, exist_ok=True)
                logfile = settings["log_dir"] / f"{started.replace(':', '').replace('-', '')}_{args.mode}.log"
                flags = "-i" if settings["action"] == "install" else "-u"
                odoo_command = command + [
                    "-c", str(odoo_config), "-d", database, flags, module,
                    "--test-tags", settings["tags"], "--stop-after-init", "--log-level=test",
                ]
                run["evidence_reference"] = str(logfile)
                try:
                    completed = subprocess.run(
                        odoo_command, capture_output=True, text=True, timeout=args.timeout, check=False,
                    )
                    output = completed.stdout + "\n" + completed.stderr
                    logfile.write_text(output, encoding="utf-8", errors="replace")
                    run["exit_status"] = completed.returncode
                    summaries = list(SUMMARY_RE.finditer(output))
                    if summaries:
                        summary = summaries[-1]
                        run["failed"] = int(summary.group("failed")) + int(summary.group("errors"))
                        run["passed"] = max(0, int(summary.group("total")) - run["failed"])
                        run["skipped"] = None
                    if completed.returncode != 0:
                        run["result_status"] = "FAIL"
                        run["blocking_reason"] = "Odoo test command returned a nonzero exit status"
                    elif not summaries or int(summaries[-1].group("total")) == 0:
                        run["result_status"] = "BLOCKED"
                        run["blocking_reason"] = "Odoo exited successfully but a nonzero executed-test summary was not verified"
                    elif run["failed"]:
                        run["result_status"] = "FAIL"
                        run["blocking_reason"] = "Odoo reported failed or errored tests"
                    else:
                        run["result_status"] = "PASS"
                except subprocess.TimeoutExpired as exc:
                    captured = (exc.stdout or b"") + (exc.stderr or b"")
                    if isinstance(captured, bytes):
                        captured = captured.decode("utf-8", errors="replace")
                    logfile.write_text(captured, encoding="utf-8", errors="replace")
                    run["result_status"] = "FAIL"
                    run["blocking_reason"] = f"Odoo test execution exceeded timeout of {args.timeout} seconds"
                except OSError as exc:
                    run["result_status"] = "BLOCKED"
                    run["blocking_reason"] = f"Odoo process could not start: {exc.__class__.__name__}"
    except LookupError as exc:
        run["result_status"] = "NO_TESTS"
        run["blocking_reason"] = str(exc)
    except (ValueError, OSError) as exc:
        run["result_status"] = "BLOCKED"
        run["blocking_reason"] = str(exc)

    run["completed_at"] = now()
    try:
        record(run)
    except OSError as exc:
        print(f"Could not update {REPORT_PATH}: {exc}", file=sys.stderr)
        return 6
    print(f"{run['result_status']}: {run['blocking_reason'] or run['evidence_reference'] or 'verified'}")
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2, "NO_TESTS": 3, "NOT_RUN": 4}.get(run["result_status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
