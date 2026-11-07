"""Final standalone PR08 source/evidence/cleanup audit. No Odoo runtime required."""
import ast
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree
ROOT=Path(__file__).resolve().parents[2]
started=datetime.now(timezone.utc).isoformat(timespec='seconds')
checks=[]
def check(label,condition):
 assert condition,label
 checks.append('PASS '+label)
ledger=json.loads((ROOT/'evidence/pr08-verified-source-sha256.json').read_text(encoding='utf-8'))
for name,value in ledger.items():
 check('Frozen source '+name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value)
 if name.endswith('.py'):compile((ROOT/name).read_bytes(),name,'exec')
manifest=ast.literal_eval((ROOT/'__manifest__.py').read_text(encoding='utf-8'))
check('Community version/dependencies retained',manifest['version']=='20.0.1.0.0' and manifest['depends']==['base','product'])
for name in manifest['data']:ElementTree.parse(ROOT/name)
check('All manifest XML parses',True)
old=json.loads((ROOT/'evidence/pr07-verified-source-sha256.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(ROOT/'evidence/pr07-source-baseline.zip') as z:
 check('Actual PR07 archive matches every prior verified source hash',all(hashlib.sha256(z.read(n)).hexdigest()==v for n,v in old.items()))
allowed={'__manifest__.py','models/__init__.py','tests/__init__.py','models/product_resolution.py','tests/test_product_resolution.py'}
check('Prior business changes limited to registration and documented identity/fixture fixes',all(ledger[n]==v for n,v in old.items() if n not in allowed))
for name in ('models/commercial_engine.py','models/commercial_validation.py','models/commercial_math.py'):
 source=(ROOT/name).read_text(encoding='utf-8')
 check(name+' no sudo/intermediate commit', '.sudo(' not in source and '.commit(' not in source)
 check(name+' no SQL master-price mutation',not any(token in source.upper() for token in ('UPDATE PRODUCT_', 'INSERT INTO PRODUCT_', 'DELETE FROM PRODUCT_', 'UPDATE RES_CURRENCY', 'INSERT INTO RES_CURRENCY')))
report=json.loads((ROOT/'TEST_REPORT.json').read_text(encoding='utf-8'))
history=[r for r in report['history'] if r.get('prompt_id')=='PR-08']
def last(scope):return [r for r in history if r.get('verification_scope')==scope][-1]
classes=('TestCommercialMath','TestCommercialNormalization','TestCommercialFx','TestVendorCommercialBaseline','TestCommercialSnapshots','TestCommercialSecurity')
expected_hash=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
for scope,count in [('PR08_FRESH',195),('PR08_TARGETED',113),('PR08_UPGRADE_VERIFY',195)]:
 run=last(scope);text=(ROOT/run['evidence_reference']).read_text(encoding='utf-8')
 check(scope+' genuine status/count',run['result_status']=='PASS' and run['passed']==count and run['failed']==0)
 if run.get('source_hash'):
  check(scope+' exact final source hash',run['source_hash']==expected_hash and not run.get('source_changed_during_run'))
 else:
  # The fresh candidate began before the final numeric edit, but Odoo imports
  # this addon after installing its dependencies. Prove the frozen runtime/test
  # files all predate that recorded addon-load boundary; do not reuse earlier
  # targeted/update candidates whose addon import preceded the edit.
  match=re.search(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Loading module vendor_price_revision_impact_simulator',text,re.M)
  cutoff=datetime.strptime(match.group(1),'%Y-%m-%d %H:%M:%S,%f').replace(tzinfo=timezone.utc).timestamp() if match else 0
  names=[n for n in ledger if not n.startswith('tests/upgrade/')]
  check(scope+' frozen source predates actual addon import',bool(cutoff) and all((ROOT/n).stat().st_mtime<=cutoff for n in names))
 check(scope+' nonempty successful Odoo summary',f'0 failed, 0 error(s) of {count} tests' in text)
 for cls in classes:check(scope+' selected '+cls,any(n.startswith(cls+'.') for n in run['test_names']))
 check(scope+' financial reference markers',all(marker in text for marker in ('PR08_REFERENCE','PR08_FX_REFERENCE','PR08_TIER_REFERENCE','PR08_WORKLOAD')))
run=last('PR07_TO_PR08_PRESERVATION')
check('Actual PR07 source/correction/verified identity preservation',run['result_status']=='PASS' and 'PR08_PROBE=PASS' in (ROOT/run['evidence_reference']).read_text(encoding='utf-8'))
run=last('PR08_CONCURRENCY');text=(ROOT/run['evidence_reference']).read_text(encoding='utf-8')
check('Nine real-session concurrency probes',run['result_status']=='PASS' and run['passed']==9 and all('PR08_CONCURRENT_'+n+'=PASS' in text for n in ('VALIDATE','BASELINE','FX','UOM_FACTOR','PRODUCT_UOM','CORRECT','MAPPING','CANCEL','CONTEXT')))
run=last('PR08_OPERATIONAL_SAFETY');text=(ROOT/run['evidence_reference']).read_text(encoding='utf-8')
check('Operational existing confirmed/posted/valued fixtures unchanged',run['result_status']=='PASS' and 'PR08_OPERATIONAL_SAFETY=PASS' in text and all(n in text for n in ('confirmed_SO=','confirmed_PO=','posted_entry=','valued_done_move=','move_value=3500.0')))
check('Odoo20 valuation model limitation stated','PR08_OPERATIONAL_SVL_MODEL=NOT_APPLICABLE_Odoo20_stock_move_value' in text)
check('Earlier relevant failed attempts retained',any(r['result_status']=='FAIL' for r in history))
check('No disposable resources remain',not list(ROOT.glob('.pr08*')))
check('Clean PostgreSQL shutdown retained','database system is shut down' in (ROOT/'evidence/pr08-postgres.log').read_text(encoding='utf-8').splitlines()[-1])
check('Operator/commercial handoff guide exists',(ROOT/'docs/COMMERCIAL_PRICE_VALIDATION.md').is_file())
completed=datetime.now(timezone.utc).isoformat(timespec='seconds');ref='evidence/DEV-04-pr08-static-validation.txt'
(ROOT/ref).write_text('PR08 QUICK static evidence\nStarted: '+started+'\nCompleted: '+completed+'\n'+'\n'.join(checks)+'\n',encoding='utf-8')
record=dict(prompt_id='PR-08',phase='DEV-04',odoo_version='20.0',module=ROOT.name,environment=dict(os='Windows',edition='Community',database=None),test_level='QUICK',invocation='python tests/upgrade/verify_pr08_static.py',started_at=started,completed_at=completed,exit_status=0,passed=len(checks),failed=0,skipped=0,result_status='PASS',evidence_reference=ref,blocking_reason=None,verification_scope='PR08_STATIC')
report['history'].append(record);report['latest_run']=record
(ROOT/'TEST_REPORT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('PASS static checks:',len(checks))
