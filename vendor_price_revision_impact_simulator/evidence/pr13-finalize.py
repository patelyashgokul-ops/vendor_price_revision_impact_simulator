"""Fail-closed final report from real, source-matched PR13 runtime evidence."""
import ast
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
started = datetime.now(timezone.utc).isoformat(timespec='seconds')
report_path = ROOT/'TEST_REPORT.json'
report = json.loads(report_path.read_text(encoding='utf-8'))
ledger = json.loads((ROOT/'evidence/pr13-verified-source-sha256.json').read_text(encoding='utf-8'))
source_hash = hashlib.sha256(json.dumps(ledger, sort_keys=True).encode()).hexdigest()
checks = []


def check(label, condition):
    assert condition, label
    checks.append(label)


for name, sha in ledger.items():
    path = ROOT/name
    check('Frozen source '+name, hashlib.sha256(path.read_bytes()).hexdigest() == sha)
    if path.suffix == '.py':
        ast.parse(path.read_text(encoding='utf-8-sig'))
    if path.suffix == '.xml':
        etree.parse(str(path))
baseline = json.loads((ROOT/'evidence/pr12-verified-source-sha256.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(ROOT/'evidence/pr12-source-baseline.zip') as archive:
    for name, sha in baseline.items():
        check('Exact PR12 archive '+name, hashlib.sha256(archive.read(name)).hexdigest() == sha)
        if name not in ('__manifest__.py', 'models/__init__.py', 'tests/__init__.py', 'tests/test_module_foundation.py'):
            check('Earlier implementation/test unchanged '+name, ledger[name] == sha)
check('Baseline checksum', hashlib.sha256((ROOT/'evidence/pr12-source-baseline.zip').read_bytes()).hexdigest() ==
      (ROOT/'evidence/pr12-source-baseline.sha256').read_text(encoding='utf-8').split()[0])
native = json.loads((ROOT/'evidence/pr13-native-api-audit.json').read_text(encoding='utf-8'))
for item in native['files']:
    check('Native API source '+item['path'], hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() == item['sha256'])

runtime_ledger = json.loads((ROOT/'evidence/pr13-runtime-e330-source-sha256.json').read_text(encoding='utf-8'))
runtime_hash = hashlib.sha256(json.dumps(runtime_ledger, sort_keys=True).encode()).hexdigest()
check('Only menu assertion changed after application freeze',
      set(runtime_ledger) == set(ledger) and [n for n in ledger if runtime_ledger[n] != ledger[n]] == ['tests/test_module_foundation.py'])
with zipfile.ZipFile(ROOT/'evidence/pr12-source-baseline.zip') as archive:
    old_test = archive.read('tests/test_module_foundation.py').decode('utf-8').replace('\r\n', '\n')
expected = old_test.replace('self.env.ref(f"{MODULE}.menu_purchase_evidence"))',
                            'self.env.ref(f"{MODULE}.menu_purchase_evidence") | self.env.ref(f"{MODULE}.menu_cost_snapshots"))')
check('Foundation exact-menu assertion extended, not weakened',
      expected == (ROOT/'tests/test_module_foundation.py').read_text(encoding='utf-8'))
gates = {}
for scope in ('FRESH', 'HELPERS_VERIFY', 'TARGETED', 'UPGRADE', 'UPGRADE-PRESERVATION', 'CONCURRENCY', 'OPERATIONAL-SAFETY'):
    def compatible(r):
        if r.get('source_hash') == source_hash:
            return True
        # Only the foundation menu assertion changed, and neither accepted old
        # gate selected that test file. Application and selected tests are exact.
        return scope in ('FRESH', 'TARGETED') and r.get('source_hash') == runtime_hash and \
            bool(r.get('test_names')) and not any(n.startswith('TestModuleFoundation.') for n in r['test_names'])
    scopes = {'PR13_UPGRADE', 'PR13_UPGRADE_VERIFY'} if scope == 'UPGRADE' else {'PR13_'+scope}
    matches = [r for r in report['history'] if r.get('verification_scope') in scopes and
               r.get('result_status') == 'PASS' and compatible(r) and
               r.get('source_changed_during_run') is False]
    check('Mandatory final-source runtime gate '+scope, bool(matches))
    gates[scope] = matches[-1]
    check('Runtime evidence retained '+scope, (ROOT/matches[-1]['evidence_reference']).is_file())
    check('Nonzero executed assertion/test count '+scope, matches[-1]['passed'] > 0)
check('Disposable runtime removed', not list(ROOT.glob('.pr13*')))
check('Stopped PostgreSQL', 'database system is shut down' in (ROOT/'evidence/pr13-postgres.log').read_text(encoding='utf-8'))
source = (ROOT/'models/cost_attribution.py').read_text(encoding='utf-8')
check('No business commits', '.commit(' not in source)
check('No operational actions', not any(v in source for v in ('button_confirm(', 'action_post(', '_action_done(', '_action_assign(', '_update_standard_price(', '_run_fifo(')))
check('No final margin/exposure engine', not any(v in source for v in ('gross_margin =', 'gross_profit =', 'total_financial_exposure =')))
check('No operational writes', not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and
      n.func.attr in ('write', 'create', 'unlink') for n in ast.walk(ast.parse(source))))
check('FIFO layers retained once', "if k not in ('layers', 'reference_quantity', 'reference_value', 'reference_unit_cost')" in source)
check('Optional landed evidence company bound', "('cost_id.company_id', '=', cid)" in source)
fresh = (ROOT/gates['FRESH']['evidence_reference']).read_text(encoding='utf-8')
for marker in ('PR13_STANDARD', 'PR13_AVCO', 'PR13_FIFO', 'PR13_PROTECTED', 'PR13_REPLACEMENT', 'PR13_MOQ', 'PR13_LANDED', 'PR13_REFERENCE_A', 'PR13_WORKLOAD'):
    check('Executed controlled reference '+marker, marker in fresh)
seconds = float(re.search(r'PR13_WORKLOAD demand_entries=100 costs=100 seconds=([\d.]+)', fresh).group(1))
ops = (ROOT/gates['OPERATIONAL-SAFETY']['evidence_reference']).read_text(encoding='utf-8')
check('Portal/public runtime negatives', 'PR13_PORTAL_PUBLIC=PASS' in ops)
models = re.search(r'PR13_OPERATIONAL_MODELS=(.+)', ops).group(1).split(',')
methods = (ROOT/'tests/test_cost_attribution.py').read_text(encoding='utf-8').count('    def test_')
now = datetime.now(timezone.utc).isoformat(timespec='seconds')
table = '\n'.join('| '+scope+' | '+str(r['passed'])+(' assertion groups' if r.get('test_unit') else ' tests')+' PASS | '+r['evidence_reference']+' |' for scope, r in gates.items())
changed = [n for n in ledger if n not in baseline or ledger[n] != baseline[n]]
summary = f'''# PR13 / DEV07 — Inventory and replacement cost attribution

## A — Environment

Odoo 20.0 Community FINAL, Python 3.14.6, PostgreSQL 18.4, Windows. Addon
`vendor_price_revision_impact_simulator`. Owned disposable loopback cluster 55444;
no production credentials or databases. Native valuation uses stock.move.value,
product.value and the read-only product FIFO stack, not stock.valuation.layer.
Native source hashes: evidence/pr13-native-api-audit.json.

## B — Implementation

Immutable cost.snapshot, cost.line and cost.issue models attach exactly one result
to every current PR10 entry. Standard and AVCO retain company accounting references,
with supported-estimate allocation confidence. Reserved/free remain distinct.
FIFO preserves remaining native move portions and a reconciled company-product
pool once; warehouse/demand acquisition tracing stays incomplete. No invented
layer allocation or Standard Cost fallback. Current exact PR12 protected terms
can supply incoming costs; disputed/pending amendments retain both alternatives
without selecting a final protected price. PR08 proposals supply hypothetical
replacement costs using explicit date and per-entry buying quantity, guarded
FX/UoM and highest eligible unique MOQ. No cross-demand tier consolidation.
Native existing costs already include capitalized adjustments; nothing is added
again. Net replacement references explicitly exclude future unevidenced charges.
Quantity/cost confidence is separate; unknown value is null, documented zero is
numeric. Decimal precision 38 and separate currency rounding are retained.

Savepoint publication, company/batch serialization, shared source locks, complete
fingerprints, strict fresh getters and immutable previous versions protect audit
history and idempotence. Native source drilldowns retain ordinary native ACLs.

## C — Files changed

{chr(10).join('- '+n for n in changed)}

Architecture and PR14 contract: docs/COST_ATTRIBUTION_FOUNDATION.md. Verification
drivers/probes, native audit, baseline archive, full logs and frozen ledger are
retained under evidence/. DEVELOPMENT_PROGRESS.md and TEST_REPORT.json record
the actual status. Earlier implementation and financial/security test bodies are unchanged. The
foundation exact-menu assertion includes the new menu and preserves duplicate/root checks.

## D — Executed reference results

| Controlled fixture | Actual reference result |
|---|---|
| Standard Cost | 60 units at INR 100, reference 6,000; proposal 115 does not revalue stock |
| AVCO actual native receipts | 10 at 90 plus 10 at 110: company-product reference 100 |
| FIFO actual native receipts | 30 at 90 plus 30 at 100: company pool 60, value 5,700, weighted 95; warehouse selected cost unavailable |
| FIFO partial native consumption | Remaining portions 20 at 90 plus 30 at 100: 50, value 4,800 |
| Exact PR12 protected PO | 40 at 100, reference 4,000; proposal 115 not applied |
| New procurement | Explicit single-entry 100 at proposed 115, scenario reference 11,500 |
| MOQ 100 | Explicit single-entry buying scenario 100 selects 109; separate 60-unit entries each stay at 115 |
| Landed no-double-counting | Configured recorded-cost reference 105 remains 105, never 110; no landed posting claimed |
| Combined scenario | Demand 200 = stock 60 at 100 + protected incoming 40 at 100 + new procurement 100 at 115; distinct sources, no gross margin |

## E — Confidence and limitations

Accounting source verification differs from physical acquisition proof. Standard/
AVCO attribution is a supported estimate; protected PO is a verified commercial
basis; replacement/MOQ is a hypothetical scenario, not an actual buying guarantee.
Missing date/FX/tier, default zero, unreconciled FIFO, lot-valuated lineage and
pending/disputed PO protection remain unavailable/review. FIFO company pool is
never another source-consumption ledger. Optional Community landed-cost source
integration is statically inspected; a real posted landed-cost fixture was
NOT_RUN. The 105 no-addition reference test is controlled configured-cost evidence,
not proof of a real landed-cost posting. Verified future freight/duty components
and exact lot/warehouse FIFO tracing are unsupported. Net references are not
fully landed costs. No missing cost contributes a false numeric zero.

## F — Security

Global company and all demand/supply/cost warehouse scopes apply to headers and
children; own-revision preparer role rules still apply. Sales-only, public and
portal raw-cost reads are denied. Auditors read only and cannot collect or forge
results. Direct ORM write/copy/delete, nested commands, context forgery, exports,
group reads, revoked grants and foreign selected-company access are covered.
Native cost-source opening needs native source permission. Fixed read projections
are exact company/product bound; optional landed evidence is company bound.

## G — Actual automated tests

| Gate | Source-validated result | Evidence |
|---|---|---|
{table}

{methods} new PR13 test methods. Initial fresh-install run: 29 passed, 3 failed
(PR12 scope argument mapping and a documented-zero fixture expectation); retained
FAIL history, corrected and superseded by passing final-source gates. Earlier
passing intermediate runs remain history; source compatibility is explicitly checked below.
Actual PR12 source is verified against its 76-file archive before installing it,
seeding retained records, cold capture, PR13 update and preservation comparison.
The first upgrade run had 113 passed and 1 failed: its exact root-menu assertion
omitted the newly implemented cost menu. That expected-menu set was extended;
no duplicate/root checks or business assertions were relaxed. The corrected
foundation QUICK and repeated upgrade milestone pass. Fresh44 and TARGETED118
remain valid evidence for unchanged application/selected test sources: the exact
pre-correction ledger e33036f7c8a6e082405ad3a1cac9e769b3e38c1b918056447e80f838dddaa19a
is retained as pr13-runtime-e330-source-sha256.json. The final ledger differs only
in tests/test_module_foundation.py, which those two runs did not select. This
compatibility is asserted, not retroactively relabeled as an exact-ledger run.
Six actual two-session races exercise collection,
PO price, receipt, valuation value, FX and grant changes. Retries serialize rather
than duplicate results; changed sources are rejected by fresh consumers.
Operational safety compares {len(models)} native/master models including confirmed
PO/SO, reservations, done valued move and posted entry. Public/portal direct reads
are checked additionally. Full logs and actual commands are retained.

100 demand entries reconciled; collection measured {seconds:.3f}s in the final
fresh fixture. 500/2,000/10,000 loads and peak memory NOT_MEASURED; manual browser
UAT NOT_RUN. Registered XML views/actions load on install/update. No release-wide
FULL claim or future PR14 functionality is asserted.

## H — Business safety

No product cost change, inventory revaluation, landed posting, PO/SO modification,
supplier rule change, accounting posting, customer repricing, procurement,
commercial approval/application, consolidated exposure or gross margin occurs
from PR13. Operational/posting writes in fixture scripts prepare synthetic test
records only. Business service has no commits or native create/write/delete calls.
Disposable runtime resources were removed after confirmed PostgreSQL shutdown.

## I — Progress

PR13 VERIFIED for this conservative attribution foundation. TEST_REPORT.json and
DEVELOPMENT_PROGRESS.md contain actual evidence, retained failures and limits.
Final 80-source ledger SHA256: {source_hash}.
PR12 archive SHA256: 58e17a7d296ca9ad61d19f4abe16af35d1ef8ef95b85760c3ab1df27a66b6618.
No critical mandatory failure remains. Unsupported cases stay visibly incomplete.

## J — PR14 handoff

Consume only get_current_costs(allocation_id, purchase_id, procurement_date), with
fresh upstream PR10/PR12/PR08 evidence. Retain exact entry/capacity IDs, original
base quantities/UoMs, source/company currency, FX/date/policy and snapshot versions.
Use separate accounting/PO/replacement semantics and per-source confidence. Keep
reserved/free/incoming/new procurement quantities separate. Reconcile every entry
and segment; never add independent scenarios, amendment alternatives or company
FIFO pool references as extra stock. Missing cost, unresolved lot/FIFO/FX/landed
inputs and unverified protection must remain unresolved, not zero exposure.
Recheck company/role/warehouse/native-source authorization at use time. Potential
scenario reference is not realized financial outcome. PR14 remains NOT_STARTED;
no financial exposure, profitability, approval or application engine is implemented.

Completed from real evidence at {now}.
'''
(ROOT/'evidence/DEV-07-pr13-summary.md').write_text(summary, encoding='utf-8')
(ROOT/'evidence/DEV-07-pr13-static-validation.txt').write_text('\n'.join('PASS '+n for n in checks)+f'\nTOTAL_CHECKS={len(checks)}\nFINAL_SOURCE_HASH={source_hash}\n', encoding='utf-8')
record = dict(prompt_id='PR-13', phase='DEV-07', odoo_version='20.0', module=ROOT.name,
    environment=dict(os='Windows', edition='Community', database=None, database_scope='Static final-source and mandatory evidence checks'),
    test_level='QUICK', invocation='python evidence/pr13-finalize.py', started_at=started, completed_at=now,
    exit_status=0, passed=len(checks), failed=0, skipped=0, result_status='PASS',
    evidence_reference='evidence/DEV-07-pr13-static-validation.txt', blocking_reason=None,
    verification_scope='PR13_FINAL_STATIC', source_hash=source_hash, source_changed_during_run=False,
    test_unit='static_assertion_groups')
report['history'].append(record)
report['latest_run'] = record
report['current_status'] = 'PASS'
report['current_status_detail'] = 'PR13 VERIFIED: final-source mandatory gates passed; PR14 NOT_STARTED. See full A-J report and explicit incomplete cost inputs.'
report['pr13_handoff'] = dict(status='VERIFIED', summary='evidence/DEV-07-pr13-summary.md',
    source_ledger='evidence/pr13-verified-source-sha256.json', source_hash=source_hash,
    compatible_runtime_ledger='evidence/pr13-runtime-e330-source-sha256.json',
    compatibility_reason='Only exact-menu foundation assertion extended; prior FRESH/TARGETED application and selected test sources unchanged',
    benchmark=dict(demand_entries=100, seconds=seconds, larger_workloads='NOT_MEASURED', peak_memory='NOT_MEASURED'),
    not_run=['manual browser UAT', 'posted stock_landed_costs fixture'],
    limitations=['company FIFO pool is not warehouse/demand acquisition lineage', 'lot-valuated lineage unsupported',
                 'future freight/duty components unsupported', 'replacement buying quantities are hypothetical, per entry'],
    business_mutations=False, next_prompt='PR-14 NOT_STARTED')
report_path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
p = ROOT/'DEVELOPMENT_PROGRESS.md'
progress = p.read_text(encoding='utf-8')
progress = re.sub(r'^\| PR-13 \|.*$', f"| PR-13 | DEV-07 inventory and replacement cost attribution | VERIFIED | QUICK{gates['HELPERS_VERIFY']['passed']}; TARGETED{gates['TARGETED']['passed']}; fresh{gates['FRESH']['passed']}; actual PR12 update{gates['UPGRADE']['passed']}; preservation, six races and operational safety PASS | evidence/DEV-07-pr13-summary.md; TEST_REPORT.json | FIFO warehouse/lot lineage incomplete; net replacement only; browser UAT NOT_RUN; larger loads NOT_MEASURED | None for conservative PR13 foundation | 2026-10-29 | STOP after PR13; PR14 NOT_STARTED |", progress, flags=re.M)
progress = progress.replace('| M2 | Sales, purchase, inventory, supply allocation | IN_PROGRESS (PR09–PR12 verified; inventory cost attribution remains) |', '| M2 | Sales, purchase, inventory, supply allocation | IN_PROGRESS (PR09–PR13 foundations verified; broader workflow/browser UAT not claimed) |')
progress = progress.replace('## PR-13 active verification', '## PR-13 initial verification history')
progress = progress.replace('Fresh, targeted, upgrade-preservation, concurrency and safety gates remain pending.', 'Those gates were pending at this initial checkpoint; final evidence and status follow below.')
progress += f'''

## PR-13 completion and handoff

Read-only cost snapshots/lines/issues attach one result to every current PR10
entry. Standard/AVCO company references, reconciled native FIFO remaining-move
pools, exact current PR12 protected terms and PR08 per-entry replacement/MOQ/date/
FX scenarios preserve separate cost confidence and quantity authority. Historical
landed charges are never added twice. Unknown cost remains null; physical FIFO
warehouse/lot lineage and future unevidenced components remain incomplete.

Final source: 80 files, SHA256 {source_hash}. {methods} new tests; final QUICK
{gates['HELPERS_VERIFY']['passed']}, TARGETED {gates['TARGETED']['passed']}, fresh
{gates['FRESH']['passed']}, actual PR12 update {gates['UPGRADE']['passed']}, cold
preservation, six real-session races and {len(models)}-model operational safety PASS.
Prior failures remain history. 100-entry collection {seconds:.3f}s; larger loads/
memory NOT_MEASURED, manual browser UAT and posted landed-cost fixture NOT_RUN.
Runtime removed after confirmed shutdown. No operational financial/stock changes.

See docs/COST_ATTRIBUTION_FOUNDATION.md and evidence/DEV-07-pr13-summary.md for
complete A–J evidence and strict fresh-getter/source reconciliation/security
contract. No consolidated exposure, profitability, approval or price application.
STOP after PR13. PR14 remains NOT_STARTED.
'''
p.write_text(progress, encoding='utf-8')
print('PR13_FINAL_STATIC=PASS checks='+str(len(checks)))
print('PR13_VERIFIED_SOURCE='+source_hash)
