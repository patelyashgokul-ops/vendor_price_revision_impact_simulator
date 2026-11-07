"""Fail-closed PR15 handoff, generated only from actual matching-source evidence."""
import ast
import hashlib
import json
import re
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from lxml import etree

r=Path(__file__).resolve().parents[1]
started=datetime.now(timezone.utc).isoformat(timespec='seconds')
report=json.loads((r/'TEST_REPORT.json').read_text(encoding='utf-8'))
ledger=json.loads((r/'evidence/pr15-verified-source-sha256.json').read_text(encoding='utf-8'))
sha=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
checks=[]
def check(label,condition):
    assert condition,label
    checks.append(label)
for name,value in ledger.items():
    p=r/name;check('Final source '+name,hashlib.sha256(p.read_bytes()).hexdigest()==value)
    if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8'))
    if p.suffix=='.xml':etree.parse(str(p))
baseline=json.loads((r/'evidence/pr14-verified-source-sha256.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(r/'evidence/pr14-source-baseline.zip') as z:
    for name,value in baseline.items():
        check('Exact PR14 archive '+name,hashlib.sha256(z.read(name)).hexdigest()==value)
        if name not in ('__manifest__.py','models/__init__.py','tests/__init__.py'):
            check('Prior business/security/test unchanged '+name,ledger[name]==value)
check('Baseline archive checksum',hashlib.sha256((r/'evidence/pr14-source-baseline.zip').read_bytes()).hexdigest()==(r/'evidence/pr14-source-baseline.sha256').read_text(encoding='utf-8').split()[0])
gates={}
for scope in ('FRESH','HELPERS_VERIFY','TARGETED','UPGRADE','UPGRADE-PRESERVATION','CONCURRENCY','OPERATIONAL-SAFETY'):
    scopes={'PR15_UPGRADE','PR15_UPGRADE_VERIFY'} if scope=='UPGRADE' else {'PR15_'+scope}
    rows=[x for x in report['history'] if x.get('verification_scope') in scopes and x.get('source_hash')==sha and x.get('source_changed_during_run') is False]
    check('Final-source gate '+scope,bool(rows) and rows[-1]['result_status']=='PASS')
    gates[scope]=rows[-1]
    check('Nonempty real test/probe count '+scope,rows[-1].get('passed',0)>0)
    check('Retained evidence '+scope,(r/rows[-1]['evidence_reference']).is_file())
check('Runtime removed',not list(r.glob('.pr15*')))
check('Server shutdown retained','database system is shut down' in (r/'evidence/pr15-postgres.log').read_text(encoding='utf-8'))
source=(r/'models/profitability.py').read_text(encoding='utf-8')
check('No native business CRUD',not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('create','write','unlink','sudo','commit') for n in ast.walk(ast.parse(source))))
check('No commercial/accounting/stock actions',not any(v in source for v in ('action_confirm(', 'button_confirm(', 'action_post(', '_action_done(', 'standard_price =')))
check('Upstream cost authority reused','get_current_financial_exposure(**f.scope)' in source)
check('PR11 revenue reused','nullable(source.company_sales_value)' in source)
check('No duplicate upstream publisher',not any(v in source for v in ('action_run_allocation(', 'action_collect_supply(', 'action_collect_sales_terms(', 'action_calculate_financial_exposure(')))
ops=(r/gates['OPERATIONAL-SAFETY']['evidence_reference']).read_text(encoding='utf-8')
for marker in ('PR15_UPSTREAM_IMMUTABILITY=PASS nine','PR15_PORTAL_PUBLIC=PASS','PR15_OPERATIONAL_SAFETY=PASS'):
    check('Actual probe '+marker,marker in ops)
models=re.search('PR15_OPERATIONAL_MODELS=(.+)',ops).group(1).split(',')
check('22 native models unchanged',len(models)==22)
fresh=(r/gates['FRESH']['evidence_reference']).read_text(encoding='utf-8')
check('Actual reference integration executed','PR15_REFERENCE revenue28000' in fresh)
seconds=float(re.search(r'PR15_WORKLOAD affected_lines=100 seconds=([\d.]+)',fresh).group(1))
race=(r/gates['CONCURRENCY']['evidence_reference']).read_text(encoding='utf-8')
race_names=re.findall(r'PR15_CONCURRENT_([A-Z_]+)=PASS',race)
check('Nine real-session races',len(race_names)==9)
methods=(r/'tests/test_profitability.py').read_text(encoding='utf-8').count('    def test_')
changes=[n for n,v in ledger.items() if baseline.get(n)!=v]
table='\n'.join('| '+k+' | PASS: '+str(v['passed'])+' '+('tests' if k in ('FRESH','HELPERS_VERIFY','TARGETED','UPGRADE') else 'probe groups')+' | '+v['evidence_reference']+' |' for k,v in gates.items())
failures=[x for x in report['history'] if x.get('prompt_id')=='PR-15' and x.get('result_status') in ('FAIL','BLOCKED')]
history='\n'.join('- '+x['result_status']+': '+(str(x['passed'])+' passed, '+str(x['failed'])+' failed' if x.get('passed') is not None else 'no completed test count; intentionally interrupted')+'; '+str(x.get('evidence_reference')) for x in failures) or 'No completed failed PR15 runs.'
summary=f'''# APP06 PR15 / DEV08 - implementation, testing and PR16 handoff

## A - Environment and prerequisite audit

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4, Windows. Addon
vendor_price_revision_impact_simulator. Native release source and retained PR00-14
PASS evidence checked before edits (evidence/pr15-predevelopment-audit.json).
Official [Community builds](https://nightly.odoo.com/) confirm20 stable. The existing
major is preserved. Optional Community sale_margin computes document margin from
purchase_price and document quantities; it does not represent this allocated future
vendor-revision scenario. No dependency on it/Enterprise, no native margin writes.
All runtime tests use newly created allowlisted synthetic disposable databases on
loopback55446; no production database or credentials used.

## B - Implementation

Immutable margin.snapshot/line/aggregate/risk models reuse current PR11 net sales
values and PR14 source-specific baseline/revised costs. Exact selected company,
order/line, variant, quantity/UoM, demand class, currency and allocation contribution
identity are checked. Revenue remains unchanged; no alternate price or valuation
calculation. Gross profit = revenue-cost; gross margin = profit/positive revenue.
Markup is separate and unused. Signed profit change reconciles to negative PR14
delta, reduction is baseline profit minus revised, erosion uses percentage points.
Relative reduction/decline require positive valid baselines. Decimal38 precedes
display rounding; risk uses raw values. Zero/negative revenue percentages stay null,
negative profits and margins below-100% remain visible. Missing values are not zero.

Exact sales lines are retained, with order/product.product/source-customer/company
amount-sum aggregates separated by confirmed/conditional class. Margins are ratios
of amount sums, never average percentages. Scope is affected remaining products,
not full-order margin. Unknown global adjustments remain incomplete under PR11.
Partial subset amounts are separately labeled. Conditional scenarios require the
exact current confirmed profitability baseline and expose scenario revised profit
minus confirmed revised profit only when complete; alternatives are never additive.

PR04 is the only risk authority. Existing minimum/target margin and company-currency
exposure bands are reused. Same governed margin rows now support explicit material
erosion pp and negative-profit critical settings, with existing configuration role,
audit, immutable publication and version controls. Product/category precedence is
preserved; company default is used for order/customer/company aggregate policy.
Highest known line severity remains separate from aggregate ratio risk; healthy
aggregate margins cannot hide a critical constituent. Readable source labels,
snapshot dates and stored-assessment warnings support review.
Every triggered reason retains stage, actual, threshold, policy ID and confidence.
Baseline risk is separate from revised risk and revision-induced deterioration.
Snapshots are immutable, source/policy fingerprinted, versioned and idempotent.
Current getters, company/batch serialization, shared source locks and atomic
savepoints prevent mixed publication. No business commits or sudo projections.

## C - Actual files changed

{chr(10).join('- '+n for n in changes)}

docs/PROFITABILITY_MARGIN_RISK.md documents the contract. TESTING_SETUP.md,
TEST_REPORT.json and DEVELOPMENT_PROGRESS.md contain setup, actual evidence and
status. evidence/pr15-* contains drivers, exact baseline archive/checksum, probes,
source ledger and full logs. Prior business/security tests remain unchanged.

## D - Executed reference results

| Item | Actual fixture result |
|---|---:|
| Unchanged net revenue | INR28,000 |
| Baseline / revised cost | INR20,000 /21,500 |
| Baseline / revised gross profit | INR8,000 /6,500 |
| Signed profit change / reduction | INR-1,500 /+1,500 |
| Baseline / revised margin | 28.57142857% /23.21428571% |
| Displayed margins | 28.57% /23.21% |
| Margin erosion | 5.35714286 percentage points |
| Relative profit reduction | 18.75% |
| Primary risk / revision effect | warning /new_warning |

These are actual synthetic PR11/14/15 integration results, not realized accounting
profit. Procurement assumptions keep the reference scenario_only. Verified
numerical arithmetic does not upgrade hypothetical procurement to actuals.

## E - Risk results and completeness

Reference company minimum15% is inclusive critical, target25% inclusive warning;
material erosion5pp is inclusive for positive deterioration, exposure band low.
LOW_REVISED_MARGIN and MATERIAL_MARGIN_EROSION both trigger; baseline margin is
above target and revised is warning. No minimum-margin critical breach in this
reference. Raw unrounded values determine boundaries. Tests cover14.99/15/15.01
and24.99/25/25.01, negative profits, extreme negative margin and overlapping flags.
Exposure uses existing [minimum,maximum) company-currency bands, never hardcoded INR.
Negative/minimum critical precedes high exposure, warning and normal. Incomplete
required inputs/policy/percentage yield review_required; independently known severe
flags remain visible. Estimated/scenario bases remain distinct from fully verified.

Pre-existing margin risk is compared with revised margin risk. New warning/critical,
warning-to-critical, existing critical worsened/unchanged, improvement and
undetermined classifications retain their explanations. Fixed verified customer
terms add context when profit falls; unknown flexibility remains explicit and never
authorizes a price change. Financial currentness and policy relevance are checked
separately; unrelated future policy publication does not stale the current period.

## F - Security

Raw costs and derived profit/margin/risk have the same protected boundary. Selected
company, active user, all cost/supply/demand warehouse grants, customer-commercial
grants and native access to every included order apply to headers and children.
Sales-only cannot infer vendor costs through margin; Purchase-only does not gain
customer terms. Auditor read-only; portal/public denied. Direct read/export/group,
immutable/nested/context forgery, foreign-company and revoked-scope checks execute.
Native sales drilldown reuses PR11 permission checks. No new privilege projection.

## G - Actual testing

| Gate | Actual final-source result | Evidence |
|---|---|---|
{table}

{methods} new test methods. Historical PR15 failures and intentionally interrupted
runs remain retained. Earlier source-changed candidate runs are development
evidence only; only the final-source gates above establish verification:

{history}

Actual PR14 archived84-source installation, committed cold capture before margin
schema creation, PR15 update and retained-field/source-byte preservation verify
upgrade safety including existing financial exposure. Nine real-session races:
{', '.join(race_names)}. The policy race tests governed future-period publication
serialization and current-period non-invalidation; relevant policy staleness is
separately tested. No passing earlier business/security assertions were weakened.
100 affected-line calculation measured{seconds:.3f}s after upstream preparation.
500/2000/10000 inputs and peak memory NOT_MEASURED; manual browser UAT NOT_RUN.
No release-wide FULL or PR16 sign-off claim.

## H - Business safety

The native22-model fixture proves no SO price/status, vendor rule, PO, pricelist,
reservation, stock valuation, product/accounting or mail/cron changes. Nine upstream
analytical models remain unchanged by profitability. Synthetic native writes only
prepare disposable fixtures or intentional competing changes. The business service
does not create/modify native records, post entries, approve, reprice or apply prices.
Disposable runtime removed after confirmed shutdown.

## I - Progress and limitations

PR15 VERIFIED for the documented projected profitability/risk scope. Final source
ledger {len(ledger)} files SHA256 {sha}. TEST_REPORT.json and DEVELOPMENT_PROGRESS.md
updated with real evidence. Missing warehouse/lot FIFO lineage, future landed costs,
unallocated sales adjustments/FX/costs and uncertain PO amendments retain upstream
limitations. No full-order discount/service allocation or commercial-parent rollup.
Browser UAT and larger workloads/memory remain unverified. PR16 NOT_STARTED.

## J - PR16 handoff

Use get_current_profitability only with current compatible PR11/14 source evidence
in a fresh authorized transaction. Retain exact company/customer/order/line/variant,
allocation/cost contribution IDs, currency/UoM, scenario/demand class and versions,
unchanged net revenue, baseline/revised costs, incremental exposure, profits,
margin percentages, erosion pp, signed profit change/reduction, relative ratios,
amount-sum aggregation keys, policy versions, reasons and independent completeness.
Partial/estimated/scenario-only values and unknown discount/FX/cost inputs cannot
become verified full totals or realized outcomes. Honor all confidentiality and
no-double-counting invariants. PR16 must independently reconcile full-source scope
before any sign-off foundation; no sign-off, approvals, pricing recommendations,
repricing, supplier application or accounting execution implemented here.
STOP after PR15.
'''
(r/'evidence/DEV-08-pr15-summary.md').write_text(summary,encoding='utf-8')
(r/'evidence/DEV-08-pr15-static-validation.txt').write_text('\n'.join('PASS '+s for s in checks)+f'\nTOTAL_CHECKS={len(checks)}\nSOURCE_HASH={sha}\n',encoding='utf-8')
now=datetime.now(timezone.utc).isoformat(timespec='seconds')
record=dict(prompt_id='PR-15',phase='DEV-08',odoo_version='20.0',module=r.name,environment=dict(os='Windows',edition='Community',database=None),test_level='QUICK',invocation='python evidence/pr15-finalize.py',started_at=started,completed_at=now,exit_status=0,passed=len(checks),failed=0,skipped=0,result_status='PASS',evidence_reference='evidence/DEV-08-pr15-static-validation.txt',blocking_reason=None,verification_scope='PR15_FINAL_STATIC',source_hash=sha,source_changed_during_run=False,test_unit='static_assertion_groups')
report['history'].append(record);report['latest_run']=record;report['current_status']='PASS';report['current_status_detail']='PR15 VERIFIED: projected profitability and margin risk; PR16 NOT_STARTED.'
report['pr15_handoff']=dict(status='VERIFIED',summary='evidence/DEV-08-pr15-summary.md',source_hash=sha,source_files=len(ledger),source_ledger='evidence/pr15-verified-source-sha256.json',benchmark=dict(affected_lines=100,seconds=seconds,larger_loads='NOT_MEASURED',peak_memory='NOT_MEASURED'),not_run=['manual browser UAT'],business_mutations=False,next_prompt='PR-16 NOT_STARTED')
(r/'TEST_REPORT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
p=r/'DEVELOPMENT_PROGRESS.md';progress=p.read_text(encoding='utf-8')
progress=progress.replace('| M3 | Financial exposure, margin, what-if | IN_PROGRESS; PR14 verified, later margin/what-if pending |', '| M3 | Financial exposure, margin, what-if | IN_PROGRESS; PR14-15 verified; later reconciliation/scenarios pending |')
progress=re.sub(r'^\| PR-15 \|.*$',f"| PR-15 | DEV-08 projected profitability and margin risk | VERIFIED | QUICK{gates['HELPERS_VERIFY']['passed']}; TARGETED{gates['TARGETED']['passed']}; fresh{gates['FRESH']['passed']}; actual PR14 update{gates['UPGRADE']['passed']}; preservation, nine races, 22-native/nine-upstream safety PASS | evidence/DEV-08-pr15-summary.md; TEST_REPORT.json | Projected affected scope; browser UAT NOT_RUN; larger loads/memory NOT_MEASURED | None for documented scope | 2026-10-29 | STOP after PR15; PR16 NOT_STARTED |",progress,flags=re.M)
progress+='\n\n## PR15 completion and PR16 handoff\n\nProjected profit, margin, signed change/reduction and pp erosion reuse exact PR11/14\nsources. Governed PR04 margin/exposure policies and added erosion/negative-profit\ndimensions classify baseline/revised risk with independent confidence/completeness.\nExact sales lines and amount-sum order/product/customer/company groups preserve\nconfirmed/conditional scopes. Immutable, versioned, current-source snapshots protect\nderived cost confidentiality. No native commercial/stock/accounting mutations.\n\nSee evidence/DEV-08-pr15-summary.md for complete A-J actual evidence and limitations.\nFinal source '+sha+'. Runtime removed after confirmed shutdown.\nPR16 full-source reconciliation/sign-off, repricing, approvals and application are\nnot implemented. STOP after PR15. PR16 remains NOT_STARTED.\n'
p.write_text(progress,encoding='utf-8')
print('PR15_FINAL_STATIC=PASS checks='+str(len(checks)))
print('PR15_SOURCE='+sha)
