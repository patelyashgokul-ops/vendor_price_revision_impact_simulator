"""PR20 source preservation, syntax and transaction boundary checks."""
import ast,hashlib,json,zipfile
from datetime import datetime,timezone
from pathlib import Path
from xml.etree import ElementTree as ET
R=Path(__file__).resolve().parents[1];checks=[]
def check(ok,label):
 assert ok,label
 checks.append(label)
with zipfile.ZipFile(R/'evidence/pr20-source-baseline.zip') as z:
 names=z.namelist();check(len(names)==123,'exact PR20 123-file archive');changed=[]
 for n in names:
  check((R/n).is_file(),'retained '+n)
  if z.read(n)!=(R/n).read_bytes():changed.append(n)
 check(set(changed)=={'__manifest__.py','models/__init__.py','tests/__init__.py'},'only three declared integration files differ; all old tests byte-identical')
 for n,addition in [('models/__init__.py','from . import application_math, application_engine, application_plan, application_ui'),('tests/__init__.py','from . import test_application_planning')]:
  before=ast.parse(z.read(n).decode());after=ast.parse((R/n).read_text(encoding='utf-8'))
  check(ast.dump(after)==ast.dump(ast.Module(body=before.body+ast.parse(addition).body,type_ignores=[])),'append-only imports '+n)
 prior=ast.literal_eval(z.read('__manifest__.py').decode());manifest=ast.literal_eval((R/'__manifest__.py').read_text(encoding='utf-8'))
 check(manifest['data']==prior['data']+['security/application_security.xml','views/application_views.xml'],'two planning XML files appended')
 for key in prior:
  if key!='data':check(prior[key]==manifest[key],'retained manifest '+key)
files=['__manifest__.py','__init__.py']+[str(p.relative_to(R)).replace(chr(92),'/') for d in ('models','security','views','tests','data') for p in (R/d).rglob('*') if p.is_file() and p.suffix in ('.py','.xml','.csv')]
ledger={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in sorted(files)}
for n in files:
 p=R/n
 if p.suffix=='.py':compile(p.read_text(encoding='utf-8'),str(p),'exec');check(True,'compile '+n)
 elif p.suffix=='.xml':ET.fromstring(p.read_bytes());check(True,'XML '+n)
for n in ('application_math.py','application_engine.py','application_plan.py','application_ui.py'):
 tree=ast.parse((R/'models'/n).read_text(encoding='utf-8'))
 for node in ast.walk(tree):
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
   check(node.func.attr not in ('commit','rollback'),'no manual transaction '+n+':'+str(node.lineno))
   if node.func.attr=='sudo':check(n=='application_plan.py' and any(isinstance(c,ast.FunctionDef) and c.name=='_protected_sources' and c.lineno <= node.lineno <= c.end_lineno for c in ast.walk(tree)),'only existing-pattern metadata attachment identification elevation')
  if isinstance(node,ast.FunctionDef):check(node.name not in ('action_apply','action_apply_prices','action_execute','action_execute_plan'),'no execution method '+node.name)
check(not any('product_supplierinfo' in node.value.lower() for n in ('application_math.py','application_engine.py','application_plan.py','application_ui.py') for node in ast.walk(ast.parse((R/'models'/n).read_text(encoding='utf-8'))) if isinstance(node,ast.Constant) and isinstance(node.value,str)), 'no native supplierinfo SQL table mutation')
check('action_apply' not in (R/'views/application_views.xml').read_text(encoding='utf-8'), 'no apply button')
hash_=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
report=dict(status='PASS',scope='source preservation, syntax, explicit forbidden call checks; not full security proof',checks=len(checks),completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),source_hash=hash_,changed_prior_files=changed,check_labels=checks)
(R/'evidence/pr21-static-checks.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(R/'evidence/pr21-verified-source-sha256.json').write_text(json.dumps(dict(source_hash=hash_,files=ledger),indent=2)+'\n',encoding='utf-8')
print('PR21_STATIC=PASS checks='+str(len(checks))+' files='+str(len(files))+' source='+hash_)
