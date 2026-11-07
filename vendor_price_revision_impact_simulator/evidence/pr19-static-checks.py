"""Source preservation and executable syntax checks; no runtime PASS inferred."""
import ast,hashlib,json,zipfile
from datetime import datetime,timezone
from pathlib import Path
from xml.etree import ElementTree as ET
R=Path(__file__).resolve().parents[1];checks=[]
def check(ok,label):
 assert ok,label
 checks.append(label)
with zipfile.ZipFile(R/'evidence/pr18-source-baseline.zip') as z:
 names=z.namelist();check(len(names)==108,'exact PR18 108-file archive')
 changed=[]
 for n in names:
  check((R/n).is_file(),'retained '+n)
  if z.read(n)!=(R/n).read_bytes():changed.append(n)
 check(set(changed)=={'__manifest__.py','models/__init__.py','tests/__init__.py','tests/test_module_foundation.py'},'only four declared old integration files differ')
 old=z.read('tests/test_module_foundation.py').decode().replace('\r','')
 old=old.replace('["base", "product", "purchase_stock", "sale_stock"]','["base", "product", "purchase_stock", "sale_stock", "mail"]')
 old=old.replace('self.env.ref(f"{MODULE}.menu_commercial_recommendations"))','self.env.ref(f"{MODULE}.menu_commercial_recommendations") | self.env.ref(f"{MODULE}.menu_approval_foundation"))')
 check(ast.dump(ast.parse(old))==ast.dump(ast.parse((R/'tests/test_module_foundation.py').read_text(encoding='utf-8'))),'all foundation assertions retained with explicit mail/menu extensions')
 for n,addition in [('models/__init__.py','from . import approval_math, approval_policy, approval_engine, approval'),('tests/__init__.py','from . import test_approval')]:
  before=ast.parse(z.read(n).decode());after=ast.parse((R/n).read_text(encoding='utf-8'))
  check(ast.dump(after)==ast.dump(ast.Module(body=before.body+ast.parse(addition).body,type_ignores=[])),'append-only imports '+n)
 manifest=ast.literal_eval((R/'__manifest__.py').read_text(encoding='utf-8'));prior=ast.literal_eval(z.read('__manifest__.py').decode())
 check(manifest['depends']==prior['depends']+['mail'],'only explicit mail dependency')
 check(manifest['data']==prior['data']+['security/approval_security.xml','data/approval_data.xml','views/approval_views.xml'],'only PR19 XML appended')
 for key in prior:
  if key not in ('depends','data'):check(prior[key]==manifest[key],'retained manifest '+key)
files=['__manifest__.py','__init__.py']+[str(p.relative_to(R)).replace('\\','/') for d in ('models','security','views','tests','data') for p in (R/d).rglob('*') if p.is_file() and p.suffix in ('.py','.xml','.csv')]
ledger={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in sorted(files)}
for n in files:
 p=R/n
 if p.suffix=='.py':compile(p.read_text(encoding='utf-8'),str(p),'exec');check(True,'compile '+n)
 elif p.suffix=='.xml':ET.fromstring(p.read_bytes());check(True,'XML '+n)
for n in ('approval.py','approval_policy.py','approval_engine.py','approval_math.py'):
 s=(R/'models'/n).read_text(encoding='utf-8');tree=ast.parse(s)
 for node in ast.walk(tree):
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
   check(node.func.attr not in ('sudo','commit','rollback'),'no elevated/manual transaction call '+n+':'+str(node.lineno))
  if isinstance(node,ast.FunctionDef):check(node.name not in ('action_approve','action_reject','action_return','action_apply'),'no decision/application method '+n+':'+node.name)
with zipfile.ZipFile(R/'evidence/pr19-pre-activity-hardening-source.zip') as z:
 changed_hardening=[n for n in z.namelist() if z.read(n)!=(R/n).read_bytes()]
 check(set(changed_hardening)=={'models/approval.py','models/approval_engine.py','tests/test_approval.py'},'hardening changes only activity boundary, additive risk/version and regression tests')
 def methods(tree):
  return {(cls.name,f.name):f for cls in tree.body if isinstance(cls,ast.ClassDef) for f in cls.body if isinstance(f,ast.FunctionDef)}
 for n,allowed in [('models/approval.py',{('ApprovalActivity','create'),('ApprovalActivity','write')}),('models/approval_engine.py',{('ApprovalEngine','route')}),('tests/test_approval.py',{('TestApprovalSecurity','test_no_manual_activity_or_chatter_bypass')})]:
  old=methods(ast.parse(z.read(n).decode()));new=methods(ast.parse((R/n).read_text(encoding='utf-8')))
  for key,node in old.items():
   check(key in new,'retained old method '+n+str(key))
   if key not in allowed:check(ast.dump(node)==ast.dump(new[key]),'unchanged old method '+n+str(key))
   elif n.startswith('tests/'):
    check(all(ast.dump(a)==ast.dump(b) for a,b in zip(node.body,new[key].body)),'old passing activity assertions retained as prefix')
hash_=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
report=dict(status='PASS',scope='static source preservation, syntax and explicit forbidden call checks; not runtime or full security proof',checks=len(checks),completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),source_hash=hash_,changed_prior_files=changed,check_labels=checks)
(R/'evidence/pr19-static-checks.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(R/'evidence/pr19-verified-source-sha256.json').write_text(json.dumps(dict(source_hash=hash_,files=ledger),indent=2)+'\n',encoding='utf-8')
print('PR19_STATIC=PASS checks='+str(len(checks))+' files='+str(len(files))+' source='+hash_)
