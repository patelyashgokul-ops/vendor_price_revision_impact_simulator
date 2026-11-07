"""Owned synthetic PR24 PostgreSQL/Odoo checks; retain all databases."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import shutil
import zipfile
import re
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PG = Path(r'C:\Program Files\PostgreSQL\18\bin')
ODOO = Path(r'C:\PycharmProjects\odoo20\odoo-20.0')
CLUSTER = ROOT/'.pr24_pgdata'
PORT = '55455'
ROLE = 'codex_vpr_pr24'
MODULE = ROOT.name
phase = sys.argv[1]
attempt = sys.argv[2] if len(sys.argv) > 2 else '1'
assert phase in ('fresh', 'fresh_milestone', 'retry_install', 'quick', 'targeted', 'milestone', 'upgrade', 'upgrade_resume', 'final_upgrade') and attempt.isdecimal()
db = 'codex_vpr_pr24_'+('upgrade' if phase in ('upgrade', 'upgrade_resume', 'final_upgrade') else 'fresh')+'_'+attempt+'_20261103'
LOGS = Path(r'C:\Users\Admin\.codex\visualizations\2026\10\28\01a1827f-30b8-78a1-8cfa-059a3def8980\pr24_logs')
LOGS.mkdir(parents=True, exist_ok=True)


def run(args):
    return subprocess.run([str(a) for a in args], check=True)


def source():
    names = ['__init__.py', '__manifest__.py'] + [str(p.relative_to(ROOT)).replace('\\', '/') for folder in ('models', 'security', 'views', 'data', 'tests') for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.py', '.xml', '.csv')]
    ledger = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(names)}
    return hashlib.sha256(json.dumps(ledger, sort_keys=True).encode()).hexdigest()


def probe(conf, name):
    path = ROOT/name
    logfile = LOGS/('pr24-'+path.stem+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.log')
    before = source()
    started = datetime.now(timezone.utc).isoformat()
    with logfile.open('w', encoding='utf-8') as output:
        result = subprocess.run([sys.executable, str(ODOO/'odoo-bin'), 'shell', '-c', str(conf), '-d', db, '--no-http'],
            input=path.read_text(encoding='utf-8'), text=True, stdout=output, stderr=subprocess.STDOUT)
    content = logfile.read_text(encoding='utf-8')
    cases = re.findall(r'^PR24_CASE ([A-Z0-9_]+)=PASS', content, re.M)
    passed = result.returncode == 0 and 'PR24_PROBE=PASS' in content and bool(cases)
    path = ROOT/'TEST_REPORT.json'
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    baseline = conf.name == '.pr24_baseline.conf'
    record = dict(prompt_id='PR-24', phase='DEV-12', odoo_version='20.0', module=MODULE, test_level='TARGETED',
        verification_scope=Path(name).stem+('_COLD_PR23' if baseline else '_PR24'),
        environment=dict(database=db, edition='Community', database_role='dedicated_test'),
        invocation='Odoo shell '+name, started_at=started, completed_at=datetime.now(timezone.utc).isoformat(),
        exit_status=result.returncode, result_status='PASS' if passed else 'FAIL', test_unit='assertion_groups',
        passed=len(cases) if passed else None, failed=0 if passed else None, skipped=None, test_names=cases,
        source_hash=report['pr24_handoff']['prior_source_hash'] if baseline else before,
        source_changed_during_run=before != source(), evidence_reference=str(logfile),
        evidence_sha256=hashlib.sha256(logfile.read_bytes()).hexdigest(),
        blocking_reason=None if passed else 'Probe assertion or nonzero completion evidence missing')
    report['latest_run'] = record
    report['history'].append(record)
    report['current_status'] = record['result_status']
    path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    assert passed, str(logfile)
    print('PROBE PASS '+str(logfile), flush=True)


assert CLUSTER.resolve().parent == ROOT
if not (CLUSTER/'PG_VERSION').exists():
    run([PG/'initdb.exe', '-D', CLUSTER, '-U', ROLE, '-A', 'trust', '--encoding=UTF8', '--locale=C'])
run([PG/'pg_ctl.exe', '-D', CLUSTER, '-o', f'-h 127.0.0.1 -p {PORT}', '-l', ROOT/'.pr24_postgres.log', '-w', 'start'])
try:
    if phase in ('fresh', 'fresh_milestone', 'upgrade'):
        run([PG/'createdb.exe', '-h', '127.0.0.1', '-p', PORT, '-U', ROLE, '-T', 'template0', '-E', 'UTF8', db])
    conf = ROOT/'.pr24_odoo.conf'
    conf.write_text('[options]\n'+f'addons_path = {ODOO/"addons"},{ROOT.parent}\ndata_dir = {ROOT/".pr24_odoo_data"}\ndb_host = 127.0.0.1\ndb_port = {PORT}\ndb_user = {ROLE}\n'+
        'list_db = False\nmax_cron_threads = 0\nhttp_enable = False\nserver_wide_modules = base,web\nwithout_demo = True\nbin_path = C:\\Program Files\\wkhtmltopdf\\bin\n', encoding='utf-8')
    if phase in ('upgrade', 'upgrade_resume'):
        assert attempt == '1'
        if phase == 'upgrade':
            old = ROOT/'.pr23_pgdata'
            source_db = 'codex_vpr_pr23_upgrade_4_20261102'
            run([PG/'pg_ctl.exe', '-D', old, '-o', '-h 127.0.0.1 -p 55454', '-l', ROOT/'.pr23_postgres.log', '-w', 'start'])
            try:
                dump = ROOT/'.pr24-pr23-synthetic.dump'
                run([PG/'pg_dump.exe', '-h', '127.0.0.1', '-p', '55454', '-U', 'codex_vpr_pr23', '--no-owner', '--no-privileges', '-Fc', '-f', dump, source_db])
            finally:
                run([PG/'pg_ctl.exe', '-D', old, '-m', 'fast', '-w', 'stop'])
            run([PG/'pg_restore.exe', '-h', '127.0.0.1', '-p', PORT, '-U', ROLE, '--no-owner', '--no-privileges', '-d', db, dump])
            source_files = ROOT/'.pr23_odoo_data/filestore'/source_db
            destination = ROOT/'.pr24_odoo_data/filestore'/db
            assert source_files.resolve().is_relative_to(ROOT) and source_files.is_dir()
            assert destination.resolve().is_relative_to(ROOT/'.pr24_odoo_data/filestore')
            for file in source_files.rglob('*'):
                if not file.is_file():
                    continue
                assert not file.is_symlink() and file.resolve().is_relative_to(source_files.resolve())
                target = destination/file.relative_to(source_files)
                assert target.resolve().is_relative_to(destination.resolve())
                if target.exists():
                    assert target.read_bytes() == file.read_bytes()
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(file, target)
                assert hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(file.read_bytes()).digest()
        baseline_parent = ROOT/'.pr24_baseline_addons'
        baseline = baseline_parent/MODULE
        baseline.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(ROOT/'evidence/pr23-source-baseline.zip') as archive:
            for name in archive.namelist():
                assert (baseline/name).resolve().is_relative_to(baseline.resolve())
            archive.extractall(baseline)
        baseline_conf = ROOT/'.pr24_baseline.conf'
        baseline_conf.write_text(conf.read_text(encoding='utf-8').replace('addons_path = '+str(ODOO/'addons')+','+str(ROOT.parent), 'addons_path = '+str(ODOO/'addons')+','+str(baseline_parent)), encoding='utf-8')
        probe(baseline_conf, 'evidence/pr24-preservation-probe.py')
    names = ['TestReportingQuick']
    if phase in ('fresh', 'fresh_milestone', 'retry_install'):
        names += ['TestModuleFoundation', 'TestReportingSources']
    if phase in ('targeted', 'milestone'):
        names += ['TestReportingSources']
    if phase == 'milestone':
        names += ['TestModuleFoundation', 'TestProfitabilityMath', 'TestFinancialMath', 'TestMonitorMath', 'TestExecutionQuick', 'TestDecisionQuick', 'TestApplicationQuick']
    if phase == 'fresh_milestone':
        names += ['TestProfitabilityMath', 'TestFinancialMath', 'TestMonitorMath']
    selector = ','.join('/'+MODULE+':'+name for name in names)
    level = 'milestone' if phase == 'fresh_milestone' else phase if phase in ('quick', 'targeted', 'milestone') else 'quick'
    config = dict(prompt_id='PR-24', phase='DEV-12', python=sys.executable, odoo_bin=str(ODOO/'odoo-bin'), odoo_config=str(conf),
        odoo_version='20.0', edition='Community', module=MODULE, module_path=str(ROOT), addons_path=[str(ODOO/'addons'), str(ROOT.parent)],
        database=db, database_role='dedicated_test', allowed_test_databases=[db], side_effects=dict.fromkeys(['outgoing_email', 'external_api_mutations', 'cron', 'real_payments', 'live_accounting'], False),
        postgres=dict(pg_isready=str(PG/'pg_isready.exe'), host='127.0.0.1', port=int(PORT), user=ROLE, timeout_seconds=3),
        action='install' if phase in ('fresh', 'fresh_milestone', 'retry_install') else 'update', tags=dict.fromkeys(['quick', 'targeted', 'milestone', 'full'], selector), log_directory=str(LOGS))
    path = ROOT/'.pr24_runner.json'
    path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    before = source()
    result = subprocess.run([sys.executable, str(ROOT/'scripts/run_tests.py'), '--mode', level, '--config', str(path)])
    path = ROOT/'TEST_REPORT.json'
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    for record in (report['latest_run'], report['history'][-1]):
        record.update(verification_scope='PR24_'+phase.upper(), source_hash=before, source_changed_during_run=before != source())
    report['pr24_handoff'].update(status='IN_PROGRESS', runtime_tests=report['latest_run']['result_status'])
    path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    if result.returncode:
        raise RuntimeError('PR24 test failed; retained evidence in TEST_REPORT.json')
    if phase in ('upgrade', 'upgrade_resume', 'final_upgrade'):
        probe(conf, 'evidence/pr24-preservation-probe.py')
        probe(conf, 'evidence/pr24-output-probe.py')
        probe(conf, 'evidence/pr24-preservation-probe.py')
finally:
    run([PG/'pg_ctl.exe', '-D', CLUSTER, '-m', 'fast', '-w', 'stop'])
