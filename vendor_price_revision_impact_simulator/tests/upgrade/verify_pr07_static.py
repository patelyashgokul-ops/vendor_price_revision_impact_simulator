"""Standalone QUICK evidence checks; run after final Odoo verification and cleanup."""
import ast
import hashlib
import json
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

ledger=json.loads((ROOT/'evidence/pr07-verified-source-sha256.json').read_text(encoding='utf-8'))
for name,digest in ledger.items():
    check('Frozen source '+name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest)
    if name.endswith('.py'): compile((ROOT/name).read_bytes(),name,'exec')
manifest=ast.literal_eval((ROOT/'__manifest__.py').read_text(encoding='utf-8'))
check('Community version/dependencies retained',manifest['version']=='20.0.1.0.0' and manifest['depends']==['base','product'])
for name in manifest['data']: ElementTree.parse(ROOT/name)
check('Every manifest XML document parses',True)
old=json.loads((ROOT/'evidence/pr06-verified-source-sha256.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(ROOT/'evidence/pr06-source-baseline.zip') as archive:
    check('Actual PR06 archive matches every verified hash',all(hashlib.sha256(archive.read(name)).hexdigest()==value for name,value in old.items()))
check('Prior business sources/tests/security preserved',all(ledger[name]==digest for name,digest in old.items() if name not in ('__manifest__.py','models/__init__.py','tests/__init__.py')))
source=(ROOT/'models/product_resolution.py').read_text(encoding='utf-8')
check('No business sudo or intermediate commit', '.sudo(' not in source and '.commit(' not in source)
check('No master SQL writes',not any(token in source.upper() for token in ('UPDATE PRODUCT_', 'INSERT INTO PRODUCT_', 'DELETE FROM PRODUCT_')))
report=json.loads((ROOT/'TEST_REPORT.json').read_text(encoding='utf-8'))
history=[r for r in report['history'] if r.get('prompt_id')=='PR-07']
for scope,count in [('PR07_FRESH',148),('PR07_TARGETED',47),('PR07_UPGRADE_VERIFY',148),('PR07_CONCURRENCY',5)]:
    runs=[r for r in history if r.get('verification_scope')==scope]
    run=runs[-1]
    content=(ROOT/run['evidence_reference']).read_text(encoding='utf-8')
    check(scope+' genuine status/count/evidence',run['result_status']=='PASS' and run['passed']==count and run['failed']==0 and bool(content))
    if scope!='PR07_CONCURRENCY':
        check(scope+' Odoo nonempty successful summary',f'0 failed, 0 error(s) of {count} tests' in content)
        for cls in ('TestProductExactMatching','TestVendorProductRegistry','TestProductResolutionFreshness','TestProductResolutionSecurity'):
            check(scope+' selected '+cls,any(name.startswith(cls+'.') for name in run['test_names']))
    else:
        check('Five independent-session markers',all('PR07_CONCURRENT_'+name+'=PASS' in content for name in ('MATCH','CORRECT','VERIFY','RETIRE','ARCHIVE')))
run=[r for r in history if r.get('verification_scope')=='PR06_TO_PR07_PRESERVATION'][-1]
check('Actual PR06 correction/source/history preservation',run['result_status']=='PASS' and 'PR07_PROBE=PASS' in (ROOT/run['evidence_reference']).read_text(encoding='utf-8'))
check('Real failures and BLOCKED startup retained',any(r['result_status']=='FAIL' for r in history) and any(r['result_status']=='BLOCKED' for r in history))
check('No temporary test resources remain',not list(ROOT.glob('.pr07*')))
check('Clean PostgreSQL shutdown retained','database system is shut down' in (ROOT/'evidence/pr07-postgres.log').read_text(encoding='utf-8').splitlines()[-1])
check('Operator/handoff guide exists',(ROOT/'docs/PRODUCT_MAPPING_GUIDE.md').is_file())
completed=datetime.now(timezone.utc).isoformat(timespec='seconds')
ref='evidence/DEV-04-pr07-static-validation.txt'
(ROOT/ref).write_text('PR07 QUICK static evidence\nStarted: '+started+'\nCompleted: '+completed+'\n'+'\n'.join(checks)+'\n',encoding='utf-8')
record=dict(prompt_id='PR-07',phase='DEV-04',odoo_version='20.0',module=ROOT.name,
    environment=dict(os='Windows',edition='Community',database=None),test_level='QUICK',
    invocation='python tests/upgrade/verify_pr07_static.py',started_at=started,completed_at=completed,
    exit_status=0,passed=len(checks),failed=0,skipped=0,result_status='PASS',
    evidence_reference=ref,blocking_reason=None,verification_scope='PR07_STATIC')
report['history'].append(record);report['latest_run']=record
(ROOT/'TEST_REPORT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('PASS static checks:',len(checks))
