"""Narrow source audit against the verified PR23 baseline, without runtime claims."""
import ast
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
old = json.loads((ROOT/'evidence/pr23-source-ledger.json').read_text(encoding='utf-8'))['files']
names = ['__init__.py', '__manifest__.py'] + [str(path.relative_to(ROOT)).replace('\\', '/') for folder in ('models', 'security', 'views', 'data', 'tests') for path in (ROOT/folder).rglob('*') if path.is_file() and path.suffix in ('.py', '.xml', '.csv')]
files = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(names)}
changed = sorted(name for name, digest in old.items() if files.get(name) != digest)
assert changed == sorted(['__manifest__.py', 'models/__init__.py', 'tests/__init__.py', 'tests/test_module_foundation.py']), changed
new = sorted(set(files)-set(old))
assert new == sorted(['models/reporting.py', 'models/reporting_data.py', 'security/reporting_security.xml', 'views/reporting_views.xml', 'tests/test_reporting.py']), new
checks = []
for name in new + changed:
    if name.endswith('.py'):
        ast.parse((ROOT/name).read_text(encoding='utf-8'), filename=name)
        checks.append('PYTHON_PARSE '+name)
    elif name.endswith('.xml'):
        etree.parse(str(ROOT/name))
        checks.append('XML_PARSE '+name)
manifest = ast.literal_eval((ROOT/'__manifest__.py').read_text(encoding='utf-8'))
assert manifest['version'] == '20.0.1.0.0'
assert manifest['depends'] == ['base', 'product', 'purchase_stock', 'sale_stock', 'mail']
assert all((ROOT/name).is_file() for name in manifest['data'])
checks.append('PRESERVED_COMMUNITY_VERSION_AND_DEPENDENCIES')
for name in ('models/reporting.py', 'models/reporting_data.py'):
    tree = ast.parse((ROOT/name).read_text(encoding='utf-8'))
    forbidden = [(node.lineno, node.func.attr) for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr in ('sudo', 'create', 'write', 'unlink', 'execute', 'commit', 'action_execute_approved_plan')]
    assert not forbidden, (name, forbidden)
    checks.append('NO_OPERATIONAL_MUTATION_CALLS '+name)
source_hash = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
payload = dict(prompt_id='PR-24', completed_at=datetime.now(timezone.utc).isoformat(), result_status='PASS',
    source_hash=source_hash, files=files, file_count=len(files), checks=checks,
    changed_legacy_files=changed, new_files=new, retained_original_files=len(old)-len(changed),
    limitation='Static structure/syntax only; not runtime, permission, PDF or financial proof.')
(ROOT/'evidence/pr24-source-ledger.json').write_text(json.dumps(payload, indent=2)+'\n', encoding='utf-8')
print(json.dumps({key: value for key, value in payload.items() if key != 'files'}))
