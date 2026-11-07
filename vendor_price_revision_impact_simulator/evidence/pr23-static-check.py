"""Source-bound static safety and preservation evidence; no Odoo runtime claims."""
import ast
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
import zipfile
from lxml import etree
root=Path(__file__).resolve().parents[1];checks=[]
def check(condition,name):
 assert condition,name
 checks.append(name)
old=json.loads((root/'evidence/pr22-source-ledger.json').read_text(encoding='utf-8'))
allowed={'__manifest__.py','models/__init__.py','tests/__init__.py'}
with zipfile.ZipFile(root/'evidence/pr22-source-baseline.zip') as archive:
 check(set(archive.namelist())==set(old['files']),'Exact 139-file PR22 archive')
 for name,fp in old['files'].items():
  check(hashlib.sha256(archive.read(name)).hexdigest()==fp,'Archived original '+name)
  if name not in allowed:check((root/name).read_bytes()==archive.read(name),'Unchanged legacy '+name)
names=['__init__.py','__manifest__.py']+[str(p.relative_to(root)).replace('\\','/') for d in ('models','security','views','data','tests') for p in (root/d).rglob('*') if p.is_file() and p.suffix in ('.py','.xml','.csv')]
files={}
for name in sorted(names):
 raw=(root/name).read_bytes();files[name]=hashlib.sha256(raw).hexdigest()
 if name.endswith('.py'):
  tree=ast.parse(raw,filename=name);check(True,'AST '+name)
  if name.startswith('models/monitor_'):
   for node in ast.walk(tree):
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
     check(node.func.attr not in ('commit','rollback','cursor','action_apply_approved_vendor_prices'),name+' no operational gateway/manual transaction at '+str(node.lineno))
     if node.func.attr=='execute':
      first=node.args[0]
      while isinstance(first,ast.BinOp):first=first.left
      literal=first.value if isinstance(first,ast.Constant) and isinstance(first.value,str) else ''
      check(literal.lstrip().upper().startswith('SELECT'),name+' SQL is read/lock only at '+str(node.lineno))
 elif name.endswith('.xml'):
  etree.fromstring(raw);check(True,'XML '+name)
manifest=ast.literal_eval((root/'__manifest__.py').read_text(encoding='utf-8'))
for name in manifest['data']:check((root/name).is_file(),'Manifest data exists '+name)
for name in ('monitor_models','monitor_service','monitor_policy','monitor_ui'):
 check('from . import '+name in (root/'models/__init__.py').read_text(encoding='utf-8'),'Registered '+name)
for name in ('models/monitor_models.py','models/monitor_service.py','models/monitor_policy.py'):
 check('.sudo(' not in (root/name).read_text(encoding='utf-8'),'Original-user service '+name)
cron=etree.parse(str(root/'data/monitor_cron.xml'))
check(cron.xpath("//field[@name='active']/@eval")==['False'],'Cron shipped inactive')
security=etree.parse(str(root/'security/monitor_security.xml'))
for suffix in ('run','check','incident','event','correction'):
 node=security.xpath("//record[@id='mon23_"+suffix+"_scope']/field[@name='domain']")[0]
 check('execution_id.plan_id.request_id.baseline_id.order_ids' in node.text,'Protected customer-order source scope '+suffix)
 check('vpr_supply_cost_warehouse_ids' in node.text,'Protected warehouse cost scope '+suffix)
report=json.loads((root/'TEST_REPORT.json').read_text(encoding='utf-8-sig'))
for gate in report['pr22_handoff']['gates']:
 path=Path(gate['evidence_reference']);path=path if path.is_absolute() else root/path
 if gate.get('evidence_sha256'):check(hashlib.sha256(path.read_bytes()).hexdigest()==gate['evidence_sha256'],'Prior PR22 gate evidence '+gate['verification_scope'])
source=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
result=dict(prompt_id='PR-23',result_status='PASS',completed_at=datetime.now(timezone.utc).isoformat(),checks=len(checks),
 check_names=checks,source_hash=source,files=files,changed_legacy_files=sorted(allowed),
 new_files=sorted(set(files)-set(old['files'])),old_test_files_unchanged=True)
(root/'evidence/pr23-source-ledger.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('check_names','files')}))
