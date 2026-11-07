"""Fail-closed PR16 handoff, generated only from actual matching-source evidence."""
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
ledger=json.loads((r/'evidence/pr16-verified-source-sha256.json').read_text(encoding='utf-8'))
sha=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
checks=[]
def check(label,condition):
    assert condition,label
    checks.append(label)
for name,value in ledger.items():
    p=r/name;check('Final source '+name,hashlib.sha256(p.read_bytes()).hexdigest()==value)
    if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8'))
    if p.suffix=='.xml':etree.parse(str(p))
baseline=json.loads((r/'evidence/pr15-verified-source-sha256.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(r/'evidence/pr15-source-baseline.zip') as z:
    for name,value in baseline.items():
        check('Exact PR15 archive '+name,hashlib.sha256(z.read(name)).hexdigest()==value)
        if name not in ('__manifest__.py','models/__init__.py','tests/__init__.py','tests/test_profitability.py'):
            check('Prior business/security/test unchanged '+name,ledger[name]==value)
    old=z.read('tests/test_profitability.py').decode('utf-8').replace('\r\n','\n')
    new=(r/'tests/test_profitability.py').read_text(encoding='utf-8')
    old_method=next(n for c in ast.parse(old).body if isinstance(c,ast.ClassDef) and c.name=='TestProfitabilitySnapshots' for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='test_failed_publication_rolls_back_header_lines_and_reasons')
    new_method=next(n for c in ast.parse(new).body if isinstance(c,ast.ClassDef) and c.name=='TestProfitabilitySnapshots' for n in c.body if isinstance(n,ast.FunctionDef) and n.name==old_method.name)
    old_lines=old.splitlines(keepends=True);new_lines=new.splitlines(keepends=True)
    check('Only seed-aware atomicity test changed',old_lines[:old_method.lineno-1]+new_lines[new_method.lineno-1:new_method.end_lineno]+old_lines[old_method.end_lineno:]==new_lines)
    check('Atomicity now retains all prior record values',all(v in ast.get_source_segment(new,new_method) for v in ('before=retained()', 'self.assertEqual(retained(),before)', "('batch_id','=',f.batch_id.id)", "side_effect=UserError('Injected PR15 publication failure')")))
check('Baseline archive checksum',hashlib.sha256((r/'evidence/pr15-source-baseline.zip').read_bytes()).hexdigest()==(r/'evidence/pr15-source-baseline.sha256').read_text(encoding='utf-8').split()[0])
gates={}
for scope in ('FRESH','HELPERS_VERIFY','TARGETED','UPGRADE','UPGRADE-PRESERVATION','CONCURRENCY','OPERATIONAL-SAFETY'):
    scopes={'PR16_UPGRADE','PR16_UPGRADE_VERIFY'} if scope=='UPGRADE' else {'PR16_'+scope}
    rows=[x for x in report['history'] if x.get('verification_scope') in scopes and x.get('source_hash')==sha and x.get('source_changed_during_run') is False]
    check('Final-source gate '+scope,bool(rows) and rows[-1]['result_status']=='PASS')
    gates[scope]=rows[-1]
    check('Nonempty real test/probe count '+scope,rows[-1].get('passed',0)>0)
    check('Retained evidence '+scope,(r/rows[-1]['evidence_reference']).is_file())
check('Runtime removed',not list(r.glob('.pr16*')))
check('Server shutdown retained','database system is shut down' in (r/'evidence/pr16-postgres.log').read_text(encoding='utf-8'))
source=(r/'models/reconciliation.py').read_text(encoding='utf-8')
check('No native business CRUD',not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('create','write','unlink','sudo','commit') for n in ast.walk(ast.parse(source))))
check('No commercial/accounting/stock actions',not any(v in source for v in ('action_confirm(', 'button_confirm(', 'action_post(', '_action_done(', 'standard_price =')))
check('Current upstream authority reused','get_current_profitability(**m.scope)' in source)
check('PR11 revenue independently cross-checked','SALES_NET_UNIT_EXTENSION' in source and 'REVENUE_SOURCE_MATCH' in source)
check('No duplicate upstream publisher',not any(v in source for v in ('action_run_allocation(', 'action_collect_supply(', 'action_collect_sales_terms(', 'action_calculate_financial_exposure(')))
ops=(r/gates['OPERATIONAL-SAFETY']['evidence_reference']).read_text(encoding='utf-8')
for marker in ('PR16_UPSTREAM_IMMUTABILITY=PASS thirteen','PR16_PORTAL_PUBLIC=PASS','PR16_OPERATIONAL_SAFETY=PASS'):
    check('Actual probe '+marker,marker in ops)
models=re.search('PR16_OPERATIONAL_MODELS=(.+)',ops).group(1).split(',')
check('22 native models unchanged',len(models)==22)
fresh=(r/gates['FRESH']['evidence_reference']).read_text(encoding='utf-8')
check('Actual reference integration executed','PR16_REFERENCE demand200' in fresh)
workload_log=fresh if 'PR16_WORKLOAD lines=100' in fresh else (r/gates['UPGRADE']['evidence_reference']).read_text(encoding='utf-8')
seconds=float(re.search(r'PR16_WORKLOAD lines=100 seconds=([\d.]+)',workload_log).group(1))
reference_checks=int(re.search(r'PR16_REFERENCE.*checks=(\d+)',fresh).group(1))
workload_checks=int(re.search(r'PR16_WORKLOAD.*controls=(\d+)',workload_log).group(1))
race=(r/gates['CONCURRENCY']['evidence_reference']).read_text(encoding='utf-8')
race_names=re.findall(r'PR16_CONCURRENT_([A-Z_]+)=PASS',race)
check('Nine real-session races',len(race_names)==9)
methods=(r/'tests/test_reconciliation.py').read_text(encoding='utf-8').count('    def test_')
changes=[n for n,v in ledger.items() if baseline.get(n)!=v]
integration=json.loads((r/'evidence/pr16-business-milestone-source-sha256.json').read_text(encoding='utf-8'))
integration_hash=hashlib.sha256(json.dumps(integration,sort_keys=True).encode()).hexdigest()
for name,value in integration.items():
    if name!='tests/test_profitability.py':check('Broad milestone source unchanged '+name,ledger[name]==value)
broad=[x for x in report['history'] if x.get('verification_scope')=='PR16_UPGRADE' and x.get('source_hash')==integration_hash]
check('Retained broad milestone failure evidence',bool(broad) and broad[-1]['result_status']=='FAIL' and broad[-1]['passed']==347 and broad[-1]['failed']==1)
table='\n'.join('| '+k+' | PASS: '+str(v['passed'])+' '+('tests' if k in ('FRESH','HELPERS_VERIFY','TARGETED','UPGRADE') else 'probe groups')+' | '+v['evidence_reference']+' |' for k,v in gates.items())
failures=[x for x in report['history'] if x.get('prompt_id')=='PR-16' and x.get('result_status') in ('FAIL','BLOCKED')]
history='\n'.join('- '+x['result_status']+': '+(str(x['passed'])+' passed, '+str(x['failed'])+' failed' if x.get('passed') is not None else 'no completed test count; probe/runtime details retained in log')+'; '+str(x.get('evidence_reference')) for x in failures) or 'No completed failed PR16 runs.'
summary=f'''# APP06 PR16 / DEV08 - implementation, testing and PR17 handoff

## A - Environment and prerequisite audit

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4, Windows. Addon
vendor_price_revision_impact_simulator. Local release source, exact90-file PR15
ledger and retained PR00-15 PASS evidence verified before edits; see
pr16-predevelopment-audit.json. Official [Community builds](https://nightly.odoo.com/)
confirm20 stable. Existing major preserved; no Enterprise dependencies or migration.
All database verification uses newly created explicitly allowlisted synthetic
fixtures on an owned disposable loopback55447 cluster, no production data/credentials.

## B - Independent controls implemented

Immutable reconciliation.run/check/exception/review models retain named controls,
source/version references, exact/categorical evidence, typed numeric values,
difference, currency/UoM-derived tolerances, status/severity and coverage metrics.
One current-profitability getter checks native source freshness and shared locks;
independent equations additionally inspect PR08-15 stored evidence. No repeated
pipeline execution per check or upstream publisher. Expected profit/risk calculations
do not call upstream profitability/risk helpers.

Checks cover original file SHA256/size, revision/row/version/variant lineage,
physical/reserved/free stock, unique physical/source receipts, PO supplier remainder,
ordered/delivered/outstanding demand, allocation sums/owners/capacities, exact cost
entry/segment coverage, unchanged stock/protected PO cost, old/new procurement
tier/date/FX, PR14 signed line extensions/totals/decomposition, PR11 revenue/FX,
PR15 gross profits/margins/erosion/relative ratios, risk thresholds/outcomes/reasons,
order/product/customer/company amount-ratio groups and conditional scenario isolation.

PASS/FAIL/BLOCKED/NOT_APPLICABLE/NOT_RUN/STALE remain distinct. A critical required
FAIL blocks readiness; stale/missing/not-run evidence is not-ready. Unknown cost or
revenue is never zero, incremental-only cost does not establish complete profit.
No eligible demand is explicit, not100 percent. Completeness metrics preserve
numerator/denominator/scope; quantity coverage is grouped by product/UoM and is never
called monetary confidence. Partial complete lines do not make an entire scope ready.

Existing governed PR04 policy gains a readiness-basis dimension: strict_verified
default versus explicit documented_projection for complete projected review. This
uses existing dated configuration ownership/version/publication/audit. Even permitted
projection review retains scenario/estimate confidence and grants no approval or
application. Every failed/blocked/stale control has an actionable exception; role
routing/owner assignment and append-only evidence cannot modify checks/readiness.
Closure requires an actual matching PASS in a later current same-scenario run.
Old failures persist and later recurrence creates a new open exception.

Runs are immutable, versioned, idempotent and source-fingerprinted. Publication
savepoints are atomic; existing company/batch serialization plus native shared
source locks protect concurrent collection and policy/source changes. No business
commits, sudo projection, source repair or native write actions.

## C - Actual relevant files

{chr(10).join('- '+n for n in changes)}

docs/FINANCIAL_RECONCILIATION.md documents the contract. TESTING_SETUP.md,
TEST_REPORT.json and DEVELOPMENT_PROGRESS.md retain reproducible setup/status.
evidence/pr16-* retains the exact PR15 archive, cold capture, real logs, probes,
source ledger and final static evidence. Earlier business implementation is unchanged.
The sole prior-test change strengthens atomicity to preserve every existing record
value and reject any leaked fixture result, instead of assuming empty tables.
All other earlier tests are unchanged. Final cold-install selection covers the
full numerical reference, review wizard and module foundation; all PR16 cases
execute in the final-source upgrade milestone. The earlier complete50-test fresh
PASS remains its own historical source result, not a fifty-test final UI claim.

## D - Executed controlled reference

| Item | Actual synthetic reference |
|---|---:|
| Confirmed outstanding demand | 200 units |
| Stock / protected incoming / new procurement |60 /40 /100 units |
| Revenue | INR28,000 |
| Baseline / revised cost | INR20,000 /21,500 |
| Signed incremental cost | INR+1,500 |
| Baseline / revised projected profit | INR8,000 /6,500 |
| Signed profit change / reduction | INR-1,500 /+1,500 |
| Margins |28.57142857% /23.21428571% |
| Erosion |5.35714286 percentage points |
| Reconciliation |All required controls PASS under documented_projection policy |
| Readiness |ready_for_financial_review; never approved/signed off/applied |

The fixture retains estimated stock/scenario procurement basis. Under the default
strict_verified policy the same projected cost evidence is NOT_READY. Numeric
consistency and explicit projection review never certify actual accounting costs.

## E - Actual exception references

Controlled corruption tests retain220 allocated against200 demand (difference20),
duplicate physical quant identity, protected40 revised at115 instead of100, incorrect
sales revenue30000 instead of28000, changed product/aggregate/risk and exceeded supply
capacity. Definite integrity failures are BLOCKED, never balanced/repaired in PR16.
Missing FIFO keeps known incremental1500 but full cost/profit/margin unavailable.
Missing company FX and unverified PO protection are NOT_READY without1:1 FX or
invented prices. Incorrect additive quotation provenance is blocked; alternatives
require their exact confirmed baseline and compatible source scenario.

Review notes and owner assignment never produce PASS. Tests verify reason/evidence,
company-safe assignment, duplicate review idempotence, no arbitrary waiver,
closure only after current matching PASS, retained old failure and new recurrence.

## F - Completeness and current readiness

Reference source/demand/cost/revenue/margin scope is complete: source disposition1/1,
resolved demand1/1, known cost entries3/3, known revenue1/1, margin lines1/1.
All {reference_checks} controls PASS;0 failed/blocked controls and0 critical/high
exceptions under its explicit projection policy. Strict-basis and unknown-input fixtures
preserve blocked controls/high exceptions and not-ready status. Counts and all
coverage numerators/denominators are in each frozen run; no opaque blended score.
No-demand percentages stay null. Historical stored readiness is not current authority:
source changes set current_readiness=not_ready and require current getters/revalidation.
Corrected sources generate a new run; old checks/exceptions/readiness remain audit
history. A current result is evidence for future review, not actual management sign-off.

## G - Security

Only scoped Finance initiates runs. All headers/checks/exceptions/reviews require
selected active company, cost/supply/demand warehouse grants, customer-commercial
grant and native customer-order rights. Raw supplier costs, customer terms and derived
margin/check evidence share strict confidentiality. Sales-only/Purchase-only have
no automatic disclosure. Auditors read-only, portal/public denied. Direct ORM,
export/group, foreign selected company, forged write/context and revoked grant
checks run. Review assignments grant no extra source access; original attachments
remain protected by the established intake boundary. No new sudo disclosure.

## H - Actual tests and evidence

| Gate | Actual final-source result | Evidence |
|---|---|---|
{table}

{methods} new tests. Prior failures and interrupted attempts remain history:

{history}

A resumed preservation probe initially compared a live calculated commercial status
against a fixture created two days earlier. Every stored-value comparison passed;
the original-as-of calculated assertion was then evaluated using the date recorded
in its retained commercial snapshot and passed. No application rule or stored data
was changed. This failed probe remains in history.

Two operational probe attempts exposed a fixture boundary error: adding the
Finance role after the before-capture produced a native res.users group-change
audit mail.message. The retained diagnostic log identifies that message. All
authorization setup now precedes the before-capture; unchanged full22-model and
13-upstream comparisons pass without excluding messages or changing application code.

The broad upgrade attempt executed348 tests:347 passed and one old atomicity test
assumed empty margin tables despite deliberately retained PR15 data. Its FAIL log
is retained, never relabeled PASS. The final-source focused upgrade follow-up
executes every PR16 test and the seed-aware PR15 snapshot class. All business code
and other tests are byte-identical to the broad attempt; only that atomicity test
now verifies all prior stored values and no leaked fixture result. Repeating all
unchanged upstream cases was unnecessary. Exact90-source PR15 archive was installed; all stored evidence/source bytes,
including real financial and margin/risk snapshots, were committed/cold-captured
before PR16 schema, then compared after actual update. Nine two-session races:
{', '.join(race_names)}. The future-policy publication race verifies serialization
and non-invalidation of the unrelated current period; relevant policy-change
staleness is independently covered. Native22-model and upstream13-model immutability
probes PASS.100-line reconciliation measured{seconds:.3f}s after upstream preparation,
executing {workload_checks} controls with0 exceptions.
Other workloads/peak memory NOT_MEASURED; manual browser UAT NOT_RUN. No statutory
GL audit, final release FULL or PR17 execution claim.

## I - Business safety

No supplier/customer price application, SO/PO change, stock reservation/movement,
valuation modification, journal/bill posting, actual management approval or
sign-off. PR16 creates only authorized analytical checks/runs/exceptions/reviews.
Native writes in probes prepare synthetic fixtures or controlled competing changes.
Disposable runtime removed after confirmed shutdown. All source services and prior
business/security tests remain unchanged except the stronger seed-aware atomicity
assertions described in section H.

## J - Progress and limitations

PR16 VERIFIED for the documented independent projected financial controls and review
readiness. Final {len(ledger)}-source ledger SHA256 {sha}. TEST_REPORT.json and
DEVELOPMENT_PROGRESS.md updated with real evidence. Unsupported upstream warehouse/
lot FIFO lineage, future landed components, unallocated discounts/FX, uncertain PO
amendments and historical source limitations remain incomplete. Existing current
getters/native semantics are retained, not reimplemented as a GL audit. Required
controls cannot be waived. Larger stress/memory and browser UAT remain unverified.
PR17 NOT_STARTED.

## K - PR17 handoff

Use only current get_current_reconciliation in an authorized fresh transaction.
Retain exact PR08-15 snapshot IDs/versions/fingerprints, original source hash,
normalized eligible quantities, protected PO/stock bases, procurement tiers, dates,
UoM/currency/FX methodology, current customer revenue, baseline/revised costs,
profit/margin/risk, confidence and all check evidence, required statuses, coverage
numerators/denominators and unresolved exceptions. A future what-if case must clone
bounded assumptions into new scenario evidence with a common confirmed baseline;
never mutate immutable baseline sources or add alternative scenario totals.
Readiness is not approval or price authority. Preserve company/customer/cost
confidentiality, no double-counting and missing-data invariants. Future negotiation,
repricing/sign-off/approval/application require separate governed phases.
STOP after PR16; PR17 remains NOT_STARTED.
'''
(r/'evidence/DEV-08-pr16-summary.md').write_text(summary,encoding='utf-8')
(r/'evidence/DEV-08-pr16-static-validation.txt').write_text('\n'.join('PASS '+s for s in checks)+f'\nTOTAL_CHECKS={len(checks)}\nSOURCE_HASH={sha}\n',encoding='utf-8')
now=datetime.now(timezone.utc).isoformat(timespec='seconds')
record=dict(prompt_id='PR-16',phase='DEV-08',odoo_version='20.0',module=r.name,environment=dict(os='Windows',edition='Community',database=None),test_level='QUICK',invocation='python evidence/pr16-finalize.py',started_at=started,completed_at=now,exit_status=0,passed=len(checks),failed=0,skipped=0,result_status='PASS',evidence_reference='evidence/DEV-08-pr16-static-validation.txt',blocking_reason=None,verification_scope='PR16_FINAL_STATIC',source_hash=sha,source_changed_during_run=False,test_unit='static_assertion_groups')
report['history'].append(record);report['latest_run']=record;report['current_status']='PASS';report['current_status_detail']='PR16 VERIFIED: independent financial controls and review readiness; PR17 NOT_STARTED.'
report['pr16_handoff']=dict(status='VERIFIED',summary='evidence/DEV-08-pr16-summary.md',source_hash=sha,source_files=len(ledger),source_ledger='evidence/pr16-verified-source-sha256.json',benchmark=dict(affected_lines=100,seconds=seconds,larger_loads='NOT_MEASURED',peak_memory='NOT_MEASURED'),not_run=['manual browser UAT'],business_mutations=False,next_prompt='PR-17 NOT_STARTED')
(r/'TEST_REPORT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
p=r/'DEVELOPMENT_PROGRESS.md';progress=p.read_text(encoding='utf-8')
progress=re.sub(r'^\| M3 \|.*$', '| M3 | Financial exposure, margin, what-if | IN_PROGRESS; PR14-16 verified; PR17 scenarios pending |', progress, flags=re.M)
progress=re.sub(r'^\| PR-16 \|.*$',f"| PR-16 | DEV-08 independent financial reconciliation and review readiness | VERIFIED | QUICK{gates['HELPERS_VERIFY']['passed']}; TARGETED{gates['TARGETED']['passed']}; fresh{gates['FRESH']['passed']}; actual PR15 update{gates['UPGRADE']['passed']}; preservation, nine races and22-native/13-upstream safety PASS | evidence/DEV-08-pr16-summary.md; TEST_REPORT.json | Projected review only; browser UAT NOT_RUN; larger loads/memory NOT_MEASURED | None for documented scope | 2026-10-31 | STOP after PR16; PR17 NOT_STARTED |",progress,flags=re.M)
progress+='\n\n## PR16 completion and PR17 handoff\n\nIndependent named source/quantity/revenue/cost/exposure/profit/risk checks retain\nexact evidence, duplicate controls, completeness counts and strict review readiness.\nImmutable versioned runs and append-only exceptions/reviews cannot grant approval.\nGoverned strict/default versus documented-projection readiness preserves confidence.\nActual final-source gates and limitations are in evidence/DEV-08-pr16-summary.md.\nFinal source '+sha+'. Runtime removed after confirmed shutdown.\nNo native source or upstream analytical mutation. No sign-off/application.\nSTOP after PR16. PR17 remains NOT_STARTED.\n'
p.write_text(progress,encoding='utf-8')
print('PR16_FINAL_STATIC=PASS checks='+str(len(checks)))
print('PR16_SOURCE='+sha)
