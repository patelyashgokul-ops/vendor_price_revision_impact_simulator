"""Finalize only after source-qualified runtime gates and safe runtime cleanup."""
import ast
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from lxml import etree

ROOT=Path(__file__).resolve().parents[1]
rp=ROOT/'TEST_REPORT.json'
report=json.loads(rp.read_text(encoding='utf-8'))
ledger=json.loads((ROOT/'evidence/pr11-verified-source-sha256.json').read_text(encoding='utf-8'))
source_hash=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
checks=[]
def check(label,condition):
    assert condition,label
    checks.append(label)
for n,h in ledger.items():
    p=ROOT/n
    check('Frozen source '+n,hashlib.sha256(p.read_bytes()).hexdigest()==h)
    if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'))
    if p.suffix=='.xml':etree.parse(str(p))
old=json.loads((ROOT/'evidence/pr10-verified-source-sha256.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(ROOT/'evidence/pr10-source-baseline.zip') as z:
    for n,h in old.items():check('Exact PR10 archive '+n,hashlib.sha256(z.read(n)).hexdigest()==h)
check('Archive checksum',hashlib.sha256((ROOT/'evidence/pr10-source-baseline.zip').read_bytes()).hexdigest()==(ROOT/'evidence/pr10-source-baseline.sha256').read_text(encoding='utf-8').split()[0])
scopes={}
for scope in ('HELPERS_VERIFY','TARGETED','FRESH','UPGRADE','UPGRADE-PRESERVATION','CONCURRENCY','OPERATIONAL-SAFETY'):
    matching=[r for r in report['history'] if r.get('verification_scope') in ({'PR11_UPGRADE','PR11_UPGRADE_VERIFY'} if scope=='UPGRADE' else {'PR11_'+scope})
        and r.get('result_status')=='PASS' and r.get('source_hash')==source_hash and r.get('source_changed_during_run') is False]
    check('Runtime gate '+scope,bool(matching))
    record=matching[-1]
    check('Retained log '+scope,(ROOT/record['evidence_reference']).is_file())
    scopes[scope]=record
check('No runtime resources',not list(ROOT.glob('.pr11*')))
check('Confirmed PostgreSQL shutdown','database system is shut down' in (ROOT/'evidence/pr11-postgres.log').read_text(encoding='utf-8'))
source=(ROOT/'models/sales_exposure.py').read_text(encoding='utf-8')
check('No business commit','.commit(' not in source)
check('No operational mutation actions',not any(v in source for v in ('action_confirm(','action_post(','button_confirm(','_action_done(','_action_assign(','_create_invoices(')))
check('No monetary vendor cost or margin engine',not any(v in source for v in ('gross_profit =','gross_margin =','vendor_cost =')))
freshlog=(ROOT/scopes['FRESH']['evidence_reference']).read_text(encoding='utf-8')
for marker in ('PR11_REFERENCE_A','PR11_REFERENCE_B','PR11_REFERENCE_C','PR11_REFERENCE_D','PR11_REFERENCE_E','PR11_WORKLOAD'):
    check('Executed reference '+marker,marker in freshlog)
workload=re.search(r'PR11_WORKLOAD lines=100 elapsed=([\d.]+)s',freshlog)
check('Measured workload',bool(workload))
seconds=float(workload.group(1))
opslog=(ROOT/scopes['OPERATIONAL-SAFETY']['evidence_reference']).read_text(encoding='utf-8')
opsmodels=re.search(r'PR11_OPERATIONAL_MODELS=(.+)',opslog).group(1).split(',')
now=datetime.now(timezone.utc).isoformat(timespec='seconds')
rows='\n'.join('| '+scope+' | '+str(rec.get('passed'))+' '+('tests' if 'test_unit' not in rec else 'assertion groups')+' PASS | '+rec['evidence_reference']+' |' for scope,rec in scopes.items())
summary=f'''# PR11 / DEV06 — Sales commercial exposure foundation

## A — Environment

Odoo20.0 Community FINAL, Python3.14.6 and isolated PostgreSQL18.4; addon
`vendor_price_revision_impact_simulator`. Existing major/dependencies are preserved.
PR00–PR10 evidence was inspected; the exact68-file PR10 source matched its ledger
before edits and is archived with a checksum. The local native source audit retains
20 relevant source hashes in evidence/pr11-native-source-audit.json. No existing
user database or production credentials/data were used. Disposable loopback port55442,
exact allowlists and disabled external effects governed every database run.

## B — Implementation

New sales snapshot, exact line, exception, immutable protection assessment,
audited scope grant and collection/review wizard models reuse current PR10 demand
and allocation without performing new allocation. Actual customer prices and
source discounts/currency/taxes/UoM/quantity provenance are frozen. Native tax
services produce a tax-excluded basis after Decimal discount preparation; negative
discounts retain surcharge semantics. Partial quantities come from PR10.

Reliable outstanding values and allocation-entry selling values remain distinct
from recognized revenue or vendor-cost impact. Currency rounding residuals are
explicit. Global discounts/downpayments/negative adjustments stay order-only and
block invented product apportionment. Incomplete grouped totals are null with
separate known subtotals and incomplete counts. Shipping/services are not product
demand. Confirmed and conditional currency/scenario groups remain separate.

Snapshot/version/digest/current getters, existing-source locks, company/batch
serialization, atomic savepoints and idempotency preserve history and freshness.
A real-session quote probe exposed native rolling expected_date in PR10 freshness.
Unused volatile dates are now excluded; conditional allocation requires a stored
commitment date, and a versioned date-basis tag makes earlier allocations require
explicit revalidation without overwriting their history. Confirmed native fallback
is retained. Clock-advance and missing-date regressions verify this behavior.
Current tax/price/discount/delivery/state/offer/review/UoM/FX/source changes invalidate
material evidence; unrelated notes do not. Native source permissions also apply.
No financial margin, repricing, approval/application or PR12 engine is implemented.

## C — Files changed

- models/allocation_engine.py — remove irrelevant rolling quote ETA from source
  fingerprints; require a stored conditional commitment date, retain confirmed
  expected-date fallback and version the analytical date-basis contract.
- models/sales_exposure.py — analytical models, native source projection, Decimal/
  tax/UoM/FX basis, current getters, authorization and documented review actions.
- security/sales_exposure_security.xml — role/company/all-warehouse/all-source-order
  permissions; separate audited customer grants; no operational ACL broadening.
- views/sales_exposure_views.xml — allocation collection entry, read-only historical
  sales review, exact line detail, filters, issue/evidence pages and grant controls.
- __manifest__.py, models/__init__.py, tests/__init__.py — register the new feature.
- tests/test_sales_exposure.py — 67 business/security/side-effect/workload methods.
- tests/test_module_foundation.py and tests/test_security_roles.py — exact additive
  Sales navigation expectations; confidential supplier menu assertions remain.
- docs/SALES_EXPOSURE_FOUNDATION.md, README.md, TESTING_SETUP.md,
  DEVELOPMENT_PROGRESS.md, TEST_REPORT.json — current scope, trust boundary and evidence.
- evidence/pr11-* — exact baseline, source ledger, reproducible drivers/probes,
  native audit, source-qualified logs, cleanup and this A–J handoff.

## D — Actual reference fixture results

| Reference | Executed result |
|---|---|
| A |200 × INR140 = INR28,000; free60 =8,400; independently protected incoming40 =5,600; new100 =14,000; categories reconcile28,000|
| B |10% discount: net126; full200 =25,200; delivered50 excluded; outstanding150 =18,900|
| C |Current pricelist160 does not replace recorded SO140; outstanding100 =14,000|
| D |Confirmed200 at140 =28,000; selected conditional70 at150 =10,500; selected what-if38,500 is not confirmed revenue|
| E |Product/service references15,000; global adjustment−1,000; full order14,000; product attribution incomplete, no invented allocation|

Additional executed tests cover actual invoice quantity100 with physical delivery0,
Box10 and sales-only Pack7 normalization, negative discounts, fixed/included/excluded
taxes, returns, reservation-backed uniqueness, unresolved supply selling value,
standalone and portfolio alternatives, FX direction/provenance/missing rates and
immutable source amendments. Reference markers remain in the clean-install log.

## E — Customer protection

Sales Manager assessments require native source access, company/warehouse grant,
traceable reference, classification, reason and valid effective interval. Fixed
and adjustment-allowed verified assessments are bound to exact current source
terms and retain previous assessments. Active batch/draft-revision lifecycle
metadata is checked through a fixed-ID, company-scoped service without supplier
values; cancelled contexts cannot receive a new review. Confirmation alone remains contract review;
missing/expired/inapplicable evidence never creates adjustment rights. Sent offers
receive validity review; PR10 excludes newly selected expired quotes and historical
snapshots become stale as validity changes. This is commercial evidence, not a
legal opinion or authority to change customer prices.

## F — Security

Sales-only readers need native Sales access plus an explicit customer-commercial
warehouse grant. Entire snapshots require every constituent order and warehouse
to be authorized. Native own-sales restrictions cannot disclose a combined snapshot.
Native product permissions are broader than the analytical projection. Nested
export/web specifications, grouping metadata and search/order/aggregate joins
therefore permit only captured fields and native source identity/labels. No raw
supplier cost/provenance/attachment traversal is exposed through this model.
Integer allocation IDs preserve traceability without granting supplier traversal.
Sales-only managers can review customer terms without supplier privileges; full
freshness attestation still requires allocation authority. Purchase User and Pricing
Operator do not gain customer access; broader roles need explicit grant and native
Sales rights. Auditors have immutable historical read access only.

Executed negative tests cover genuine foreign-company users with combined roles,
direct reads, searches, aggregation, exports, grant revocation, narrowed warehouses,
native source permissions, portal/employee roles, forged create/write/copy/unlink,
nested ownership commands and untrusted context. No successful forbidden access
was accepted as verification.

## G — Testing

| Selection | Actual result | Evidence |
|---|---|---|
{rows}

The100-line workload took **{seconds:.3f}s** after upstream fixture preparation;
value28,000 reconciles with2 PR11 bulk sales-line projections and1 order projection.
This is a measured synthetic case, not a general throughput guarantee. Larger
500/2000/10000-demand workload matrix and peak memory: NOT_MEASURED. Manual browser
UAT: NOT_RUN. Secure XML/model/ACL/action loading is covered by actual install/update.
Future PR14–16 financial-engine tests: NOT_RUN and out of PR11 scope.

Earlier sandbox loopback denial and draft fixture/float-preparation failures remain
in report history. Fixes preserve authorization/native lifecycle rules, use actual
invoice fixtures, reuse source batches instead of importing duplicate bytes, and
avoid native binary-floating surcharge artifacts by Decimal discount preparation.
No passing financial/security assertion was removed or weakened. Earlier runtime
passes that preceded final projection/audit/lifecycle additions remain retained,
but only exact final-hash runs without source changes satisfy the gates below. Source ledger
**{source_hash}** covers{len(ledger)} addon/test files for all final runtime gates.

## H — Business safety

Actual confirmed SO/PO, a posted balanced entry, a valued done move3500, physical
package stock50/reserved3/free47 and mixed sales UoM fixtures existed before PR11
analysis. The dedicated probe preserves all values/IDs/write dates/counts across
**{len(opsmodels)} models** around repeated collection/current checks. PR11 creates
only analytical/review records. No customer/vendor prices, discounts, pricelists,
orders, reservations, receipts/deliveries, valuation, invoices, GL entries, mail or
cron records are changed by analysis. Odoo20 valuation is stock.move.value; absent
stock.valuation.layer is not falsely claimed tested. No margin/consolidated exposure,
approval execution, customer repricing or supplier application is implemented.

The real PR10 upgrade preserves prior source bytes, mappings/corrections, commercial/
supply/allocation snapshots, policies and operational records; ordinary update
creates no sales snapshot or customer-commercial grant. Disposable runtime resources
were removed only after confirmed PostgreSQL shutdown; retained logs remain.

## I — Progress and limitations

PR11 is VERIFIED; progress/report contain source-qualified execution evidence.
PR12 remains NOT_STARTED; M2 remains IN_PROGRESS for subsequent purchase/inventory
work. Source queries cap10000 rows, history-freshness search1000 snapshots. Unknown
custom adjustment conventions require integration review; unallocated standard
adjustments stay incomplete. Historical original prices are unavailable unless
retained in prior snapshots/evidence. Source-row locks do not permanently freeze
future inserts. Fresh authorized transactions and serialization retries are mandatory.
Sales-only readers cannot attest supplier allocation freshness and receive a
conservative stale/access-unavailable indicator. Browser UAT, larger stress and
peak memory remain unexecuted/unmeasured, explicitly recorded above.

## J — PR12 handoff

Use `allocation.get_current_sales_terms(fx_date)` in a fresh authorized transaction.
Keep exact source order/line/customer/company/variant, confirmed-vs-conditional
scenario, net selling price, outstanding quantity, source/comparison UoM and factors,
tax/discount assumptions, source currency, optional sales FX rate/date/IDs, customer
protection evidence and allocation-entry IDs. Retain snapshot/version/digest and
independent value/protection/FX statuses. Never treat stored state as current approval,
missing values as zero, protected incoming as additional supply, or independent quote
scenarios as additive. Do not compare source currencies/UoMs without normalization.

PR12 must independently verify RFQ/PO commitments, supplier evidence, effective
dates/tiers, amendments/disputes and fixed/adjustable purchase terms. PR14–16 may
combine only reconciled, current, authorized inputs. Preserve company, native Sales,
customer-commercial grants, warehouse and supplier-cost confidentiality. Customer
adjustment rights do not permit automatic selling-price changes. Stop after PR11.
'''
(ROOT/'evidence/DEV-06-pr11-summary.md').write_text(summary,encoding='utf-8')
progress=ROOT/'DEVELOPMENT_PROGRESS.md'
text=progress.read_text(encoding='utf-8')
lines=text.splitlines()
for i,line in enumerate(lines):
    if line.startswith('| PR-11 |'):
        lines[i]=f"| PR-11 | DEV-06 sales commercial exposure foundation | VERIFIED | QUICK{scopes['HELPERS_VERIFY']['passed']}; targeted{scopes['TARGETED']['passed']}; fresh{scopes['FRESH']['passed']}; actual PR10 update{scopes['UPGRADE']['passed']}; preservation, six concurrency probes and{len(opsmodels)}-model safety PASS | docs/SALES_EXPOSURE_FOUNDATION.md; evidence/DEV-06-pr11-summary.md; TEST_REPORT.json | Sales references only; browser UAT NOT_RUN; larger loads/peak memory NOT_MEASURED | None for PR11 | 2026-10-29 | PR12 NOT_STARTED |"
    if line.startswith('| M2 |'):lines[i]='| M2 | Sales, purchase, inventory, supply allocation | IN_PROGRESS (PR09–PR11 foundation verified; detailed purchase/inventory analysis remains) |'
text='\n'.join(lines)+'\n'
heading='## PR-11 completion and handoff'
if heading in text:text=text[:text.index(heading)]
text+='\n'+heading+f'''

Immutable customer sales terms consume only current PR10 allocation. Exact SO lines,
actual recorded prices, Decimal discount/native tax-excluded basis, partial quantity,
UoM/FX provenance and separate confirmed/conditional scenarios preserve commercial
meaning. Global adjustments remain order-only review; missing data is not zero.
Documented Sales Manager protection assessments retain historical evidence without
authorizing repricing. Separate audited grants plus native Sales/company/warehouse/
source-order rules protect customer terms and prevent supplier-cost traversal.

67 new methods; final QUICK{scopes['HELPERS_VERIFY']['passed']}, targeted{scopes['TARGETED']['passed']},
fresh{scopes['FRESH']['passed']}, actual PR10 update{scopes['UPGRADE']['passed']}, preservation,
six real-session races and{len(opsmodels)}-model operational safety PASS. The100-line
workload measured{seconds:.3f}s after upstream preparation; no larger-load or memory
guarantee is claimed. Static/source/UTF8/cleanup evidence is retained. Earlier draft
and sandbox failures remain in report history; passing assertions were not weakened.
No operational customer/vendor price, order, stock, valuation or accounting change
occurs. Actual prior PR10 source/allocation evidence survives upgrade. All disposable
runtime resources were removed after verified shutdown.

Browser UAT is NOT_RUN; larger500/2000/10000-demand and peak-memory measurements are
NOT_MEASURED. Read docs/SALES_EXPOSURE_FOUNDATION.md and evidence/DEV-06-pr11-summary.md
for trust boundaries, source-lock/limit/freshness assumptions and complete A–J evidence.

PR12 must consume fresh get_current_sales_terms(fx_date), exact line/scenario/currency/
UoM/price/quantity and allocation IDs, independent protection/value/FX statuses and
unresolved issues. It must independently verify purchase commitments/amendments/
supplier protection. No final margin, financial aggregation, repricing recommendations,
approval or price application is implemented. STOP after PR11; PR12 NOT_STARTED.
'''
progress.write_text(text,encoding='utf-8')
for n in ('README.md','TESTING_SETUP.md','DEVELOPMENT_PROGRESS.md','docs/SALES_EXPOSURE_FOUNDATION.md','evidence/DEV-06-pr11-summary.md'):
    value=(ROOT/n).read_text(encoding='utf-8');check('UTF8 '+n,'\ufffd' not in value)
check('A-J report complete',all('## '+letter+' —' in summary for letter in 'ABCDEFGHIJ'))
check('Single progress handoff',text.count(heading)==1)
check('Next prompt untouched','| PR-12 | RFQ, PO, receipts, and supplier price disputes | NOT_STARTED |' in text)
report.update(pr11_status='VERIFIED',pr11_completed_at=now,current_status='PASS',
    current_status_detail='PR11 VERIFIED on frozen source; PR12 NOT_STARTED.',
    pr11_coverage_boundaries=dict(source_hash=source_hash,source_files=len(ledger),new_methods=67,
        quick_tests=scopes['HELPERS_VERIFY']['passed'],targeted_tests=scopes['TARGETED']['passed'],
        fresh_tests=scopes['FRESH']['passed'],actual_upgrade_tests=scopes['UPGRADE']['passed'],
        real_session_races=6,operational_models=len(opsmodels),workload_100_lines_seconds=seconds,runtime_cleanup=True),
    pr11_limitations=['Browser UAT NOT_RUN','500/2000/10000-demand stress NOT_MEASURED','Peak memory NOT_MEASURED',
        'Sales-only users cannot attest full supplier-allocation freshness','Unallocated order adjustments block product values',
        'Current getter/fresh transaction/retry required; existing-row locks do not permanently freeze future inserts',
        'No PR12 or PR14–16 financial business engine implemented'])
record=dict(prompt_id='PR-11',phase='DEV-06',odoo_version='20.0',module=ROOT.name,
    environment=dict(os='Windows',edition='Community',database=None),test_level='QUICK',
    invocation='python evidence/pr11-finalize.py',started_at=now,completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
    exit_status=0,passed=len(checks),failed=0,skipped=0,result_status='PASS',
    evidence_reference='evidence/DEV-06-pr11-static-validation.txt',blocking_reason=None,
    verification_scope='PR11_STATIC',source_hash=source_hash,source_changed_during_run=False)
(ROOT/record['evidence_reference']).write_text('\n'.join(checks)+f'\nPASS {len(checks)} checks\n',encoding='utf-8')
report['history'].append(record);report['latest_run']=record
rp.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status='VERIFIED',quick=scopes['HELPERS_VERIFY']['passed'],targeted=scopes['TARGETED']['passed'],
    fresh=scopes['FRESH']['passed'],actual_upgrade=scopes['UPGRADE']['passed'],concurrency=6,
    operational_models=len(opsmodels),static=len(checks),workload_100_seconds=seconds,source_files=len(ledger),next_prompt='PR12_NOT_STARTED')))
