"""Source-qualified finalization; fail closed if any mandatory gate is absent."""
import ast
import hashlib
import json
import re
import zipfile
from datetime import datetime,timezone
from pathlib import Path
from lxml import etree

ROOT=Path(__file__).resolve().parents[1]
rp=ROOT/'TEST_REPORT.json';report=json.loads(rp.read_text(encoding='utf-8'))
ledger=json.loads((ROOT/'evidence/pr12-verified-source-sha256.json').read_text(encoding='utf-8'))
source_hash=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
checks=[]
def check(label,condition):
    assert condition,label
    checks.append(label)
for n,h in ledger.items():
    p=ROOT/n;check('Frozen source '+n,hashlib.sha256(p.read_bytes()).hexdigest()==h)
    if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'))
    if p.suffix=='.xml':etree.parse(str(p))
baseline=json.loads((ROOT/'evidence/pr11-verified-source-sha256.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(ROOT/'evidence/pr11-source-baseline.zip') as z:
    for n,h in baseline.items():check('Exact PR11 archive '+n,hashlib.sha256(z.read(n)).hexdigest()==h)
check('Baseline checksum',hashlib.sha256((ROOT/'evidence/pr11-source-baseline.zip').read_bytes()).hexdigest()==(ROOT/'evidence/pr11-source-baseline.sha256').read_text(encoding='utf-8').split()[0])
native_audit=json.loads((ROOT/'evidence/pr12-native-source-audit.json').read_text(encoding='utf-8'))
native_root=ROOT.parents[1]/'odoo-20.0'
for n,h in native_audit['files'].items():check('Verified native Odoo20 source '+n,hashlib.sha256((native_root/n).read_bytes()).hexdigest()==h)
gates={}
for scope in ('HELPERS_VERIFY','TARGETED','FRESH','UPGRADE','UPGRADE-PRESERVATION','CONCURRENCY','OPERATIONAL-SAFETY'):
    records=[r for r in report['history'] if r.get('verification_scope') in ({'PR12_UPGRADE','PR12_UPGRADE_VERIFY'} if scope=='UPGRADE' else {'PR12_'+scope})
        and r.get('result_status')=='PASS' and r.get('source_hash')==source_hash and r.get('source_changed_during_run') is False]
    check('Mandatory runtime gate '+scope,bool(records));gates[scope]=records[-1]
    check('Retained runtime evidence '+scope,(ROOT/records[-1]['evidence_reference']).is_file())
check('Disposable runtime removed',not list(ROOT.glob('.pr12*')))
check('PostgreSQL clean shutdown','database system is shut down' in (ROOT/'evidence/pr12-postgres.log').read_text(encoding='utf-8'))
source=(ROOT/'models/purchase_commitment.py').read_text(encoding='utf-8')
check('No business commits','.commit(' not in source)
check('No operational actions',not any(v in source for v in ('button_confirm(','button_cancel(','action_post(','_action_done(','_action_assign(','_create_invoices(')))
check('No margin/exposure engine',not any(v in source for v in ('gross_margin =','gross_profit =','total_financial_exposure =')))
fresh=(ROOT/gates['FRESH']['evidence_reference']).read_text(encoding='utf-8')
for marker in ('PR12_REFERENCE_A','PR12_REFERENCE_B','PR12_REFERENCE_C','PR12_REFERENCE_D','PR12_REFERENCE_E','PR12_WORKLOAD'):
    check('Executed financial reference '+marker,marker in fresh)
seconds=float(re.search(r'PR12_WORKLOAD lines=100 seconds=([\d.]+)',fresh).group(1))
ops=(ROOT/gates['OPERATIONAL-SAFETY']['evidence_reference']).read_text(encoding='utf-8')
models=re.search(r'PR12_OPERATIONAL_MODELS=(.+)',ops).group(1).split(',')
method_count=(ROOT/'tests/test_purchase_commitment.py').read_text(encoding='utf-8').count('    def test_')
now=datetime.now(timezone.utc).isoformat(timespec='seconds')
table='\n'.join('| '+scope+' | '+str(r.get('passed'))+' '+('assertion groups' if r.get('test_unit') else 'tests')+' PASS | '+r['evidence_reference']+' |' for scope,r in gates.items())
summary=f'''# PR12 / DEV06 — Purchase commitment commercial foundation

## A — Environment

Odoo20.0 Community FINAL, Python3.14.6 and PostgreSQL18.4. Addon:
`vendor_price_revision_impact_simulator`; existing base/product/purchase_stock/
sale_stock dependencies and repository major preserved. Local native source audit
retains12 hashes and actual fields/state/tax/billing contracts. PR00–PR11 evidence
was inspected; exact72-file PR11 source matched its verified ledger before changes
and was archived with a checksum. No existing user database or production data was
used. Loopback55443 disposable databases, exact runner allowlists, isolated filestores
and disabled external/email/cron/payment/live-accounting effects govern testing.

## B — Implementation

Immutable purchase snapshot/line/issue and reference-only supplier evidence models
capture exact RFQ/PO line identity, actual recorded source prices, discounts, taxes,
currency/UoM, confirmation/arrival dates and supplier references. Draft/sent/to-approve
remain conditional; purchase is confirmed, locked is a Boolean, cancelled excluded.
Core Purchase supplier-offer validity is unavailable, never invented.

Current PR09 supply buckets govern open/received/cancelled quantities, backorders,
returns and supplier receipt boundaries. PR12 does not rebuild that engine or infer
receipt from bills. Optional current PR10 exact single-scenario ledger links preserve
allocated and remaining open quantities without creating another supply allocation.
Unknown quantity is blank, not zero. Fully received/short-closed verified zero is
distinct. Supplier route/ownership uncertainty remains in PR09/PR10 evidence.

Native Odoo purchase tax base-lines plus Decimal discount input provide tax-excluded
goods references; PR08 validates UoM pairs. Source/company currencies and traceable
guarded FX are separate. Missing rates never become1:1. Original ordered quantity,
exact variant and effective interval select the current PR08 proposal tier; no
cross-order pooling occurs. Existing PO price is not replaced with supplierinfo.
Unallocated charges/services/negative adjustment lines block invented product values.

Confirmed open commercial values, conditional RFQ values and conditional proposal/
amendment differences remain distinctly labeled. Mixed currency totals are separated;
incomplete totals are null with known subtotal/count. A documented request120 and
general proposal115 remain separate scenarios. No disputed difference is accepted
payable, posted expense, realized loss or final financial exposure.

Maker-checker supplier evidence binds exact current commercial terms, reference,
reason, classification, reviewer and effective date basis/interval. Confirmation
alone is not fixed-price evidence. Latest unknown/stale evidence never revives older
favorable protection. Pending requests do not overwrite valid fixed rights. An
accepted-recorded assessment must match current PO price; it does not execute an
amendment. Existing compatible PR09 firm attestations are reused with provenance.

Optional linked bill/credit evidence uses native Accounting read permissions with
no sudo. Exact bill and bill-line record rules also restrict stored snapshots.
Comparable differences are read-only evidence; credit notes do not amend POs and
billed quantities do not substitute for physical receipt. Source/version/policy/
assessment changes make snapshots stale; unchanged inputs are idempotent. Historical
observations remain retained without inventing an original legal price. Atomic
savepoints, company/batch serialization and shared existing-source locks protect
publication. No business method commits.

## C — Files changed

- models/purchase_commitment.py — focused analytical models, bounded source service,
  normalization, source-current getters, independent evidence reviews and wizards.
- security/purchase_commitment_security.xml — company, cost warehouse, ownership,
  billing-detail/native exact-bill access and optional customer-demand scope rules.
- views/purchase_commitment_views.xml — collection/review forms, immutable histories,
  source detail, filters and optional billing evidence; no operational repricing.
- __manifest__.py, models/__init__.py, tests/__init__.py — register PR12 feature/tests.
- tests/test_purchase_commitment.py — {method_count} business/security/safety/workload tests.
- tests/test_module_foundation.py — exact additive menu identities.
- tests/test_sales_exposure.py — retain exact2-review/1-current-snapshot assertions
  scoped to their own source IDs, allowing preserved PR11 upgrade history. No
  business/security assertion is relaxed.
- docs/PURCHASE_COMMITMENT_EXPOSURE.md, README.md, TESTING_SETUP.md,
  DEVELOPMENT_PROGRESS.md, TEST_REPORT.json — trust contract, scope and honest evidence.
- evidence/pr12-* and evidence/pr11-source-baseline.* — exact baseline, source audit,
  reproducible verification/probes, frozen source hashes, logs and this report.

## D — Actual fixture reference results

| Reference | Actual executed result |
|---|---|
| A |100 ordered /40 received /60 open at INR100; full10,000, received4,000, open6,000; independently protected100; proposal115 does not reprice PO|
| B |Open60 at100 =6,000; hypothetical115 =6,900; conditional disputed900, never accepted payable|
| C |Supplier baseline100, negotiated PO95, proposal115; unit difference20 and conditional40-unit difference800; no substitute PO100|
| D |Draft RFQ70 at115 =8,050 conditional; no confirmed incoming, protected delivery or automatic confirmation|
| E |Billed60, received50, ordered100; PR09 open50; draft bill115 vs PO100 mismatch15; bill remains draft and PO unchanged|

Other executed cases cover backorders, fully received/short-close, returns, Input-to-
Stock nonadditive putaway, Box10 price/quantity conversion, negative discounts,
included taxes, guarded FX and missing FX, original quantity100 tier109 with open60,
request120 versus general proposal115, immutable earlier prices and exact company/
variant/warehouse isolation. Markers remain in the final clean-install log.

## E — Commercial protection and limitations

Supplier agreement references support fixed/adjustable/unknown and pending/disputed/
already-recorded amendment assessments. A different active Purchase Manager verifies
source-current proposed evidence, with a reason and scoped authority. Retained source
and validity digests prevent stale or expired protection. No supplier acknowledgement,
contract or legal original price is fabricated. Confirmation before effective date
plus arrival after it creates review, never automatic supplier price acceptance.
Legacy PR09 firm status and PR12 review evidence remain separately traceable; PR12
does not silently rewrite supply or allocation. Future consumers must inspect both.

No optional Purchase Agreement dependency is added. Core supplier-offer expiry is
not recorded. Reference-only documents are not copied into broadly accessible
attachments; original evidence keeps its existing ACL. Landed-cost/nonrecoverable
tax attribution belongs to later cost phases. Current tax-excluded goods price is
not claimed as complete inventory acquisition or payable cost.

## F — Security

Existing roles, mandatory selected company and every warehouse cost grant protect
headers/children/evidence. Purchase preparer ownership remains restricted; managers
review authorized drafts, auditors remain read-only, and Sales/portal/configuration
do not acquire confidential supplier terms. Optional PR10 customer quantities also
require demand grants. Native source opening independently checks PO access and
current company/warehouse. No broad operational administrator group is introduced.

Billing detail requires native account.move/account.move.line model authority AND
access to every exact source bill/line under native record rules. Detail-free scopes
remain separate. Revocation hides search/read/group/export history. Input wizards
permit only source identity labels and cannot export/nest/filter into confidential
native source fields. Computed user bill-ID metadata is self-user only, with acting-UID-dependent
cache keys; another user or forged context UID cannot enumerate another reviewer
bill scope. Public create/write/copy/unlink/nested ownership/context flags
cannot forge protected or verified results. Evidence verification enforces role,
company, current terms and independent checker server-side.

Executed negative tests include genuine CompanyB combined roles, CompanyA source
read/export/review denial, company and warehouse grants, Sales/portal/employee roles,
bill-model revocation, exact native bill-record rules, aggregation, direct ORM,
forged states, nested commands, untrusted context and wizard alternate traversal.

## G — Automated evidence

| Selection | Actual result | Retained evidence |
|---|---|---|
{table}

The first complete upgrade attempt ran451 tests (448 PASS,3 failures); it remains
FAIL in history. Final upgrade verification selects all PR12 tests, affected PR11
protection/snapshot cases, supply/allocation integrity, commercial/revision security
and module/view loading. The final selection has its own actual count in the table;
it is not represented as a451-test PASS. No unchanged earlier financial regression
is silently discarded.

All final gates match frozen{len(ledger)}-file source **{source_hash}** and record
no source changes during execution. Earlier draft ISO/Odoo datetime adapter and
fixture failures remain in report history. Native putaway transfers are selected
by exact company/product/Input/Stock source rather than assuming PO picking links;
native note field, role-first rejection and upstream-stale assertions are corrected
without weakening source quantities or permissions. Upgrade tests retain actual
PR11 history, so previous sales global-empty-table assumptions were corrected to
assert exactly2 reviews/1 current snapshot for the same source line/allocation.
Metadata impersonation is explicitly denied; no unrelated Accounting permission
is granted to return an empty relation. Maker-checker testing includes
a manager attempting to verify their own evidence. No passing assertion was removed. A final native user-model review also closed
a metadata impersonation path by making operational bill scope self-user-only.
Detail-free snapshots avoid empty native bill relation writes, which otherwise
incorrectly require Accounting ACLs.

The100-line workload measured **{seconds:.3f}s** for scoped refresh/collection after
fixture preparation; conditional value10,000 reconciles. Larger500/2000/10000-source
and peak memory: NOT_MEASURED. Manual browser UAT: NOT_RUN. Views/ACL/actions/models
loaded in actual installation/update. Future PR13/14 financial tests: NOT_RUN and
outside PR12 scope. Static/source/UTF8/cleanup validation is retained separately.

## H — Business safety

The dedicated safety probe starts with confirmed SO/PO, physical package stock50,
reserved3/free47, mixed-unit delivery demand3, valued done stock move3500 and a posted
balanced entry. PR12 repeated collection/current getters and supplier request
assessment preserve all original values/IDs/write dates/counts across **{len(models)}
operational/master/mail/cron/package models**. No PO/SO price/quantity/state change,
supplierinfo/product cost write, receipt/reservation mutation, bill posting/payment,
stock valuation change or accounting entry occurs from analytical actions.
Odoo20 stock.move.value is the native valuation source; absent stock.valuation.layer
is not falsely claimed tested. No final exposure/margin/repricing/application or
operational amendment-approval engine is implemented.

Actual PR11 update preserves source attachment bytes, corrections/mappings,
commercial/supply/allocation snapshots and customer sales snapshots/reviews, policies
and existing operational records. Ordinary update creates no purchase snapshots.
The cold baseline was captured before PR12 schema registration. Disposable runtime
resources were removed after confirmed shutdown; retained logs remain.

## I — Progress

PR12 is VERIFIED; TEST_REPORT.json and DEVELOPMENT_PROGRESS.md retain actual evidence.
M2 remains IN_PROGRESS for inventory cost work. Source/evidence/history bounds10000
fail without partial publication; freshness filtering caps1000 histories. Native
billing scope over10000 sources fails closed. Existing-row locks do not permanently
freeze future inserts; fresh authorized transactions and serialization retry are
required. Browser UAT/larger stress/memory remain explicitly unexecuted/unmeasured.
PR13 stays NOT_STARTED. The next stage requires a separate instruction after
this PR12 handoff.

## J — PR13 handoff

Use `batch.get_current_purchase_terms(warehouse_ids, include_rfqs, allocation_id,
include_bills, fx_date, comparison_date)` in a fresh authorized transaction. Retain
snapshot/version/digest, exact vendor/company/variant/PO line, PR09 bucket and receipt
boundary IDs, quantities/source-comparison UoM, recorded/protected/proposed/request
price distinctions, currency/common FX date/rate IDs, date/tier/policy evidence and
independent quantity/value/protection/amendment/billing statuses. PR10 references
represent one scenario; protected incoming is a subset, not extra supply. Missing
cost or quantity is not zero. Pending disputes do not alter fixed rights or authorize
payable increases. Never sum independent amendment or quotation alternatives.

PR13 must independently establish inventory cost method, valuation confidence,
landed-cost assumptions, replacement-source applicability and source-level quantity/
cost reconciliation. Respect company, cost warehouse, native source/accounting,
exact-bill and customer-demand grant boundaries. PR12 references are not stock
valuation or final financial exposure. Stop after PR12; PR13 NOT_STARTED.
'''
(ROOT/'evidence/DEV-06-pr12-summary.md').write_text(summary,encoding='utf-8')
p=ROOT/'DEVELOPMENT_PROGRESS.md';text=p.read_text(encoding='utf-8');rows=text.splitlines()
for i,row in enumerate(rows):
    if row.startswith('| PR-12 |'):rows[i]=f"| PR-12 | DEV-06 RFQ/PO purchase commitment evidence | VERIFIED | QUICK{gates['HELPERS_VERIFY']['passed']}; targeted{gates['TARGETED']['passed']}; fresh{gates['FRESH']['passed']}; actual PR11 update{gates['UPGRADE']['passed']}; preservation, six real-session races and{len(models)}-model safety PASS | docs/PURCHASE_COMMITMENT_EXPOSURE.md; evidence/DEV-06-pr12-summary.md; TEST_REPORT.json | Commercial references only; browser UAT NOT_RUN; larger stress/memory NOT_MEASURED | None for PR12 | 2026-10-29 | PR13 NOT_STARTED |"
    if row.startswith('| M2 |'):rows[i]='| M2 | Sales, purchase, inventory, supply allocation | IN_PROGRESS (PR09–PR12 verified; inventory cost attribution remains) |'
text='\n'.join(rows)+'\n';heading='## PR-12 completion and handoff'
if heading in text:text=text[:text.index(heading)]
text+='\n'+heading+f'''

Exact recorded RFQ/PO commercial terms reuse PR09 authoritative incoming quantities
and optional current PR10 scenario attribution. Conditional RFQs, source-currency
open commitment references and disputed amendment scenarios remain separate.
Independent supplier assessments preserve dates/references/current terms without
approving PO edits. Optional native-authorized bill/credit references never replace
receipt quantities. Company/cost/native-billing/demand scope and immutable evidence
protect confidentiality. No operational purchase/stock/accounting mutation occurs.

{method_count} new methods; final QUICK{gates['HELPERS_VERIFY']['passed']}, targeted{gates['TARGETED']['passed']},
fresh{gates['FRESH']['passed']}, actual PR11 update{gates['UPGRADE']['passed']}, preservation,
six real-session races and{len(models)}-model operational safety PASS.100-line scoped
refresh/collection measured{seconds:.3f}s; larger workloads/peak memory NOT_MEASURED,
browser UAT NOT_RUN. Exact72-file PR11 archive and frozen{len(ledger)}-source final
ledger identify real evidence. Earlier ISO/fixture/stale-expectation failures are
retained; no passing business/security assertion was weakened. Prior PR11 sales
snapshots/reviews, source bytes, mappings, commercial/supply/allocation evidence and
actual confirmed/reserved/valued/posted records survive update. Disposable runtime
resources removed after confirmed shutdown.

Read docs/PURCHASE_COMMITMENT_EXPOSURE.md and evidence/DEV-06-pr12-summary.md for
complete A–J evidence, trust boundaries and source limits. PR13 must call fresh
get_current_purchase_terms(...) and retain exact bucket/line/entry IDs, quantity,
currency/UoM/date/tier/FX, agreed/protected/proposed/request distinctions and every
independent completeness/evidence status. It must independently verify inventory
cost sources and landed/replacement basis. No PR13 cost attribution, final exposure,
margin, repricing, approval execution or price application is implemented.
STOP after PR12; PR13 remains NOT_STARTED.
'''
p.write_text(text,encoding='utf-8')
for n in ('README.md','TESTING_SETUP.md','DEVELOPMENT_PROGRESS.md','docs/PURCHASE_COMMITMENT_EXPOSURE.md','evidence/DEV-06-pr12-summary.md'):
    check('Valid UTF8 '+n,'\ufffd' not in (ROOT/n).read_text(encoding='utf-8'))
check('Complete A-J report',all('## '+letter+' —' in summary for letter in 'ABCDEFGHIJ'))
check('Single PR12 handoff',text.count(heading)==1)
check('PR13 not started','| PR-13 | Inventory replacement cost analysis | NOT_STARTED |' in text)
record=dict(prompt_id='PR-12',phase='DEV-06',odoo_version='20.0',module=ROOT.name,
    environment=dict(os='Windows',edition='Community',database=None),test_level='QUICK',
    invocation='python evidence/pr12-finalize.py',started_at=now,completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
    exit_status=0,passed=len(checks),failed=0,skipped=0,result_status='PASS',evidence_reference='evidence/DEV-06-pr12-static-validation.txt',
    blocking_reason=None,verification_scope='PR12_STATIC',source_hash=source_hash,source_changed_during_run=False)
(ROOT/record['evidence_reference']).write_text('\n'.join(checks)+f'\nPASS {len(checks)} checks\n',encoding='utf-8')
report.update(pr12_status='VERIFIED',pr12_completed_at=now,current_status='PASS',current_status_detail='PR12 VERIFIED on frozen source; PR13 NOT_STARTED.',
    pr12_coverage_boundaries=dict(source_hash=source_hash,source_files=len(ledger),new_methods=method_count,
        quick=gates['HELPERS_VERIFY']['passed'],targeted=gates['TARGETED']['passed'],fresh=gates['FRESH']['passed'],
        actual_upgrade=gates['UPGRADE']['passed'],real_session_races=6,operational_models=len(models),workload_100_seconds=seconds,runtime_cleanup=True),
    pr12_limitations=['Browser UAT NOT_RUN','500/2000/10000-source benchmarks NOT_MEASURED','Peak memory NOT_MEASURED',
        'No fabricated supplier-offer validity or historical original price','Unallocated charges block product attribution',
        'Fresh transaction/current getter/retry mandatory; existing-row locks do not permanently freeze future inserts',
        'No PR13 or later inventory-cost/financial/repricing/approval/application engine implemented'])
report['history'].append(record);report['latest_run']=record;rp.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status='VERIFIED',source_files=len(ledger),methods=method_count,quick=gates['HELPERS_VERIFY']['passed'],
    targeted=gates['TARGETED']['passed'],fresh=gates['FRESH']['passed'],actual_upgrade=gates['UPGRADE']['passed'],concurrency=6,
    operational_models=len(models),static=len(checks),workload_100_seconds=seconds,next_prompt='PR13_NOT_STARTED')))
