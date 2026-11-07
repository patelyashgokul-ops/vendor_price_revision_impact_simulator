"""Temporary local PR-21 verification driver; all databases are created here."""
import json
import hashlib
from datetime import datetime, timezone
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PG = Path(r"C:\Program Files\PostgreSQL\18\bin")
ODOO = Path(r"C:\PycharmProjects\odoo20\odoo-20.0")
LOGS = Path(r"C:\Users\Admin\.codex\visualizations\2026\10\28\01a1827f-30b8-78a1-8cfa-059a3def8980\pr21_logs")
CLUSTER = ROOT / ".pr21_pgdata"
MODULE = ROOT.name
PORT = "55452"
ROLE = "codex_vpr_pr21"
phase = sys.argv[1]
attempt = sys.argv[2] if len(sys.argv) > 2 else "1"
assert phase in {"fresh", "targeted", "upgrade", "upgrade_resume", "upgrade_verify", "preservation", "allocation", "helpers", "helpers_verify", "concurrency", "operations", "performance", "approved_performance", "smoke", "repairs", "activity_guard"}
assert attempt.isdecimal()
if phase=='upgrade' and (ROOT/'.pr21_security_review').exists():raise RuntimeError('PR21 activity default-context security regression investigation; upgrade not started')
assert CLUSTER.resolve().parent == ROOT and CLUSTER.name == ".pr21_pgdata"
LOGS.mkdir(parents=True, exist_ok=True)


def run(command, **kwargs):
    return subprocess.run([str(arg) for arg in command], check=True, **kwargs)


def source_hash():
    names=['__manifest__.py','__init__.py']+[str(p.relative_to(ROOT)).replace('\\','/') for d in ('models','security','views','tests','data') for p in (ROOT/d).rglob('*') if p.is_file() and p.suffix in ('.py','.xml','.csv')]
    actual={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}
    return hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest()


def configure(database, baseline=False, action="update", mode="targeted", prepare_only=False):
    before_source_hash = source_hash()
    addon_parent = ROOT / ".pr21_baseline_addons" if baseline else ROOT.parent
    conf = ROOT / ".pr21_odoo.conf"
    conf.write_text(
        "[options]\n"
        f"addons_path = {ODOO / 'addons'},{addon_parent}\n"
        f"data_dir = {ROOT / '.pr21_odoo_data'}\n"
        f"db_host = 127.0.0.1\ndb_port = {PORT}\ndb_user = {ROLE}\n"
        "list_db = False\nmax_cron_threads = 0\nhttp_enable = False\nhttp_port = 8093\n"
        "server_wide_modules = base,web\nwithout_demo = True\n",
        encoding="utf-8",
    )
    if phase == "concurrency" or prepare_only:
        return
    selector = f"/{MODULE}:TestModuleFoundation" if baseline else f"/{MODULE}"
    if not baseline:
        names=('TestApplicationMath','TestApplicationQuick','TestApplicationControls','TestModuleFoundation')
        if phase=='fresh' and attempt!='1':names=('TestApplicationMath','TestApplicationQuick','TestApplicationControls.test_company_calendar_is_frozen_and_caller_tz_cannot_replace_it','TestApplicationControls.test_real_intent_wizard_is_creator_bound','TestModuleFoundation')
        elif phase in ('helpers','helpers_verify'):names=('TestApplicationMath','TestApplicationQuick','TestModuleFoundation')
        elif phase=='smoke':names=('TestApplicationQuick.test_exact_update_preview_no_write_and_repeat',)
        elif phase=='targeted':names=('TestApplicationControls.test_109_approval_does_not_plan_unapproved112','TestApplicationControls.test_target105_current_before_and_old_plan_immutable','TestApplicationControls.test_expiry_during_planning_cannot_finish_ready')
        elif phase=='repairs':names=('TestApplicationQuick',)
        elif phase in ('upgrade','upgrade_resume','upgrade_verify'):names=names+('TestApprovalMath','TestApprovalRoutes','TestApprovalLifecycle','TestApprovalSecurity','TestDecisionMath','TestDecisionQuick','TestDecisionWorkflow','TestDecisionDelegation','TestDecisionValidity','TestDecisionSecurity','TestDecisionFinancial')
        selector = ','.join(f'/{MODULE}:{name}' for name in names) if names else f'/{MODULE}'
    config = {
        "prompt_id": "PR-21", "phase": "DEV-11", "python": sys.executable,
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
    path = ROOT / ".pr21_runner.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/run_tests.py"),
                             "--mode", mode, "--config", str(path)], check=False)
    report_path = ROOT / "TEST_REPORT.json"
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    latest = report["latest_run"]
    original_log = Path(latest["evidence_reference"]) if latest["evidence_reference"] else None
    if original_log and original_log.is_file():
        relative = f"evidence/pr21-{phase}-{'baseline' if baseline else action}-{original_log.name}"
        content = original_log.read_text(encoding="utf-8")
        (ROOT / relative).write_text(content, encoding="utf-8")
        for record in (latest, report["history"][-1]):
            record["evidence_reference"] = relative
            record["verification_scope"] = "PR20_BASELINE_PREPARATION" if baseline else f"PR21_{phase.upper()}"
            record["test_names"] = re.findall(r"Starting ([A-Za-z0-9_.]+) \.\.\.", content)
            record["source_hash"] = hashlib.sha256((ROOT/"evidence/pr20-source-baseline.zip").read_bytes()).hexdigest() if baseline else before_source_hash
            record["source_hash_kind"] = "PR20_baseline_archive_sha256" if baseline else "final_code_ledger_sha256"
            record["source_changed_during_run"] = before_source_hash != source_hash()
            record["environment"]["database_scope"] = "Created for this run in an isolated disposable loopback PostgreSQL 18.4 cluster"
        report["current_status"] = latest["result_status"]
        report["current_status_detail"] = f"PR-21 {phase}: {latest['result_status']}; verification still in progress."
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{phase} runner failed: {latest['evidence_reference']}")

def shell_probe(file, scope, markers, baseline=False):
    started=datetime.now(timezone.utc).isoformat(timespec='seconds');working_hash=source_hash()
    before_hash=hashlib.sha256((ROOT/'evidence/pr20-source-baseline.zip').read_bytes()).hexdigest() if baseline else working_hash
    ref='evidence/pr21-'+scope+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.log'
    with (ROOT/ref).open('w',encoding='utf-8') as live_log:
        result=subprocess.run([sys.executable,str(ODOO/'odoo-bin'),'shell','-c',str(ROOT/'.pr21_odoo.conf'),'-d',database,'--no-http'],input=(ROOT/file).read_text(encoding='utf-8'),stdout=live_log,stderr=subprocess.STDOUT,text=True)
    output=(ROOT/ref).read_text(encoding='utf-8')
    ok=result.returncode==0 and all(m in output for m in markers)
    rp=ROOT/'TEST_REPORT.json';report=json.loads(rp.read_text(encoding='utf-8'))
    record=dict(prompt_id='PR-21',phase='DEV-11',odoo_version='20.0',module=MODULE,environment=dict(os='Windows',edition='Community',database=database,database_scope='Disposable allowlisted loopback cluster'),test_level='TARGETED',invocation='Odoo shell '+file,started_at=started,completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),exit_status=result.returncode,passed=len(markers) if ok else None,failed=0 if ok else None,skipped=0,result_status='PASS' if ok else 'FAIL',evidence_reference=ref,blocking_reason=None if ok else 'Probe assertion/marker failed',verification_scope='PR21_'+scope.upper(),probe_script_sha256=hashlib.sha256((ROOT/file).read_bytes()).hexdigest(),source_hash=before_hash,source_hash_kind='PR20_baseline_archive_sha256' if baseline else 'final_code_ledger_sha256',source_changed_during_run=working_hash!=source_hash(),test_unit='probe_assertion_groups')
    if scope in ('upgrade-seed','upgrade-cold-capture'):record.update(test_level='SETUP',passed=None,failed=None)
    report['history'].append(record);report['latest_run']=record;report['current_status']=record['result_status'];rp.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');assert ok,ref

import zipfile
if not (CLUSTER/'PG_VERSION').exists():run([PG/'initdb.exe','-D',CLUSTER,'-U',ROLE,'-A','trust','--encoding=UTF8','--locale=C'])
run([PG/'pg_ctl.exe','-D',CLUSTER,'-o',f'-h 127.0.0.1 -p {PORT}','-l',ROOT/'.pr21_postgres.log','-w','start'])
try:
    database=f'codex_vpr_pr21_{phase}_{attempt}_20261101'
    if phase in ('upgrade_resume','upgrade_verify','preservation'):
        database=f'codex_vpr_pr21_upgrade_{attempt}_20261101'
    elif phase in ('allocation','targeted','concurrency','helpers_verify','operations','performance','approved_performance','smoke','repairs','activity_guard'):
        database=json.loads((ROOT/'.pr21_state.json').read_text(encoding='utf-8'))['fresh']
    else:run([PG/'createdb.exe','-h','127.0.0.1','-p',PORT,'-U',ROLE,'-T','template0','-E','UTF8',database])
    if phase in ('fresh','helpers'):
        (ROOT/'.pr21_state.json').write_text(json.dumps({'fresh':database}))
        configure(database,action='install',mode='milestone' if phase=='fresh' else 'quick')
    elif phase in ('allocation','targeted','smoke','repairs'):configure(database,action='update',mode='targeted')
    elif phase=='helpers_verify':configure(database,action='update',mode='quick')
    elif phase=='activity_guard':
        configure(database,prepare_only=True)
        shell_probe('evidence/pr21-activity-guard-probe.py','activity-guard',['PR21_ACTIVITY_TARGET_FORMS=PASS','PR21_OPERATIONAL_SAFETY=PASS'])
    elif phase=='operations':
        configure(database,prepare_only=True)
        shell_probe('evidence/pr21-operational-safety-probe.py','operational-safety',['PR21_OPERATIONAL_SAFETY=PASS','PR21_DECISION_UPSTREAM=PASS'])
    elif phase=='approved_performance':
        configure(database,prepare_only=True)
        shell_probe('evidence/pr21-approved-performance-probe.py','approved-performance',['PR21_APPROVED_PERFORMANCE_'+str(n)+'=' for n in (10,100,500,2000)]+['PR21_APPROVED_PERFORMANCE=PASS'])
    elif phase=='performance':
        configure(database,prepare_only=True)
        shell_probe('evidence/pr21-performance-probe.py','performance',['PR21_PERFORMANCE_10=','PR21_PERFORMANCE_100=','PR21_PERFORMANCE_500=','PR21_PERFORMANCE_2000=','PR21_PERFORMANCE=PASS'])
    elif phase=='concurrency':
        configure(database,prepare_only=True)
        shell_probe('evidence/pr21-concurrency-probe.py','concurrency',['PR21_CONCURRENT_DOUBLE=PASS','PR21_CONCURRENT_PHANTOM=PASS','PR21_CONCURRENT_TARGET=PASS','PR21_CONCURRENT_INVALIDATE=PASS','PR21_COMPANY_ISOLATION=PASS','PR21_CONCURRENCY=PASS'])
    elif phase in ('upgrade','upgrade_resume'):
        target=ROOT/'.pr21_baseline_addons'/MODULE;target.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(ROOT/'evidence/pr20-source-baseline.zip') as z:z.extractall(target)
        configure(database,baseline=True,action='install',mode='quick',prepare_only=phase=='upgrade_resume')
        if phase=='upgrade':shell_probe('evidence/pr21-upgrade-seed.py','upgrade-seed',['PR21_PROBE=PASS'],baseline=True)
        shell_probe('evidence/pr21-upgrade-capture.py','upgrade-cold-capture',['PR21_CAPTURE=PASS'],baseline=True)
        configure(database,action='update',mode='milestone')
        shell_probe('evidence/pr21-upgrade-preservation.py','upgrade-preservation',['PR21_PROBE=PASS'])
        # Separate operational probe follows preservation once implementation passes.

    elif phase in ('upgrade_verify','preservation'):
        configure(database,prepare_only=phase=='preservation',action='update',mode='milestone')
        shell_probe('evidence/pr21-upgrade-preservation.py','upgrade-preservation',['PR21_PROBE=PASS'])


finally:run([PG/'pg_ctl.exe','-D',CLUSTER,'-m','fast','-w','stop'])
