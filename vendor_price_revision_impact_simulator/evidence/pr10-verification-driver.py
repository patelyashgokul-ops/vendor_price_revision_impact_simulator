"""Temporary local PR-10 verification driver; all databases are created here."""
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
LOGS = Path(r"C:\Users\Admin\.codex\visualizations\2026\10\28\01a1827f-30b8-78a1-8cfa-059a3def8980\pr10_logs")
CLUSTER = ROOT / ".pr10_pgdata"
MODULE = ROOT.name
PORT = "55441"
ROLE = "codex_vpr_pr10"
phase = sys.argv[1]
attempt = sys.argv[2] if len(sys.argv) > 2 else "1"
assert phase in {"fresh", "targeted", "upgrade", "upgrade_resume", "upgrade_verify", "preservation", "allocation", "helpers", "helpers_verify", "concurrency"}
assert attempt.isdecimal()
assert CLUSTER.resolve().parent == ROOT and CLUSTER.name == ".pr10_pgdata"
LOGS.mkdir(parents=True, exist_ok=True)


def run(command, **kwargs):
    return subprocess.run([str(arg) for arg in command], check=True, **kwargs)


def source_hash():
    names=['__manifest__.py','__init__.py']+[str(p.relative_to(ROOT)).replace('\\','/') for d in ('models','security','views','tests','data') for p in (ROOT/d).rglob('*') if p.is_file() and p.suffix in ('.py','.xml','.csv')]
    actual={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}
    return hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest()


def configure(database, baseline=False, action="update", mode="targeted", prepare_only=False):
    before_source_hash = source_hash()
    addon_parent = ROOT / ".pr10_baseline_addons" if baseline else ROOT.parent
    conf = ROOT / ".pr10_odoo.conf"
    conf.write_text(
        "[options]\n"
        f"addons_path = {ODOO / 'addons'},{addon_parent}\n"
        f"data_dir = {ROOT / '.pr10_odoo_data'}\n"
        f"db_host = 127.0.0.1\ndb_port = {PORT}\ndb_user = {ROLE}\n"
        "list_db = False\nmax_cron_threads = 0\nhttp_enable = False\nhttp_port = 8086\n"
        "server_wide_modules = base,web\nwithout_demo = True\n",
        encoding="utf-8",
    )
    if phase == "concurrency" or prepare_only:
        return
    selector = f"/{MODULE}:TestModuleFoundation" if baseline else f"/{MODULE}"
    if phase == "fresh":
        selector = ",".join(f"/{MODULE}:{name}" for name in ("TestModuleFoundation", "TestVendorPriceRevision", "TestRevisionSecurity", "TestCompanyConfiguration", "TestImportParser", "TestImportIntake", "TestImportSecurity", "TestImportDownload", "TestStructuralHelpers", "TestImportMapping", "TestImportValidation", "TestImportCorrections", "TestImportValidationSecurity", "TestProductExactMatching", "TestVendorProductRegistry", "TestProductResolutionFreshness", "TestProductResolutionSecurity", "TestCommercialMath", "TestCommercialNormalization", "TestCommercialFx", "TestVendorCommercialBaseline", "TestCommercialSnapshots", "TestCommercialSecurity", "TestSupplyQuantities", "TestSupplyReceipts", "TestSupplyIntegrity", "TestSupplySecurity", "TestAllocationHelpers", "TestConfirmedDemand", "TestAllocationReservations", "TestAllocationCapacity", "TestQuotationAllocation", "TestAllocationIntegrity", "TestAllocationSecurity", "TestAllocationWorkload"))
    if phase == "targeted":
        selector = ",".join(f"/{MODULE}:{name}" for name in ("TestCompanyConfiguration", "TestProductExactMatching", "TestVendorProductRegistry", "TestProductResolutionFreshness", "TestProductResolutionSecurity", "TestImportValidationSecurity", "TestImportSecurity", "TestImportDownload", "TestCommercialMath", "TestCommercialNormalization", "TestCommercialFx", "TestVendorCommercialBaseline", "TestCommercialSnapshots", "TestCommercialSecurity", "TestSupplyQuantities", "TestSupplyReceipts", "TestSupplyIntegrity", "TestSupplySecurity", "TestAllocationHelpers", "TestConfirmedDemand", "TestAllocationReservations", "TestAllocationCapacity", "TestQuotationAllocation", "TestAllocationIntegrity", "TestAllocationSecurity"))
    if phase == 'allocation':
        selector = ','.join(f'/{MODULE}:{name}' for name in ("TestAllocationHelpers", "TestConfirmedDemand", "TestAllocationReservations", "TestAllocationCapacity", "TestQuotationAllocation", "TestAllocationIntegrity", "TestAllocationSecurity"))
    if phase in ('helpers','helpers_verify'):selector=f'/{MODULE}:TestAllocationHelpers'
    config = {
        "prompt_id": "PR-10", "phase": "DEV-05", "python": sys.executable,
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
    path = ROOT / ".pr10_runner.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/run_tests.py"),
                             "--mode", mode, "--config", str(path)], check=False)
    report_path = ROOT / "TEST_REPORT.json"
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    latest = report["latest_run"]
    original_log = Path(latest["evidence_reference"]) if latest["evidence_reference"] else None
    if original_log and original_log.is_file():
        relative = f"evidence/pr10-{phase}-{'baseline' if baseline else action}-{original_log.name}"
        content = original_log.read_text(encoding="utf-8")
        (ROOT / relative).write_text(content, encoding="utf-8")
        for record in (latest, report["history"][-1]):
            record["evidence_reference"] = relative
            record["verification_scope"] = "PR09_BASELINE_PREPARATION" if baseline else f"PR10_{phase.upper()}"
            record["test_names"] = re.findall(r"Starting ([A-Za-z0-9_.]+) \.\.\.", content)
            record["source_hash"] = hashlib.sha256((ROOT/"evidence/pr09-source-baseline.zip").read_bytes()).hexdigest() if baseline else before_source_hash
            record["source_hash_kind"] = "PR08_baseline_archive_sha256" if baseline else "final_code_ledger_sha256"
            record["source_changed_during_run"] = before_source_hash != source_hash()
            record["environment"]["database_scope"] = "Created for this run in an isolated disposable loopback PostgreSQL 18.4 cluster"
        report["current_status"] = latest["result_status"]
        report["current_status_detail"] = f"PR-10 {phase}: {latest['result_status']}; verification still in progress."
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"{phase} runner failed: {latest['evidence_reference']}")

def shell_probe(file, scope, markers, baseline=False):
    started=datetime.now(timezone.utc).isoformat(timespec='seconds');working_hash=source_hash()
    before_hash=hashlib.sha256((ROOT/'evidence/pr09-source-baseline.zip').read_bytes()).hexdigest() if baseline else working_hash
    result=subprocess.run([sys.executable,str(ODOO/'odoo-bin'),'shell','-c',str(ROOT/'.pr10_odoo.conf'),'-d',database,'--no-http'],input=(ROOT/file).read_text(),capture_output=True,text=True)
    ref='evidence/pr10-'+scope+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.log'
    (ROOT/ref).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    ok=result.returncode==0 and all(m in result.stdout for m in markers)
    rp=ROOT/'TEST_REPORT.json';report=json.loads(rp.read_text())
    record=dict(prompt_id='PR-10',phase='DEV-05',odoo_version='20.0',module=MODULE,environment=dict(os='Windows',edition='Community',database=database,database_scope='Disposable allowlisted loopback cluster'),test_level='TARGETED',invocation='Odoo shell '+file,started_at=started,completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),exit_status=result.returncode,passed=len(markers) if ok else None,failed=0 if ok else None,skipped=0,result_status='PASS' if ok else 'FAIL',evidence_reference=ref,blocking_reason=None if ok else 'Probe assertion/marker failed',verification_scope='PR10_'+scope.upper(),probe_script_sha256=hashlib.sha256((ROOT/file).read_bytes()).hexdigest(),source_hash=before_hash,source_hash_kind='PR09_baseline_archive_sha256' if baseline else 'final_code_ledger_sha256',source_changed_during_run=working_hash!=source_hash(),test_unit='probe_assertion_groups')
    if scope in ('upgrade-seed','upgrade-cold-capture'):record.update(test_level='SETUP',passed=None,failed=None)
    report['history'].append(record);report['latest_run']=record;report['current_status']=record['result_status'];rp.write_text(json.dumps(report,indent=2)+'\n');assert ok,ref

import zipfile
if not (CLUSTER/'PG_VERSION').exists():run([PG/'initdb.exe','-D',CLUSTER,'-U',ROLE,'-A','trust','--encoding=UTF8','--locale=C'])
run([PG/'pg_ctl.exe','-D',CLUSTER,'-o',f'-h 127.0.0.1 -p {PORT}','-l',ROOT/'.pr10_postgres.log','-w','start'])
try:
    database=f'codex_vpr_pr10_{phase}_{attempt}_20261029'
    if phase in ('upgrade_resume','upgrade_verify','preservation'):
        database=f'codex_vpr_pr10_upgrade_{attempt}_20261029'
    elif phase in ('allocation','targeted','concurrency','helpers_verify'):
        database=json.loads((ROOT/'.pr10_state.json').read_text())['fresh']
    else:run([PG/'createdb.exe','-h','127.0.0.1','-p',PORT,'-U',ROLE,'-T','template0','-E','UTF8',database])
    if phase in ('fresh','helpers'):
        (ROOT/'.pr10_state.json').write_text(json.dumps({'fresh':database}))
        configure(database,action='install',mode='quick')
    elif phase in ('allocation','targeted'):configure(database,action='update',mode='targeted')
    elif phase=='helpers_verify':configure(database,action='update',mode='quick')
    elif phase=='concurrency':
        configure(database,prepare_only=True)
        shell_probe('evidence/pr10-concurrency-probe.py','concurrency',['PR10_CONCURRENT_'+name+'=PASS' for name in ('ALLOCATE','SO_QUANTITY','DELIVERY','RESERVATION','RECEIPT','PO_CANCEL','QUOTE_CONFIRM','GRANT')])
    elif phase in ('upgrade','upgrade_resume'):
        target=ROOT/'.pr10_baseline_addons'/MODULE;target.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(ROOT/'evidence/pr09-source-baseline.zip') as z:z.extractall(target)
        configure(database,baseline=True,action='install',mode='quick',prepare_only=phase=='upgrade_resume')
        if phase=='upgrade':
            started=datetime.now(timezone.utc).isoformat(timespec='seconds')
            result=subprocess.run([sys.executable,str(ODOO/'odoo-bin'),'-c',str(ROOT/'.pr10_odoo.conf'),'-d',database,'-i','sale_stock','--stop-after-init','--log-level=info'],capture_output=True,text=True)
            ref='evidence/pr10-upgrade-sales-setup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.log';(ROOT/ref).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
            ok=result.returncode==0 and 'Modules loaded.' in result.stderr
            rp=ROOT/'TEST_REPORT.json';report=json.loads(rp.read_text());record=dict(prompt_id='PR-10',phase='DEV-05',odoo_version='20.0',module=MODULE,environment=dict(database=database,edition='Community',database_scope='Disposable PR09 upgrade fixture'),test_level='SETUP',invocation='Install standard Community sale_stock under exact PR09 addon code; no tests claimed',started_at=started,completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),exit_status=result.returncode,result_status='PASS' if ok else 'FAIL',passed=None,failed=None,skipped=None,evidence_reference=ref,blocking_reason=None if ok else 'Sales integration fixture setup failed')
            report['history'].append(record);report['latest_run']=record;report['current_status']=record['result_status'];rp.write_text(json.dumps(report,indent=2)+'\n');assert ok,ref
        shell_probe('evidence/pr10-upgrade-seed.py','upgrade-seed',['PR10_PROBE=PASS'],baseline=True)
        shell_probe('evidence/pr10-upgrade-capture.py','upgrade-cold-capture',['PR10_CAPTURE=PASS'],baseline=True)
        configure(database,action='update',mode='milestone')
        shell_probe('evidence/pr10-upgrade-preservation.py','upgrade-preservation',['PR10_PROBE=PASS'])
        shell_probe('evidence/pr10-operational-safety-probe.py','operational-safety',['PR10_OPERATIONAL_SAFETY=PASS'])
    elif phase in ('upgrade_verify','preservation'):
        configure(database,prepare_only=phase=='preservation',action='update',mode='milestone')
        shell_probe('evidence/pr10-upgrade-preservation.py','upgrade-preservation',['PR10_PROBE=PASS'])
        if phase=='upgrade_verify':
            shell_probe('evidence/pr10-operational-safety-probe.py','operational-safety',['PR10_OPERATIONAL_SAFETY=PASS'])

finally:run([PG/'pg_ctl.exe','-D',CLUSTER,'-m','fast','-w','stop'])
