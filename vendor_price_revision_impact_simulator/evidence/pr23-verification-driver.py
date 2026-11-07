"""Dedicated synthetic PR23 runtime; retain every database and stopped cluster."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
PG=Path(r'C:\Program Files\PostgreSQL\18\bin')
ODOO=Path(r'C:\PycharmProjects\odoo20\odoo-20.0')
CLUSTER=ROOT/'.pr23_pgdata'; PORT='55454'; ROLE='codex_vpr_pr23'; MODULE=ROOT.name
phase=sys.argv[1]; attempt=sys.argv[2] if len(sys.argv)>2 else '1'
assert attempt.isdecimal() and phase in ('fresh','quick','targeted','milestone','upgrade','clone_upgrade','capture','seed','probe','security','successor','superseded_dedup','concurrency','performance','preservation','filestore')
LOGS=Path(r'C:\Users\Admin\.codex\visualizations\2026\10\28\01a1827f-30b8-78a1-8cfa-059a3def8980\pr23_logs')
LOGS.mkdir(parents=True,exist_ok=True)
kind=sys.argv[3] if len(sys.argv)>3 else ('upgrade' if phase in ('upgrade','clone_upgrade','preservation') else 'fresh')
assert kind in ('fresh','upgrade')
db='codex_vpr_pr23_'+kind+'_'+attempt+'_20261102'
def run(args,**kwargs):return subprocess.run([str(a) for a in args],check=True,**kwargs)
def source():
 names=['__init__.py','__manifest__.py']+[str(p.relative_to(ROOT)).replace('\\','/') for d in ('models','security','views','data','tests') for p in (ROOT/d).rglob('*') if p.is_file() and p.suffix in ('.py','.xml','.csv')]
 files={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}
 return hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
def configure(baseline=False):
 parent=ROOT/'.pr23_baseline_addons' if baseline else ROOT.parent
 conf=ROOT/'.pr23_odoo.conf'
 conf.write_text('[options]\n'+f'addons_path = {ODOO/"addons"},{parent}\ndata_dir = {ROOT/".pr23_odoo_data"}\ndb_host = 127.0.0.1\ndb_port = {PORT}\ndb_user = {ROLE}\n'+
 'list_db = False\nmax_cron_threads = 0\nhttp_enable = False\nserver_wide_modules = base,web\nwithout_demo = True\n',encoding='utf-8')
 return parent,conf
def tests(action='update',baseline=False):
 parent,conf=configure(baseline)
 names=['TestModuleFoundation'] if baseline else ['TestModuleFoundation','TestMonitorMath','TestMonitorPending']
 if phase=='milestone':names+=['TestExecutionQuick','TestExecutionControls','TestApplicationQuick','TestDecisionQuick','TestDecisionValidity','TestDecisionSecurity']
 selector=','.join('/'+MODULE+':'+n for n in names)
 level='milestone' if phase=='milestone' else 'quick'
 config=dict(prompt_id='PR-23',phase='DEV-12',python=sys.executable,odoo_bin=str(ODOO/'odoo-bin'),odoo_config=str(conf),
  odoo_version='20.0',edition='Community',module=MODULE,module_path=str(parent/MODULE),addons_path=[str(ODOO/'addons'),str(parent)],
  database=db,database_role='dedicated_test',allowed_test_databases=[db],side_effects=dict.fromkeys(['outgoing_email','external_api_mutations','cron','real_payments','live_accounting'],False),
  postgres=dict(pg_isready=str(PG/'pg_isready.exe'),host='127.0.0.1',port=int(PORT),user=ROLE,timeout_seconds=3),action=action,
  tags=dict.fromkeys(['quick','targeted','milestone','full'],selector),log_directory=str(LOGS))
 path=ROOT/'.pr23_runner.json';path.write_text(json.dumps(config,indent=2),encoding='utf-8');before=source()
 result=subprocess.run([sys.executable,str(ROOT/'scripts/run_tests.py'),'--mode',level,'--config',str(path)])
 rp=ROOT/'TEST_REPORT.json'; report=json.loads(rp.read_text(encoding='utf-8-sig'))
 for rec in (report['latest_run'],report['history'][-1]):
  rec.update(verification_scope='PR23_'+phase.upper()+('_BASELINE' if baseline else ''),source_hash=before,source_changed_during_run=before!=source())
 report['pr23_handoff']['status']='IN_PROGRESS';rp.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 if result.returncode:raise RuntimeError('Actual test gate failed; see TEST_REPORT.json latest_run')
def probe(file):
 _,conf=configure(baseline=phase in ('upgrade','clone_upgrade','capture'));before=source();started=datetime.now(timezone.utc).isoformat()
 ref='evidence/pr23-'+phase+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.log'
 with (ROOT/ref).open('w',encoding='utf-8') as log:
  result=subprocess.run([sys.executable,str(ODOO/'odoo-bin'),'shell','-c',str(conf),'-d',db,'--no-http'],
   input=(ROOT/file).read_text(encoding='utf-8'),text=True,stdout=log,stderr=subprocess.STDOUT)
 content=(ROOT/ref).read_text(encoding='utf-8');markers=re.findall(r'^PR23_CASE ([A-Z0-9_]+)=PASS',content,re.M)
 passed=result.returncode==0 and ('PR23_PROBE=PASS' in content) and bool(markers)
 rp=ROOT/'TEST_REPORT.json';report=json.loads(rp.read_text(encoding='utf-8-sig'))
 rec=dict(prompt_id='PR-23',phase='DEV-12',odoo_version='20.0',module=MODULE,test_level='TARGETED',
  environment=dict(edition='Community',database=db,database_role='dedicated_test',port=PORT),
  invocation='Odoo shell '+file,started_at=started,completed_at=datetime.now(timezone.utc).isoformat(),exit_status=result.returncode,
  passed=len(markers) if passed else None,failed=0 if passed else None,skipped=0,result_status='PASS' if passed else 'FAIL',
  evidence_reference=ref,blocking_reason=None if passed else 'Probe assertion or completion marker missing',
  test_unit='assertion_groups',test_names=markers,source_hash=before,source_changed_during_run=before!=source())
 report['latest_run']=rec;report['history'].append(rec);report['current_status']=rec['result_status'];rp.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(rec),flush=True)
 if not passed:raise RuntimeError(ref)

assert CLUSTER.resolve().parent==ROOT
if not (CLUSTER/'PG_VERSION').exists():run([PG/'initdb.exe','-D',CLUSTER,'-U',ROLE,'-A','trust','--encoding=UTF8','--locale=C'])
run([PG/'pg_ctl.exe','-D',CLUSTER,'-o',f'-h 127.0.0.1 -p {PORT}','-l',ROOT/'.pr23_postgres.log','-w','start'])
try:
 if phase in ('fresh','upgrade','clone_upgrade'):
  run([PG/'createdb.exe','-h','127.0.0.1','-p',PORT,'-U',ROLE,'-T','template0','-E','UTF8',db])
 if phase in ('upgrade','clone_upgrade'):
  target=ROOT/'.pr23_baseline_addons'/MODULE;target.mkdir(parents=True,exist_ok=True)
  with zipfile.ZipFile(ROOT/'evidence/pr22-source-baseline.zip') as archive:archive.extractall(target)
  if phase=='upgrade':
   tests('install',True)
   probe('evidence/pr23-seed-probe.py')
  else:
   # This exact source is our retained PR22 synthetic cluster, never production.
   # pg_dump performs a consistent read-only dump; no source database is cloned
   # by the runner, deleted, rewritten, or exposed outside this workspace.
   old=ROOT/'.pr22_pgdata'; source_db='codex_vpr_pr22_fresh_5_20261102'
   assert json.loads((ROOT/'.pr22_state.json').read_text(encoding='utf-8'))['fresh']==source_db
   run([PG/'pg_ctl.exe','-D',old,'-o','-h 127.0.0.1 -p 55453','-l',ROOT/'.pr22_postgres.log','-w','start'])
   try:
    dump=ROOT/'.pr23-pr22-synthetic.dump'
    run([PG/'pg_dump.exe','-h','127.0.0.1','-p','55453','-U','codex_vpr_pr22','--no-owner','--no-privileges','-Fc','-f',dump,source_db])
   finally:run([PG/'pg_ctl.exe','-D',old,'-m','fast','-w','stop'])
   run([PG/'pg_restore.exe','-h','127.0.0.1','-p',PORT,'-U',ROLE,'--no-owner','--no-privileges','-d',db,dump])
   run([sys.executable,ROOT/'evidence/pr23-copy-filestore.py',db])
  probe('evidence/pr23-capture-probe.py')
  tests('update')
 elif phase in ('fresh','quick','targeted','milestone'):tests('install' if phase=='fresh' else 'update')
 else:probe('evidence/pr23-'+phase.replace('_','-')+'-probe.py')
finally:
 run([PG/'pg_ctl.exe','-D',CLUSTER,'-m','fast','-w','stop'])
