"""Reproducible syntax, baseline preservation and critical gateway checks."""
import ast,hashlib,json,zipfile
from datetime import datetime,timezone
from pathlib import Path
from lxml import etree
R=Path(__file__).resolve().parents[1]
checks=[]
def check(label,condition):
 assert condition,label
 checks.append(label)
names=['__init__.py','__manifest__.py']+[p.relative_to(R).as_posix() for d in ('models','security','views','tests','data') for p in (R/d).rglob('*') if p.is_file() and p.suffix in ('.py','.xml','.csv')]
ledger={n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in sorted(names)}
for n in names:
 if n.endswith('.py'):ast.parse((R/n).read_text(encoding='utf-8-sig'));checks.append('AST '+n)
 if n.endswith('.xml'):etree.parse(str(R/n));checks.append('XML '+n)
archive=R/'evidence/pr21-source-baseline.zip'
check('Exact archived PR21 source',hashlib.sha256(archive.read_bytes()).hexdigest()=='4b9b4cb9a37610204ccbf4979de61097be649c7d20caf39cb7f808bb0abdf413')
with zipfile.ZipFile(archive) as z:
 old=set(z.namelist());changed=sorted(n for n in old if z.read(n)!=(R/n).read_bytes())
 check('Only authorized legacy integration files changed',set(changed)=={'__manifest__.py','models/__init__.py','tests/__init__.py','models/application_engine.py','models/application_ui.py'})
 check('All old tests byte-identical',all(z.read(n)==(R/n).read_bytes() for n in old if n.startswith('tests/test_')))
 added=sorted(set(names)-old)
manifest=ast.literal_eval((R/'__manifest__.py').read_text())
for n in manifest['data']:check('Manifest resource '+n,(R/n).is_file())
for n in ('execution.py','execution_lock.py','execution_policy.py','execution_commit.py','execution_boundary.py','execution_ui.py'):
 src=(R/'models'/n).read_text();tree=ast.parse(src)
 for node in ast.walk(tree):
  if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
   check('No manual transaction boundary '+n+':'+str(node.lineno),node.func.attr not in ('commit','rollback','cursor'))
 check('No stale decision actor aliases '+n,'.decision_ids.actor_id' not in src and '.decision_ids.principal_id' not in src)
src=(R/'models/execution.py').read_text()
for token in ('_RECEIPT_CAPABILITY = object()',"type(confirmation) is not bool",'with clean.cr.savepoint()',"FOR UPDATE",'ApplicationEngine(request).build()',"'PENDING_COMMIT'",'ALREADY_APPLIED_TARGET_CHANGED','source_watch(request)','native.check_access'):
 check('Gateway '+token,token in src)
check('Explicit target UoM and ancestor locks','SELECT id FROM uom_uom' in src and 'unit.parent_path' in src)
check('One approval receipt uniqueness','UNIQUE(authorization_id)' in src)
check('No native sudo in gateway','.sudo(' not in src)
commit=(R/'models/execution_commit.py').read_text()
check('Deferred final commit guard','DEFERRABLE INITIALLY DEFERRED' in commit and 'clock_timestamp()' in commit)
check('Commit guard reads native only','UPDATE product_supplierinfo' not in commit and 'INSERT INTO product_supplierinfo' not in commit and 'DELETE FROM product_supplierinfo' not in commit)
security=(R/'security/execution_security.xml').read_text()
check('No native permission grant','model_product_supplierinfo' not in security)
check('No automatic group grants','implied_ids' not in security)
lock=(R/'models/execution_lock.py').read_text()
check('Native writers share versioned scope','ON CONFLICT' in lock and 'epoch+1' in lock and "_inherit = 'product.supplierinfo'" in lock)
for token in ('def create(', 'def write(', 'def unlink('):check('Native hook '+token,token in lock)
report=dict(prompt_id='PR-22',result_status='PASS',completed_at=datetime.now(timezone.utc).isoformat(),checks=len(checks),check_names=checks,source_hash=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest(),files=ledger,changed_legacy_files=changed,new_files=added,old_tests_unchanged=True)
(R/'evidence/pr22-source-ledger.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('result_status','checks','source_hash','changed_legacy_files','new_files')}))
