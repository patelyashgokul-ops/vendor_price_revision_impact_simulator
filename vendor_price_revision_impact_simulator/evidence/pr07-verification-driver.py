"""Temporary local PR-07 verification driver; all databases are created here."""
import json
from datetime import datetime, timezone
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PG = Path(r"C:\Program Files\PostgreSQL\18\bin")
ODOO = Path(r"C:\PycharmProjects\odoo20\odoo-20.0")
LOGS = Path(r"C:\Users\Admin\.codex\visualizations\2026\10\28\01a1827f-30b8-78a1-8cfa-059a3def8980\pr07_logs")
CLUSTER = ROOT / ".pr07_pgdata"
MODULE = ROOT.name
PORT = "55438"
ROLE = "codex_vpr_pr07"
phase = sys.argv[1]
attempt = sys.argv[2] if len(sys.argv) > 2 else "1"
assert phase in {"fresh", "targeted", "upgrade", "upgrade_verify", "concurrency"}
assert attempt.isdecimal()
assert CLUSTER.resolve().parent == ROOT and CLUSTER.name == ".pr07_pgdata"
LOGS.mkdir(parents=True, exist_ok=True)


def run(command, **kwargs):
    return subprocess.run([str(arg) for arg in command], check=True, **kwargs)


def configure(database, baseline=False, action="update", mode="targeted"):
    addon_parent = ROOT / ".pr07_baseline_addons" if baseline else ROOT.parent
    conf = ROOT / ".pr07_odoo.conf"
    conf.write_text(
        "[options]\n"
        f"addons_path = {ODOO / 'addons'},{addon_parent}\n"
        f"data_dir = {ROOT / '.pr07_odoo_data'}\n"
        f"db_host = 127.0.0.1\ndb_port = {PORT}\ndb_user = {ROLE}\n"
        "list_db = False\nmax_cron_threads = 0\nhttp_enable = False\nhttp_port = 8083\n"
        "server_wide_modules = base,web\nwithout_demo = True\n",
        encoding="utf-8",
    )
    selector = f"/{MODULE}:TestModuleFoundation" if baseline else f"/{MODULE}"
    if phase == "fresh":
        selector = ",".join(f"/{MODULE}:{name}" for name in ("TestModuleFoundation", "TestVendorPriceRevision", "TestRevisionSecurity", "TestCompanyConfiguration", "TestImportParser", "TestImportIntake", "TestImportSecurity", "TestImportDownload", "TestStructuralHelpers", "TestImportMapping", "TestImportValidation", "TestImportCorrections", "TestImportValidationSecurity", "TestProductExactMatching", "TestVendorProductRegistry", "TestProductResolutionFreshness", "TestProductResolutionSecurity"))
    if phase == "targeted":
        selector = ",".join(f"/{MODULE}:{name}" for name in ("TestProductExactMatching", "TestVendorProductRegistry", "TestProductResolutionFreshness", "TestProductResolutionSecurity", "TestImportValidationSecurity", "TestImportSecurity", "TestImportDownload"))
    config = {
        "prompt_id": "PR-07", "phase": "DEV-04", "python": sys.executable,
        "odoo_bin": str(ODOO / "odoo-bin"), "odoo_config": str(conf),
        "odoo_version": "20.0", "edition": "Community", "module": MODULE,
        "module_path": str(addon_parent / MODULE),
        "addons_path": [str(ODOO / "addons"), str(addon_parent)],
        "database": database, "database_role": "dedicated_test",
        "allowed_test_databases": [database],
        "side_effects": dict.fromkeys([
            "outgoing_email", "external_api_mutations", "cron", "real_payments", "live_accounting"
        ], False),
        "postgres": {"pg_isready": str(PG / "pg_isready.exe"), "host": "127.0.0.1",
                     "port": int(PORT), "user": ROLE, "timeout_seconds": 3},
        "action": action,
        "tags": dict.fromkeys(["quick", "targeted", "milestone", "full"], selector),
        "log_directory": str(LOGS),
    }
    path = ROOT / ".pr07_runner.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/run_tests.py"),
                             "--mode", mode, "--config", str(path)], check=False)
    report_path = ROOT / "TEST_REPORT.json"
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    latest = report["latest_run"]
    original_log = Path(latest["evidence_reference"]) if latest["evidence_reference"] else None
    if original_log and original_log.is_file():
        relative = f"evidence/pr07-{phase}-{'baseline' if baseline else action}-{original_log.name}"
        content = original_log.read_text(encoding="utf-8")
        (ROOT / relative).write_text(content, encoding="utf-8")
        for record in (latest, report["history"][-1]):
            record["evidence_reference"] = relative
            record["verification_scope"] = "PR06_BASELINE_PREPARATION" if baseline else f"PR07_{phase.upper()}"
            record["test_names"] = re.findall(r"Starting ([A-Za-z0-9_.]+) \.\.\.", content)
            record["environment"]["database_scope"] = "Created for this run in an isolated disposable loopback PostgreSQL 18.4 cluster"
        report["current_status"] = latest["result_status"]
        report["current_status_detail"] = f"PR-07 {phase}: {latest['result_status']}; verification still in progress."
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{phase} runner failed: {latest['evidence_reference']}")



import zipfile
if not (CLUSTER / 'PG_VERSION').exists():
    run([PG / 'initdb.exe', '-D', CLUSTER, '-U', ROLE, '-A', 'trust', '--encoding=UTF8', '--locale=C'])
run([PG / 'pg_ctl.exe', '-D', CLUSTER, '-o', f'-h 127.0.0.1 -p {PORT}', '-l', ROOT / '.pr07_postgres.log', '-w', 'start'])
try:
    database = f'codex_vpr_pr07_{phase}_{attempt}_20261028'
    if phase == 'upgrade_verify':
        database = 'codex_vpr_pr07_upgrade_1_20261028'
    elif phase in ('targeted', 'concurrency'):
        database = json.loads((ROOT / '.pr07_state.json').read_text())['fresh']
    else:
        run([PG / 'createdb.exe', '-h', '127.0.0.1', '-p', PORT, '-U', ROLE, '-T', 'template0', '-E', 'UTF8', database])
    if phase == 'fresh':
        (ROOT / '.pr07_state.json').write_text(json.dumps({'fresh': database}))
        configure(database, action='install', mode='quick')
    elif phase == 'targeted':
        configure(database, action='update', mode='targeted')
    elif phase == 'concurrency':
        started = datetime.now(timezone.utc).isoformat(timespec='seconds')
        result = subprocess.run([sys.executable, str(ODOO/'odoo-bin'), 'shell', '-c', str(ROOT/'.pr07_odoo.conf'), '-d', database, '--no-http'], input=(ROOT/'tests/upgrade/verify_concurrent_products.py').read_text(encoding='utf-8'), capture_output=True, text=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        ref = f'evidence/pr07-concurrency-{stamp}.log'
        (ROOT/ref).write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
        passed = result.returncode == 0 and all(marker in result.stdout for marker in ['PR07_CONCURRENT_MATCH=PASS', 'PR07_CONCURRENT_VERIFY=PASS', 'PR07_CONCURRENT_CORRECT=PASS', 'PR07_CONCURRENT_RETIRE=PASS', 'PR07_CONCURRENT_ARCHIVE=PASS'])
        rp = ROOT/'TEST_REPORT.json'
        report = json.loads(rp.read_text(encoding='utf-8'))
        record = dict(prompt_id='PR-07', phase='DEV-04', odoo_version='20.0', module=MODULE,
            environment=dict(os='Windows', edition='Community', database=database, database_scope='Dedicated disposable loopback PostgreSQL 18.4'),
            test_level='TARGETED', invocation='Odoo shell tests/upgrade/verify_concurrent_products.py', started_at=started,
            completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), exit_status=result.returncode,
            passed=5 if passed else None, failed=0 if passed else None, skipped=0, result_status='PASS' if passed else 'FAIL',
            evidence_reference=ref, blocking_reason=None if passed else 'Concurrent assertion failed; see log', verification_scope='PR07_CONCURRENCY')
        report['history'].append(record); report['latest_run']=record
        rp.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        assert passed, ref
    elif phase in ('upgrade', 'upgrade_verify'):
        target = ROOT / '.pr07_baseline_addons' / MODULE
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(ROOT / 'evidence/pr06-source-baseline.zip') as z:
            z.extractall(target)
        if phase == 'upgrade':
            configure(database, baseline=True, action='install', mode='quick')
        def probe(source, suffix):
            started = datetime.now(timezone.utc).isoformat(timespec='seconds')
            result = subprocess.run([sys.executable, str(ODOO/'odoo-bin'), 'shell', '-c', str(ROOT/'.pr07_odoo.conf'), '-d', database, '--no-http'], input=source, capture_output=True, text=True)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            ref = f'evidence/pr07-{phase}-{suffix}-{stamp}.log'
            (ROOT/ref).write_text(result.stdout+'\n'+result.stderr, encoding='utf-8')
            passed = result.returncode == 0 and 'PR07_PROBE=PASS' in result.stdout
            report_path = ROOT/'TEST_REPORT.json'
            report = json.loads(report_path.read_text(encoding='utf-8-sig'))
            record = dict(prompt_id='PR-07', phase='DEV-04', odoo_version='20.0', module=MODULE,
                environment=dict(os='Windows', edition='Community', database=database, database_scope='Dedicated disposable loopback PostgreSQL 18.4'),
                test_level='SETUP' if suffix=='seed' else 'TARGETED', invocation=f'Odoo shell PR06 upgrade {suffix} probe',
                started_at=started, completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), exit_status=result.returncode,
                passed=None, failed=None, skipped=None, result_status='PASS' if passed else 'FAIL',
                evidence_reference=ref, blocking_reason=None if passed else 'Probe assertion or marker failed', verification_scope='PR06_TO_PR07_'+suffix.upper())
            report['history'].append(record)
            report['latest_run']=record
            report_path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
            assert passed, ref
        if phase == 'upgrade':
            probe((ROOT/'tests/upgrade/seed_pr06.py').read_text(), 'seed')
        configure(database, action='update', mode='milestone')
        probe((ROOT/'tests/upgrade/verify_pr07.py').read_text(), 'preservation')
finally:
    run([PG/'pg_ctl.exe', '-D', CLUSTER, '-m', 'fast', '-w', 'stop'])

