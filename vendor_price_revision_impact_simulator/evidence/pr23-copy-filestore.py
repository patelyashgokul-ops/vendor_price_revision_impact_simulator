"""Copy retained synthetic PR22 files without deleting or overwriting any content."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[1]
source=root/'.pr22_odoo_data/filestore/codex_vpr_pr22_fresh_5_20261102'
assert source.is_dir() and source.resolve().is_relative_to(root)
databases=sys.argv[1:]
assert databases and all(name in ('codex_vpr_pr23_upgrade_1_20261102','codex_vpr_pr23_upgrade_2_20261102','codex_vpr_pr23_upgrade_3_20261102','codex_vpr_pr23_upgrade_4_20261102') for name in databases)
files=[p for p in source.rglob('*') if p.is_file()]
assert files
results=[]
for database in databases:
 target=root/'.pr23_odoo_data/filestore'/database
 assert target.resolve().is_relative_to(root/'.pr23_odoo_data/filestore')
 copied=0;verified=[]
 for path in files:
  assert not path.is_symlink() and path.resolve().is_relative_to(source.resolve())
  relative=path.relative_to(source);destination=target/relative
  assert destination.resolve().is_relative_to(target.resolve())
  expected=hashlib.sha256(path.read_bytes()).hexdigest()
  if destination.exists():
   assert not destination.is_symlink() and hashlib.sha256(destination.read_bytes()).hexdigest()==expected, str(relative)+' existing bytes differ'
  else:
   destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,destination);copied+=1
  assert hashlib.sha256(destination.read_bytes()).hexdigest()==expected
  verified.append(dict(path=relative.as_posix(),sha256=expected,size=path.stat().st_size))
 results.append(dict(database=database,copied_missing_files=copied,verified_files=len(verified),manifest=verified))
payload=dict(checked_at=datetime.now(timezone.utc).isoformat(),source_database='codex_vpr_pr22_fresh_5_20261102',
 production=False,deleted=False,overwritten=False,results=results)
name='evidence/pr23-filestore-copy-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json'
(root/name).write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(evidence=name,results=[{k:v for k,v in r.items() if k!='manifest'} for r in results])))
