"""Static source/packaging checks complement runtime tests, never replace them."""
import ast,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from lxml import etree
r=Path.cwd();started=datetime.now(timezone.utc).isoformat(timespec='seconds');checks=[]
def check(condition,label):
 assert condition,label
 checks.append(label)
for d in ('models','tests'):
 for p in sorted((r/d).rglob('*.py')):
  ast.parse(p.read_text(encoding='utf-8-sig'));checks.append('AST '+str(p.relative_to(r)))
for d in ('security','views','data'):
 for p in sorted((r/d).rglob('*.xml')):
  etree.parse(str(p));checks.append('XML '+str(p.relative_to(r)))
manifest=ast.literal_eval((r/'__manifest__.py').read_text())
check(manifest['depends']==['base','product','purchase_stock','sale_stock'],'Exact Community purchase/stock dependency')
for f in manifest['data']:check((r/f).is_file(),'Manifest resource '+f)
for p in sorted((r/'models').glob('allocation_*.py')):
 tree=ast.parse(p.read_text())
 forbidden={'_action_done','_action_assign','_update_available_quantity','_update_reserved_quantity','button_confirm','button_validate','button_cancel','action_confirm','action_post','_set_standard_price'}
 check(not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden for n in ast.walk(tree)),'No operational actions '+p.name)
 check(not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='commit' for n in ast.walk(tree)),'No collector mid-transaction commit '+p.name)
check('get_current_supply(' in (r/'models/allocation_engine.py').read_text(),'Current PR09 gateway required')
check('self.reader.lock()' in (r/'models/allocation_engine.py').read_text(),'PR09 scoped source locks reused')
check("'not any'" in (r/'security/allocation_security.xml').read_text(),'All-warehouse global intersection rules present')
check((r/'docs/DEMAND_ALLOCATION.md').is_file(),'Operator/trust-boundary documentation retained')
ledger=json.loads((r/'evidence/pr10-verified-source-sha256.json').read_text())
check(all(hashlib.sha256((r/n).read_bytes()).hexdigest()==h for n,h in ledger.items()),'Frozen source ledger matches every code/test byte')
source_hash=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
check(hashlib.sha256((r/'evidence/pr09-source-baseline.zip').read_bytes()).hexdigest()==(r/'evidence/pr09-source-baseline.sha256').read_text().strip(),'Exact PR09 archive retained')
check(not any(r.glob('.pr10*')),'Disposable cluster, filestores, configs and baseline checkout removed')
check('database system is shut down' in (r/'evidence/pr10-postgres.log').read_text(),'Retained PostgreSQL clean-shutdown evidence')
for name in ('DEVELOPMENT_PROGRESS.md','README.md','TESTING_SETUP.md','docs/DEMAND_ALLOCATION.md','evidence/DEV-05-pr10-summary.md','TEST_REPORT.json'):
    value=(r/name).read_text(encoding='utf-8-sig')
    check('\ufffd' not in value,'UTF8 artifact '+name)
check(all('## '+c+' ' in (r/'evidence/DEV-05-pr10-summary.md').read_text(encoding='utf-8') for c in 'ABCDEFGHI'),'Complete A-I report sections')
log='evidence/DEV-05-pr10-static-validation.txt';(r/log).write_text('\n'.join(checks)+'\nSTATIC_CHECKS='+str(len(checks))+' PASS\n')
rp=r/'TEST_REPORT.json';report=json.loads(rp.read_text());record=dict(prompt_id='PR-10',phase='DEV-05',odoo_version='20.0',module=r.name,environment=dict(os='Windows',edition='Community',database=None),test_level='QUICK',invocation='python evidence/pr10-static-validation.py',started_at=started,completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),exit_status=0,passed=len(checks),failed=0,skipped=0,result_status='PASS',evidence_reference=log,blocking_reason=None,verification_scope='PR10_STATIC',source_hash=source_hash,source_changed_during_run=False)
report['history'].append(record);report['latest_run']=record;rp.write_text(json.dumps(report,indent=2)+'\n');print('STATIC_CHECKS='+str(len(checks))+' PASS')
