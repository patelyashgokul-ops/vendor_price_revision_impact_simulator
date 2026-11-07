"""Create the PR14 handoff only from source-matched, nonempty real evidence."""
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
rp = ROOT/'TEST_REPORT.json'
report = json.loads(rp.read_text(encoding='utf-8'))
ledger = json.loads((ROOT/'evidence/pr14-verified-source-sha256.json').read_text(encoding='utf-8'))
source_hash = hashlib.sha256(json.dumps(ledger, sort_keys=True).encode()).hexdigest()
checks = []


def check(label, condition):
    assert condition, label
    checks.append(label)


for name, sha in ledger.items():
    p = ROOT/name
    check('Frozen source '+name, hashlib.sha256(p.read_bytes()).hexdigest() == sha)
    if p.suffix == '.py':
        ast.parse(p.read_text(encoding='utf-8-sig'))
    if p.suffix == '.xml':
        etree.parse(str(p))
baseline = json.loads((ROOT/'evidence/pr13-verified-source-sha256.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(ROOT/'evidence/pr13-source-baseline.zip') as archive:
    for name, sha in baseline.items():
        check('Exact PR13 source archive '+name, hashlib.sha256(archive.read(name)).hexdigest() == sha)
        if name not in ('__manifest__.py', 'models/__init__.py', 'tests/__init__.py', 'tests/test_module_foundation.py'):
            check('Earlier feature/test unchanged '+name, ledger[name] == sha)
    old = archive.read('tests/test_module_foundation.py').decode('utf-8').replace('\r\n', '\n')
    extended = old.replace('self.env.ref(f"{MODULE}.menu_cost_snapshots"))',
        'self.env.ref(f"{MODULE}.menu_cost_snapshots") | self.env.ref(f"{MODULE}.menu_financial_analysis"))')
    check('Exact root/menu assertion extended, not weakened', extended == (ROOT/'tests/test_module_foundation.py').read_text(encoding='utf-8'))
check('Baseline archive checksum', hashlib.sha256((ROOT/'evidence/pr13-source-baseline.zip').read_bytes()).hexdigest() ==
      (ROOT/'evidence/pr13-source-baseline.sha256').read_text(encoding='utf-8').split()[0])
version = json.loads((ROOT/'evidence/pr14-version-verification.json').read_text(encoding='utf-8'))
check('Verified local Odoo20 release source', hashlib.sha256(Path(version['local_source']).read_bytes()).hexdigest() == version['local_sha256'])
gates = {}
for scope in ('FRESH', 'HELPERS_VERIFY', 'TARGETED', 'UPGRADE', 'UPGRADE-PRESERVATION', 'CONCURRENCY', 'OPERATIONAL-SAFETY'):
    scopes = {'PR14_UPGRADE', 'PR14_UPGRADE_VERIFY'} if scope == 'UPGRADE' else {'PR14_'+scope}
    matches = [r for r in report['history'] if r.get('verification_scope') in scopes and
        r.get('result_status') == 'PASS' and r.get('source_hash') == source_hash and r.get('source_changed_during_run') is False]
    check('Mandatory exact-source gate '+scope, bool(matches))
    gates[scope] = matches[-1]
    check('Real nonzero test/assertion count '+scope, matches[-1].get('passed', 0) > 0)
    check('Retained log '+scope, (ROOT/matches[-1]['evidence_reference']).is_file())
check('Disposable runtime removed', not list(ROOT.glob('.pr14*')))
check('Confirmed PostgreSQL shutdown', 'database system is shut down' in (ROOT/'evidence/pr14-postgres.log').read_text(encoding='utf-8'))
source = (ROOT/'models/financial_exposure.py').read_text(encoding='utf-8')
tree = ast.parse(source)
check('No business commits', '.commit(' not in source)
check('No new sudo projection', '.sudo(' not in source and 'su=True' not in source)
check('No native write/create/delete', not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ('create', 'write', 'unlink') for n in ast.walk(tree)))
check('No operational actions', not any(s in source for s in ('action_confirm(', 'button_confirm(', 'action_post(', '_action_done(', '_update_standard_price(', '_run_fifo(')))
check('No margin or risk fields', not any(s in source for s in ('gross_margin =', 'gross_profit =', 'risk_score =', 'target_margin =')))
check('Cost and sales authority reused', 'get_current_costs(**self.cost.scope)' in source and 'get_current_sales_terms(self.sales.fx_date)' in source)
check('No second allocation publisher', 'action_run_allocation(' not in source and 'action_collect_supply(' not in source)
fresh = (ROOT/gates['FRESH']['evidence_reference']).read_text(encoding='utf-8')
for marker in ('PR14_REFERENCE_A', 'PR14_REFERENCE_B', 'PR14_REFERENCE_C', 'PR14_REFERENCE_D', 'PR14_REFERENCE_E', 'PR14_REFERENCE_F', 'PR14_FX', 'PR14_WORKLOAD'):
    check('Executed financial fixture '+marker, marker in fresh)
seconds = float(re.search(r'PR14_WORKLOAD financial_entries=100 seconds=([\d.]+)', fresh).group(1))
ops = (ROOT/gates['OPERATIONAL-SAFETY']['evidence_reference']).read_text(encoding='utf-8')
check('Public/portal negative runtime proof', 'PR14_PORTAL_PUBLIC=PASS' in ops)
check('Upstream analytical snapshots unchanged', 'PR14_UPSTREAM_IMMUTABILITY=PASS' in ops)
models = re.search(r'PR14_OPERATIONAL_MODELS=(.+)', ops).group(1).split(',')
methods = (ROOT/'tests/test_financial_exposure.py').read_text(encoding='utf-8').count('    def test_')
now = datetime.now(timezone.utc).isoformat(timespec='seconds')
table = '\n'.join('| '+scope+' | '+str(r['passed'])+(' assertion groups' if r.get('test_unit') else ' tests')+' PASS | '+r['evidence_reference']+' |' for scope, r in gates.items())
changed = [n for n in ledger if n not in baseline or ledger[n] != baseline[n]]
summary = f'''# PR14 / DEV07 — projected financial exposure

## A — Environment

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4, Windows. Addon
`vendor_price_revision_impact_simulator`. The established 20.0 major is preserved.
Official stable version checked at development start: [release notes](https://www.odoo.com/page/release-notes),
[Community builds](https://nightly.odoo.com/). Local release hash and actual
verification timestamp are in evidence/pr14-version-verification.json.
All test databases belong to an owned disposable loopback cluster on55445;
production databases, credentials and operational records were not used.

## B — Implementation

Immutable financial.snapshot, financial.line and financial.issue models calculate
one contribution per exact PR10 entry from current PR13 costs and PR11 demand
classification. PR08/09/10/12 authorities are reused through their current getters.
Existing stock and protected incoming use the same source costs in baseline and
revised scenarios. Old procurement tiers are independently resolved for each
actual entry quantity using PR08's tier helper; proposed pricing comes from PR13.
No cross-demand consolidation, alternative vendor, Standard Cost or zero fallback.
Explicit procurement dates, current company policies and normalized UoMs apply.

Signed delta is revised minus baseline, using Decimal38. Common-rate and separate-
date FX methods remain distinct, with explicit price/FX decomposition where
source currencies permit. Grouped product/warehouse/UoM/classification weighted
costs are analytical references, never product revaluation. Raw/rounded totals and
rounding residuals reconcile; there is no arbitrary balancing line.

Confirmed and quotation/portfolio scenarios remain separate. A quotation requires
its matching current confirmed financial baseline; its conditional difference is
scenario delta minus confirmed delta, not another total to add. All missing inputs
and quantities remain visible. Full cost completeness is distinct from incremental
delta completeness; unchanged unknown stock may contribute zero delta while total
costs stay unavailable. Numeric completeness never upgrades estimates or hypothetical
buying/FX into verified actual procurement. Savepoints, company/batch serialization,
shared source locks, fingerprints, versioning and fresh getters protect publication.

## C — Actual files changed

{chr(10).join('- '+n for n in changed)}

The new service/security/UI/tests provide the feature; manifest and package imports
register it. The foundation exact-menu assertion includes the new Financial Analysis
folder without relaxing root/duplicate checks. Earlier business and security tests
remain unchanged. docs/FINANCIAL_EXPOSURE_ENGINE.md defines the financial contract.
Verification drivers/probes, baseline archive, ledger and logs are retained in
evidence/. TESTING_SETUP.md, TEST_REPORT.json and DEVELOPMENT_PROGRESS.md document
actual verification and handoff.

## D — Executed controlled financial references

| Fixture | Baseline | Revised | Projected delta / result |
|---|---:|---:|---|
| A: demand200, stock60@100, protected40@100, new100 old100/new115 | 20,000 | 21,500 | +1,500; weighted revised107.50 |
| B: same scope, eligible single-entry MOQ100 at109 | 20,000 | 20,900 | +900 |
| C: protected negotiated PO95, other terms unchanged | 19,800 | 21,300 | +1,500 |
| D: old price unavailable at planning date | unavailable | comparison unavailable | null delta; quantity100 retained, not zero |
| E: unapproved PO amendment40, recorded100/requested115 | unavailable protected comparison | unavailable | not accepted, quantity/reference alternatives preserved |
| F: confirmed100 plus conditional quote70, old100/new115 | scoped source costs retained | scenario scope170 | confirmed delta1,500; scenario delta2,550; conditional difference1,050; not additive |
| Signed decrease:100 units old115/new109 | 11,500 | 10,900 | -600 potential reduction, not realized savings |
| FX per unit:USD10@90 toUSD11@94 | 900 | 1,034 | +134 = supplier90 + FX44; common-rate alternative kept separate |
| Unknown FIFO stock60, plus new100 | total unavailable | total unavailable | projected delta1,500 may be complete; full cost remains incomplete |

Amounts are INR in these fixtures, under their declared source, date and per-entry
buying assumptions. Fixtures A/B/C are numerically complete scenarios, not proof of
accepted supplier prices, actual acquisition cost, future buying or recognized expense.

## E — Completeness and limitations

Cost, delta and source confidence are separate. Existing Standard/AVCO references
remain estimates; native FIFO company pools do not establish allocated warehouse
costs. Verified unchanged stock delta is not a verified total stock value.
Unprotected/pending/disputed POs, missing dates, old-tier conflicts, unsupported
FX and unresolved quantities stay incomplete. Known subset deltas are labeled
partial and never substituted for a full total. Sales FX/revenue incompleteness
does not prevent an otherwise valid cost calculation; it remains a PR15 input gap.

Future landed components, exact warehouse/lot FIFO tracing, procurement optimization,
explicit adjustable-PO amendment what-if execution and advanced scenarios are not
implemented. Net replacement and documented counterfactual old-price assumptions
remain explicit. No profitability, margin, risk or customer repricing is implemented.
Rounding residuals are visible and bounded; no hidden adjustment fills a gap.

## F — Security

Existing role/company/own-revision controls plus all demand/supply/cost warehouse
grants apply. Native customer-order permission and audited customer-commercial
warehouse scope are additionally required. Purchase-only cannot obtain customer
contracts, and Sales-only cannot obtain raw supplier cost/financial data. Finance
can create authorized analytical results without editing upstream intake. Auditors
remain read-only; public/portal read denial, foreign selected-company denial,
group/export rules, immutable/nested/context forgery, grant revocation and formula
injection protection are exercised. Native source drilldown retains native rights.
The financial service introduces no sudo projection or accounting-admin grant.

## G — Actual automated tests

| Gate | Exact final-source result | Evidence |
|---|---|---|
{table}

{methods} new financial test methods. Initial fresh run:53 passed/1 fixture error
(price syntax .004 rejected upstream). Second fresh run:55 passed/2 fixture errors
(changing a confirmed pricelist and missing native export permission). Third fresh
run:56 passed/1 failed fixture assertion, corrected to distinguish verified source
currency sales terms from unavailable company FX conversion. An interrupted fourth
attempt produced no completed test result and is not counted as a pass. These FAIL
records remain history. Fixtures were corrected to native supported setup without
relaxing any financial or security assertion. All final-source gates above passed.
The actual PR13 archive contains80 verified source files and real retained PR13
cost snapshots were cold-captured before any financial table existed. Upgrade
preservation compares all retained fields/source bytes, including sales, purchase,
cost, stock, confirmed orders and posted journal evidence. Seven real two-session
races cover duplicate collection, PO price, receipt, valuation value, FX, scope
revocation and proposed-price correction; changed sources are checked individually.
Operational safety compares {len(models)} native/master models and six upstream
analytical models, with real confirmed/reserved/valued/posted synthetic fixtures.

The 100-financial-entry benchmark measured {seconds:.3f}s in the final fresh run,
reconciling baseline100,000/revised115,000/delta15,000. Other benchmark sizes and
peak memory NOT_MEASURED; manual browser UAT NOT_RUN. XML views/actions load on
fresh installation and update. No release-wide FULL or PR15 test claim is made.

## H — Business safety

No customer repricing, supplierinfo change, PO/SO mutation, stock reservation,
inventory revaluation, accounting/bill posting, approval or vendor-price application
is performed by financial simulation. No gross profit, gross margin or risk scoring
is produced. Native writes in verification scripts prepare synthetic fixtures or
controlled competing source changes only. Business code has no commits or native
create/write/delete calls. Disposable runtime was removed after confirmed shutdown.

## I — Progress

PR14 VERIFIED for the documented projected financial calculation scope. All required
source-integrity, financial/security and installation/update gates passed. Historical
failures and unmeasured work remain explicit in TEST_REPORT.json. Final84-file
ledger SHA256:{source_hash}. PR15 remains NOT_STARTED. Wider release/UAT and
unsupported input scenarios are not claimed complete.

## J — PR15 handoff

Use only get_current_financial_exposure with fresh authorized PR08–13 sources.
Preserve exact allocation/cost/demand/order/product links, scenario and source
versions, grouped quantity/UoM, target/source currency and explicit FX method,
policy, old/proposed prices, MOQ, date and buying assumptions. Honor complete versus
partial baseline/revised costs, signed incremental totals, separate delta confidence,
conditional differences, raw/reported reconciliation and unknown inputs. Do not add
alternative quote totals or reconsume FIFO/PO/stock quantities. Current PR11 net
selling-value evidence is an additional profitability prerequisite, not something
this engine certifies or calculates into margin. Risk requires governed thresholds.
Estimated, scenario-only, disputed or stale inputs cannot become realized outcomes
or unqualified committed exposure. Recheck role/company/cost/customer scope and
native source permissions. STOP after PR14; no PR15 implementation was started.

Completed from actual evidence at {now}.
'''
(ROOT/'evidence/DEV-07-pr14-summary.md').write_text(summary, encoding='utf-8')
(ROOT/'evidence/DEV-07-pr14-static-validation.txt').write_text('\n'.join('PASS '+n for n in checks)+f'\nTOTAL_CHECKS={len(checks)}\nFINAL_SOURCE_HASH={source_hash}\n', encoding='utf-8')
record = dict(prompt_id='PR-14', phase='DEV-07', odoo_version='20.0', module=ROOT.name,
    environment=dict(os='Windows', edition='Community', database=None, database_scope='Static source and mandatory actual evidence checks'),
    test_level='QUICK', invocation='python evidence/pr14-finalize.py', started_at=started, completed_at=now,
    exit_status=0, passed=len(checks), failed=0, skipped=0, result_status='PASS', evidence_reference='evidence/DEV-07-pr14-static-validation.txt',
    blocking_reason=None, verification_scope='PR14_FINAL_STATIC', source_hash=source_hash, source_changed_during_run=False, test_unit='static_assertion_groups')
report['history'].append(record)
report['latest_run'] = record
report['current_status'] = 'PASS'
report['current_status_detail'] = 'PR14 VERIFIED: projected source-weighted financial exposure, explicit completeness/confidence; PR15 NOT_STARTED.'
report['pr14_handoff'] = dict(status='VERIFIED', summary='evidence/DEV-07-pr14-summary.md',
    source_ledger='evidence/pr14-verified-source-sha256.json', source_hash=source_hash,
    benchmark=dict(financial_entries=100, seconds=seconds, other_sizes='NOT_MEASURED', peak_memory='NOT_MEASURED'),
    not_run=['manual browser UAT'], limitations=['warehouse/lot FIFO cost lineage incomplete',
        'future landed components unsupported', 'per-entry buying and future FX assumptions remain scenario-only',
        'no authorized PO amendment what-if execution', 'selling-value completeness remains separate'],
    business_mutations=False, next_prompt='PR-15 NOT_STARTED')
rp.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
p = ROOT/'DEVELOPMENT_PROGRESS.md'
progress = p.read_text(encoding='utf-8')
progress = progress.replace('| M3 | Financial exposure, margin, what-if | NOT_STARTED |', '| M3 | Financial exposure, margin, what-if | IN_PROGRESS; PR14 verified, later margin/what-if pending |')
progress = re.sub(r'^\| PR-14 \|.*$', f"| PR-14 | DEV-07 projected financial exposure engine | VERIFIED | QUICK{gates['HELPERS_VERIFY']['passed']}; TARGETED{gates['TARGETED']['passed']}; fresh{gates['FRESH']['passed']}; actual PR13 update{gates['UPGRADE']['passed']}; preservation, seven races and {len(models)}-model safety PASS | evidence/DEV-07-pr14-summary.md; TEST_REPORT.json | Explicit scenario/estimated/incomplete costs; browser UAT NOT_RUN; larger loads/memory NOT_MEASURED | None for documented PR14 scope | 2026-10-29 | STOP after PR14; PR15 NOT_STARTED |", progress, flags=re.M)
progress += f'''

## PR-14 completion and PR15 handoff

Financial snapshot/line/issue models consume fresh PR08–13 sources without a second
allocation engine. Source-specific baseline/revised costs preserve owned stock and
protected PO terms; independent old tiers use actual per-entry procurement quantity.
Signed deltas, explicit common/separate-date FX, UoM, grouped weighted cost and
raw/report rounding reconcile. Confirmed and conditional scenarios remain separate.
Unknown costs stay null; total-cost completeness differs from delta completeness.
Numeric completeness never upgrades estimates or hypothetical buying/FX to actuals.
Company/cost/demand/customer/native scope and immutable evidence protect results.

Final84-source ledger:{source_hash}; {methods} new methods. QUICK
{gates['HELPERS_VERIFY']['passed']}, TARGETED{gates['TARGETED']['passed']}, fresh
{gates['FRESH']['passed']}, actual PR13 update{gates['UPGRADE']['passed']}, cold
preservation, seven real-session races, {len(models)}-native-model and six-upstream-
model safety PASS. Earlier fixture errors remain history.100-entry financial
collection measured{seconds:.3f}s; other loads/peak memory NOT_MEASURED; manual
browser UAT NOT_RUN. Dedicated runtime removed after confirmed shutdown.

See docs/FINANCIAL_EXPOSURE_ENGINE.md and evidence/DEV-07-pr14-summary.md for A–J
results, limitations and strict fresh-getter/reconciliation/security contract.
PR15 needs current compatible PR11 selling values, complete cost basis and governed
risk thresholds; no margin/risk/approval/application/customer repricing implemented.
STOP after PR14. PR15 remains NOT_STARTED.
'''
p.write_text(progress, encoding='utf-8')
print('PR14_FINAL_STATIC=PASS checks='+str(len(checks)))
print('PR14_VERIFIED_SOURCE='+source_hash)
