"""PR20 source preservation, syntax and transaction boundary checks."""
import ast,hashlib,json,zipfile
from datetime import datetime,timezone
from pathlib import Path
from xml.etree import ElementTree as ET
R=Path(__file__).resolve().parents[1];checks=[]
def check(ok,label):
 assert ok,label
 checks.append(label)
with zipfile.ZipFile(R/'evidence/pr19-source-baseline.zip') as z:
 names=z.namelist();check(len(names)==116,'exact PR19 116-file archive');changed=[]
 for n in names:
  check((R/n).is_file(),'retained '+n)
  if z.read(n)!=(R/n).read_bytes():changed.append(n)
 check(set(changed)=={'__manifest__.py','models/__init__.py','tests/__init__.py','models/approval_engine.py','models/approval.py'},'only five declared integration files differ; all old tests byte-identical')
 for n in ('models/approval_engine.py','models/approval.py'):
  old=z.read(n).decode().replace('self.policy._audit_snapshot()[str(self.policy.id)]','self.policy._approval_routing_snapshot()') if n.endswith('engine.py') else z.read(n).decode()
  new=(R/n).read_text(encoding='utf-8')
  if n.endswith('engine.py'):check(ast.dump(ast.parse(old))==ast.dump(ast.parse(new)),'engine only uses compatible routing policy hook')
  else:
   def strings_to_marker(tree):
    for node in ast.walk(tree):
     if isinstance(node,ast.Constant) and isinstance(node.value,str):node.value='STRING'
    return tree
   check(ast.dump(strings_to_marker(ast.parse(old)))==ast.dump(strings_to_marker(ast.parse(new))),'old approval logic unchanged; message text only')
 for n,addition in [('models/__init__.py','from . import approval_decision_math, approval_decision_policy, approval_decisions, approval_decision_ui'),('tests/__init__.py','from . import test_approval_decisions')]:
  before=ast.parse(z.read(n).decode());after=ast.parse((R/n).read_text(encoding='utf-8'))
  check(ast.dump(after)==ast.dump(ast.Module(body=before.body+ast.parse(addition).body,type_ignores=[])),'append-only imports '+n)
 prior=ast.literal_eval(z.read('__manifest__.py').decode());manifest=ast.literal_eval((R/'__manifest__.py').read_text(encoding='utf-8'))
 check(manifest['data']==prior['data']+['security/approval_decision_security.xml','views/approval_decision_views.xml'],'two decision XML files appended')
 for key in prior:
  if key!='data':check(prior[key]==manifest[key],'retained manifest '+key)
files=['__manifest__.py','__init__.py']+[str(p.relative_to(R)).replace(chr(92),'/') for d in ('models','security','views','tests','data') for p in (R/d).rglob('*') if p.is_file() and p.suffix in ('.py','.xml','.csv')]
ledger={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in sorted(files)}
for n in files:
 p=R/n
 if p.suffix=='.py':compile(p.read_text(encoding='utf-8'),str(p),'exec');check(True,'compile '+n)
 elif p.suffix=='.xml':ET.fromstring(p.read_bytes());check(True,'XML '+n)
for n in ('approval_decision_math.py','approval_decision_policy.py','approval_decisions.py','approval_decision_ui.py'):
 tree=ast.parse((R/'models'/n).read_text(encoding='utf-8'))
 for node in ast.walk(tree):
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
   check(node.func.attr not in ('commit','rollback'),'no manual transaction '+n+':'+str(node.lineno))
   if node.func.attr=='sudo':check(n=='approval_decision_ui.py' and node.lineno==138,'only existing-pattern metadata attachment identification elevation')
  if isinstance(node,ast.FunctionDef):check(node.name not in ('action_apply','action_apply_prices','action_dry_run'),'no application/dry-run method '+node.name)
hash_=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
report=dict(status='PASS',scope='source preservation, syntax, explicit forbidden call checks; not full security proof',checks=len(checks),completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),source_hash=hash_,changed_prior_files=changed,check_labels=checks)
(R/'evidence/pr20-static-checks.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(R/'evidence/pr20-verified-source-sha256.json').write_text(json.dumps(dict(source_hash=hash_,files=ledger),indent=2)+'\n',encoding='utf-8')
print('PR20_STATIC=PASS checks='+str(len(checks))+' files='+str(len(files))+' source='+hash_)
