"""Publish PR18 handoff only after source-bound real execution and cleanup."""
import runpy,json,hashlib,re,ast
from datetime import datetime,timezone
from pathlib import Path
r=Path(__file__).resolve().parents[1]
started=datetime.now(timezone.utc).isoformat(timespec='seconds')
static=runpy.run_path(str(r/'evidence/pr18-static.py'))
ledger,sha,checks=static['ledger'],static['sha'],static['checks']
check=static['check']
check('Frozen final source exact',ledger==json.loads((r/'evidence/pr18-verified-source-sha256.json').read_text(encoding='utf-8')))
report=json.loads((r/'TEST_REPORT.json').read_text(encoding='utf-8'))
prior_hash=hashlib.sha256(json.dumps(static['prior'],sort_keys=True).encode()).hexdigest()
broad=[v for v in report['history'] if v.get('verification_scope') in ('PR18_UPGRADE','PR18_UPGRADE_RESUME') and v.get('source_hash')==prior_hash and v.get('source_changed_during_run') is False]
check('Genuine source-bound broad PR17 upgrade before precise rounding fix',bool(broad) and broad[-1]['result_status']=='PASS' and broad[-1]['passed']==283)
broad=broad[-1]
gates={}
for scope in ('FRESH','HELPERS_VERIFY','TARGETED','UPGRADE','UPGRADE-PRESERVATION','CONCURRENCY','OPERATIONAL-SAFETY','PERFORMANCE'):
    scopes={'PR18_UPGRADE','PR18_UPGRADE_RESUME','PR18_UPGRADE_VERIFY'} if scope=='UPGRADE' else {'PR18_'+scope}
    rows=[v for v in report['history'] if v.get('verification_scope') in scopes and v.get('source_hash')==sha and v.get('source_changed_during_run') is False]
    check('Matching-source gate '+scope,bool(rows) and rows[-1]['result_status']=='PASS' and (rows[-1].get('passed') or 0)>0)
    gates[scope]=rows[-1]
    check('Retained actual log '+scope,(r/rows[-1]['evidence_reference']).is_file())
    scripts={'UPGRADE-PRESERVATION':'pr18-upgrade-preservation.py','CONCURRENCY':'pr18-concurrency-probe.py','OPERATIONAL-SAFETY':'pr18-operational-safety-probe.py','PERFORMANCE':'pr18-performance-probe.py'}
    if scope in scripts:check('Exact executed probe '+scope,rows[-1]['probe_script_sha256']==hashlib.sha256((r/'evidence'/scripts[scope]).read_bytes()).hexdigest())
archive_sha=hashlib.sha256((r/'evidence/pr17-source-baseline.zip').read_bytes()).hexdigest()
for scope in ('PR17_BASELINE_PREPARATION','PR18_UPGRADE-SEED','PR18_UPGRADE-COLD-CAPTURE'):
    rows=[v for v in report['history'] if v.get('prompt_id')=='PR-18' and v.get('verification_scope')==scope and v.get('source_hash')==archive_sha]
    check('Actual PR17 baseline preparation '+scope,bool(rows) and rows[-1]['result_status']=='PASS')
    if scope.endswith('PREPARATION'):check('Nonempty old installation tests',rows[-1]['passed']==4)
check('Owned runtime removed',not list(r.glob('.pr18*')))
check('Retained stopped server','database system is shut down' in (r/'evidence/pr18-postgres.log').read_text(encoding='utf-8'))
ops=(r/gates['OPERATIONAL-SAFETY']['evidence_reference']).read_text(encoding='utf-8')
for marker in ('PR18_UPSTREAM_IMMUTABILITY=PASS twenty_three','PR18_PORTAL_PUBLIC=PASS','PR18_OPERATIONAL_SAFETY=PASS'):check('Actual safety '+marker,marker in ops)
native=re.search(r'PR18_OPERATIONAL_MODELS=(.+)',ops).group(1).split(',')
check('22 native models unchanged',len(native)==22)
upstream=re.search(r'PR18_UPSTREAM_MODELS=(.+)',ops).group(1).split(',')
check('23 actual upstream models unchanged',len(upstream)==len(set(upstream))==23)
race=(r/gates['CONCURRENCY']['evidence_reference']).read_text(encoding='utf-8')
races=re.findall(r'PR18_CONCURRENT_([A-Z_]+)=PASS',race)
check('12 separate-session races',len(races)==len(set(races))==12 and {'CUSTOMER_TERMS','QUOTE_CONFIRMATION','ASSUMPTIONS','GRANT'}<=set(races))
fresh=(r/gates['FRESH']['evidence_reference']).read_text(encoding='utf-8')
for marker in ('PR18_REFERENCE','PR18_PARTIAL','PR18_TAX_NATIVE','PR18_FX_UOM','PR18_PARTIAL_FX_ROUNDING'):check('Actual fixture '+marker,marker in fresh)
work=re.search(r'PR18_WORKLOAD lines=100 seconds=([\d.]+) recommendation_lines=100',fresh)
repeat=re.search(r'PR18_WORKLOAD repeated_generations=10 seconds=([\d.]+) unique_headers=1',fresh)
check('Actual 100-line and 10-repeat measurements',bool(work) and bool(repeat))
perf=(r/gates['PERFORMANCE']['evidence_reference']).read_text(encoding='utf-8')
measurements=[json.loads(re.search(r'PR18_PERFORMANCE_'+str(size)+r'=(.+)',perf).group(1)) for size in (500,2000)]
check('Actual 500/2000 eligible native-price workloads',all(v['affected_lines']==n and v['eligible_draft_lines']==n-1 and v['partial_draft_lines']==1 and v['protected_confirmed_lines']==1 and v['unchanged_native_models']==22 and v['sql_queries']>0 and v['sampled_rss_peak_bytes']>=v['rss_start_bytes'] for n,v in zip((500,2000),measurements)))
check('10000 actual financial source records across five stages',measurements[-1]['source_references']==10000 and all(v==2000 for v in measurements[-1]['source_reference_counts'].values()))
perf_table='\n'.join('| '+str(v['affected_lines'])+' | '+str(v['seconds'])+' | '+str(v['sql_queries'])+' | '+str(round(v['sampled_rss_peak_bytes']/1048576,2))+' | '+str(round(v['sampled_rss_growth_bytes']/1048576,2))+' | '+str(v['source_references'])+' |' for v in measurements)
preservation=(r/gates['UPGRADE-PRESERVATION']['evidence_reference']).read_text(encoding='utf-8')
preserved=int(re.search(r'PR18_PRESERVED_MODELS=(\d+)',preservation).group(1))
check('Retained actual prior models',preserved>40)
baseline=static['baseline']
changed=[n for n,h in ledger.items() if baseline.get(n)!=h]
methods=sum(isinstance(n,ast.FunctionDef) and n.name.startswith('test_') for n in ast.walk(ast.parse((r/'tests/test_recommendations.py').read_text(encoding='utf-8'))))
table='| Actual PR17 upgrade, pre-rounding source | PASS '+str(broad['passed'])+' tests | '+broad['evidence_reference']+' |\n'+'\n'.join('| '+scope+' | PASS '+str(row['passed'])+' '+('tests' if scope in ('FRESH','HELPERS_VERIFY','TARGETED','UPGRADE') else 'probe groups')+' | '+row['evidence_reference']+' |' for scope,row in gates.items())
failures=[v for v in report['history'] if v.get('prompt_id')=='PR-18' and v.get('result_status') in ('FAIL','BLOCKED')]
history='\n'.join('- '+v['result_status']+': '+str(v.get('passed'))+' passed; '+str(v.get('failed'))+' failed; '+str(v.get('evidence_reference')) for v in failures)
summary=f'''# APP06 PR18 / DEV09 - implementation, testing and PR19 handoff

## A - Environment and prerequisites

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4, Windows. Existing major
version preserved. Official [Community builds](https://nightly.odoo.com/) and
local release/source checked at development start; see pr18-predevelopment-audit.json.
PR00-17 supporting evidence and exact102-file PR17 source archive verified before
edits. All execution used owned allowlisted synthetic databases on loopback55449,
HTTP/cron/external writes disabled. No production credentials or data. Actual
invocations, databases and timestamps appear in TEST_REPORT.json and retained logs.

## B - Implemented behavior

Immutable recommendations, exact-line evidence, comparable alternatives and
append-only review records consume current PR17 scenarios, PR16 readiness, PR11
sales, PR14 cost and PR15 risk with frozen governed PR04 policy. Gross-margin
inversion is C/(1-m), with finite0<=m<100, upward currency rounding, signed gap
and separate nonnegative recovery. Missing cost/revenue/policy remains unavailable.
Optional explicit baseline revenue in shared PR15 and independent PR16 equations
preserves genuine before/after profit when customer revenue changes; exact AST
checks prove all previous three-argument behavior identical. PR16 empty risk JSON
now accepts its native False representation as an empty list, with readiness strict.

Independent exact-line targets are default. Explicit published same-order policy
permits deterministic eligible-original-revenue proportional recovery within one
order with one coherent target. Different orders and conditional quotations never
inherit another confirmed-book gap. Delivered quantity is excluded. Eligible,
protected and review quantities reconcile to outstanding; conditional quantity is
a separate dimension, not additional demand. Fixed commitments stay protected,
unknown adjustment rights require review. Unsent drafts permit analytical review
only under policy. Sent valid or expired offers remain review unless current
verified rights and recorded notice/amendment conditions support review; expiration
does not grant rights. Confirmation/cancellation/source changes invalidate evidence.

Native Odoo20 tax base-line semantics invert excluded/included/fixed/group taxes,
discounts and negative-discount surcharges. Candidate display price remains in
original sales currency/UoM, separate from net comparison-unit/company-currency
financial reference. Source FX/UoM conversion is explicit, discount applied once.
Affine/positive-slope probe, directional rounding and native forward recomputation
check the actual eligible subtotal. Zero/100% discounts, unsupported/nonlinear
pricing, global unallocated discount or missing basis remain review/incomplete.
For partial repricing the unchanged portion also uses native original-price/
discount/tax/quantity forward calculation, source-currency rounding and company
FX rounding. Its disclosed difference from proportional revenue is included in
the projected total. Percentage caps use actual normalized native net unit price.
Calculation version advances to v2; former recommendations require revalidation.

Published maximum net uplift and exact-line source-currency/UoM floors/caps are
restrictive documented assumptions, never invented customer permission. Caps round
down, required prices round up, residual gap remains visible. Already-satisfied
targets keep existing price. Customer revenue recovery and supplier cost reduction
stay separate. A single linear same-FX/single-product/proposal supplier ceiling
uses N*(1-m), unchanged supply cost and eligible new procurement only. Multiple
tiers, FX/landed/date/PO alterations, multiple products, zero procurement and missing
cost instead require explicit current PR17 alternatives. Already-good costs are
never raised to the ceiling. Combined outcomes recompute revenue/cost/profit/risk;
separate benefits are never simply added. Financial completeness, commercial
feasibility and risk remain separate, with explainable review priority.

Fingerprints bind sources, versions, date, target policy, assumptions, prices,
eligibility and controls. Unchanged retries reuse the same record; changes require
revalidation and linked history. Failed option publication rolls back all PR18
rows. Review/preference/archive events do not approve/apply; archive regeneration
creates a new version. Company/batch/scenario and upstream source locks serialize
generation with concurrent business/policy/terms changes; fresh retries reject
stale or revoked source access. No business commits or privilege elevation.

## C - Actual changed files and purposes

{chr(10).join('- '+n for n in changed)}

recommendation_math.py supplies target/rounding/eligibility equations;
recommendation_engine.py integrates frozen sources, native pricing and alternatives;
recommendation.py supplies governed policy, immutable models and Finance wizards.
Security XML protects all headers/children/wizards; Community views provide readonly
registers, source drilldown and analytical review. Manifest/imports register them.
test_recommendations.py adds {methods} meaningful cases; foundation expectation adds
the one implemented submenu while preserving all previous assertions. Shared math
changes and empty-JSON guard are precisely checked against the old archive; every
other prior business/security/test file is byte-identical. Documentation:
docs/CUSTOMER_REPRICING_RECOMMENDATIONS.md, TESTING_SETUP.md, progress/report and
pr18-* synthetic verification scripts/logs. Source108-file ledger: {sha}.

## D - Executed financial references

| Measure | Actual asserted result |
|---|---:|
| Current net revenue | INR28000 |
| Revised cost | INR21500 |
| Current gross profit | INR6500 |
| Current margin |23.21428571%|
| Target margin |25%|
| Required net revenue before rounding |28666.666666...|
| Rounded-up aggregate requirement |INR28666.67|
| Additional net revenue required |INR666.67|
| Supplier total cost ceiling |INR21000|
| Unchanged60 stock +40 protected PO cost |INR10000|
| Eligible new procurement |100 units|
| Hypothetical supplier unit ceiling |INR110|
| Alternative cost reduction |INR500|

All200 fixed-price SO units stay protected with no candidate display price. A
separate verified-adjustable100-of200 example requires INR146.67 on eligible units
and yields INR667 extra after unit rounding; unchanged quantity retains original
revenue. Unsent draft100 has its own INR1333.34 gap and price153.34, independent
of the confirmed-book gap. Sent valid offers without amendment rights stay review.
Actual10% discount candidate170.38, included18% tax candidate180.94; grouped/fixed
tax and negative-discount cases execute native forward checks. USD90 conversion
with box10 sales UoM yields USD17.04/box on100 comparison units and reaches25%.
100% discount and missing FIFO/global-discount cases stay incomplete/review.
The new partial-FX regression reproduces a real pre-fix miss:3 units atUSD3.35
less10%, rate90, original revenue814.50, scenario cost619.86, required826.48.
Native unchanged2-unit subtotalUSD6.03 gives542.70. USD3.50 on1 eligible unit
would total826.20 and margin24.97458243%, despite the former proportional forecast
claiming826.50. Corrected candidateUSD3.51 yields827.10 and margin above25%.
A restrictive USD3.15 net cap correctly leaves candidateUSD3.50, total826.20 and
visible INR0.28 residual; it is cap-constrained, never target-reached. Source prices
and discounts remain unchanged. Failed reproduction and passing regression retained.
Delivered40/open60 quantity is checked. A1% cap produces141.40 with visible residual;
floor/cap conflict is not verified. Supplier110 gives total21000/margin25%; explicit
combined alternatives recompute margin with actual candidate revenue.

## E - Commercial interpretation and limitations

Candidate prices are analytical review references, not amendments or authority.
Fixed confirmed prices and uncertain contracts stay protected/review; quote
opportunities have exact cohorts and validity evidence. Unrecovered gaps, caps,
conditions, risk and missing inputs remain visible. Supplier ceiling is a financial
bound, not a feasible/accepted offer. Hypothetical recovery is never realized
profit/cash. No elasticity, probability, competitor data or invented cap. Current
PR16 strict readiness and PR17 completeness cannot be waived by assumptions.
Documented projections remain projected, not accounting valuation or actual cost.

## F - Security

Only source-scoped Finance can generate/review. Confidential readers/auditors are
read-only. Active selected company, warehouse supply/demand/cost grants, customer
commercial grants and native sales rights protect all related derived pricing and
supplier costs, searches/groups/exports and direct ORM access. Sales/Purchase alone
cannot read or calculate derived cost/margin recommendations. Foreign-company,
forged context, direct create/write/unlink, revoked customer grant, auditor mutation
and portal/public negatives execute. Native source drilldown checks access. Global
rules remain in force; no sudo financial disclosure or approval bypass.

## G - Real automated evidence

| Gate | Result | Evidence |
|---|---|---|
{table}

Actual PR17 archive installed with4 foundation tests, seeded/cold-captured before
PR18 schema existed, then updated with the integrated PR11-18 regression. Exact
stored history/source bytes and native states retained across {preserved} models;
no automatic recommendations created on upgrade. Static preservation/syntax/safety
checks: {len(checks)} PASS. Twelve real separate-session races cover duplicate
generation, PO price, receipt, valued move, FX, grant revocation, proposal, sales
price, policy publication, scenario assumptions, customer terms and quotation
confirmation. Ten repeated generations: {repeat.group(1)} seconds, one header.
100 real affected lines: {work.group(1)} seconds,100 recommendation lines, cost11500.
These are observed synthetic timings, not production capacity or a latency SLA.
The283-test broad update belongs to exact pre-rounding source {prior_hash}.
After that run, only customer_line native remainder/cap basis, its calculation
version and one additional regression method changed. Exact108-file archives and
AST checks prove every other application method and all38 earlier recommendation
tests unchanged. Final-source fresh/QUICK/TARGETED and the focused actual-update
UPGRADE gate above cover the correction; preservation reruns on final source.
No claim that all283 tests reran on the later source.

Separate warm same-process generation (fixture preparation excluded), with actual
native tax/price candidates on N-1 unsent draft lines plus1 protected confirmed
line, including1 partially eligible two-unit draft line with one unchanged-price
unit, produced the following measured workload results:

| Affected lines | Seconds | SQL queries | Sampled RSS peak MiB | RSS growth MiB | Financial source references |
|---:|---:|---:|---:|---:|---:|
{perf_table}

The2000-line cohort binds exactly2000 records each from PR11 sales, PR13 costs,
PR14 financial, PR15 margin and PR17 detail:10000 relevant stage references, not
10000 independent orders or10000 detail rows in one model. Native confirmed/quote
prices, quantities, discounts and states remained unchanged, with22 native model
snapshots also equal before/after each eligible-pricing workload. RSS samples every20ms
measure this process, not a whole-system or fixture-build peak. These single-product,
shared-currency/tax synthetic cohorts do not certify diverse production capacity.

Historical failed attempts are retained:
{history}

Initial generated relation name exceeded PostgreSQL63 characters; explicit short
M2M relation repaired. Fresh37/41 exposed four issues repaired and focused PASS4:
new submenu expectation, Decimal test context, unique tax fixture names, real
PR16 empty-JSON handling. Foreign-currency fixture initially attempted a confirmed
order pricelist change; native protection held. Fixture setup moved before
confirmation and focused PASS1, without bypassing native safeguards. Any additional
probe/setup corrections appear in retained logs and TESTING_SETUP.md.

Manual browser UAT and FULL release regression NOT_RUN. Greater workloads,
10000 independent orders/detail rows, cold/production concurrency capacity and
whole-system peak memory NOT_MEASURED. Mandatory PR18 scoped gates above PASS.

## H - Business safety

Actual snapshots compare all22 native model record counts/values before/after
recommendation/review: customer/vendor prices, SO/PO, stock/reservations, valuation,
FX/cost/master data, posted journal and outgoing communication records unchanged.
23 upstream analytical model snapshots unchanged. Existing confirmed orders,
posted journal and valued done stock move retained. Fixture setup/concurrent
mutation exists only in owned synthetic probes, not application behavior. No
customer/supplier message, operational reservation, inventory revaluation,
accounting posting, management approval or live price application by PR18.
Owned runtime shut down and seven exact temporary paths removed after all gates.

## I - Progress

PR18 VERIFIED for the documented analytical scope. TEST_REPORT.json retains real
attempts and source-bound final gates; DEVELOPMENT_PROGRESS.md updated. No known
mandatory scoped failure remains. Limitations above remain explicit. This is not
a FULL release or manual UAT sign-off. STOP after PR18; PR19 NOT_STARTED.

## J - PR19 handoff, no implementation

Consume get_current_recommendation, original vendor revision and exact company/
warehouse/demand scope, verified PR16 baseline/readiness, selected current PR17
scenario/result/input versions, frozen PR04 target policy and PR11/14/15 evidence.
Retain recommendation line/option/review IDs and fingerprints, eligible/protected/
review/conditional quantities, customer protection/contract conditions, native
price/tax/discount/FX/UoM references, supplier alternatives, proposed conditional
benefit, residual gap, financial completeness, independent controls, risk reasons
and commercial feasibility. Financial sign-off requires current complete sources
and no unresolved critical financial controls; commercial feasibility is separate.

Future Sales/Purchase commercial review, Finance financial sign-off and governed
Director authority limits need exact company/currency/amount/role policies. Future
maker-checker must separate preparer from approver and revalidate authority,
conflicts, stale inputs, contract consent and approval scope on the server. PR18
preferred-for-review events confer no authority. No automatic approval routing,
approve/reject execution, customer/vendor price application, quotation rewriting,
sending, PO amendment, valuation/accounting or executive dashboard implemented.
PR19 remains NOT_STARTED and requires its own active prompt.
'''
(r/'evidence/DEV-09-pr18-summary.md').write_text(summary,encoding='utf-8')
artifact=dict(prompt_id='PR-18',phase='DEV-09',odoo_version='20.0',module=r.name,environment=dict(os='Windows',edition='Community',database_scope='No database execution in static finalizer; gates reference isolated runtime logs'),test_level='STATIC',started_at=started,completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),exit_status=0,result_status='PASS',passed=len(checks),failed=0,source_hash=sha,source_changed_during_run=False,verification_scope='PR18_FINAL_HANDOFF',evidence_reference='evidence/DEV-09-pr18-summary.md',checks=checks)
report['history'].append(artifact);report['latest_run']=artifact;report['current_status']='PASS';report['current_status_detail']='PR18 VERIFIED: source-bound fresh/QUICK/TARGETED/actual PR17 upgrade/preservation/12 races/22 native and23 upstream safety PASS. PR19 NOT_STARTED.'
report['pr18_handoff']=dict(status='VERIFIED',source_hash=sha,summary=artifact['evidence_reference'],broad_upgrade=dict(passed=broad['passed'],source_hash=prior_hash,evidence=broad['evidence_reference'],note='Exact pre-rounding source; constrained two-file delta and final-source follow-up proved'),gates={k:dict(status=v['result_status'],passed=v['passed'],evidence=v['evidence_reference']) for k,v in gates.items()},performance=measurements,limits=['Browser UAT NOT_RUN','FULL release NOT_RUN','Production/cold capacity and larger independent-order workloads NOT_MEASURED'],pr19='NOT_STARTED')
(r/'TEST_REPORT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
p=r/'DEVELOPMENT_PROGRESS.md';s=p.read_text(encoding='utf-8');lines=s.splitlines()
for i,line in enumerate(lines):
    if line.startswith('| PR-18 |'):
        lines[i]='| PR-18 | DEV-09 customer repricing recommendations | VERIFIED | QUICK'+str(gates['HELPERS_VERIFY']['passed'])+'; TARGETED'+str(gates['TARGETED']['passed'])+'; fresh'+str(gates['FRESH']['passed'])+'; actual PR17 broad update283 (pre-fix), final follow-up'+str(gates['UPGRADE']['passed'])+'; preservation,12 races,22-native/23-upstream safety;500/2000 lines and10000 stage references measured | evidence/DEV-09-pr18-summary.md; TEST_REPORT.json | Analytical only; browser UAT/FULL NOT_RUN; production capacity NOT_MEASURED | None for documented scope | '+datetime.now(timezone.utc).date().isoformat()+' | STOP after PR18; PR19 NOT_STARTED |'
s='\n'.join(lines)+'\n\n## PR18 completion and PR19 handoff\n\nImmutable recommendations and native pricing references verified on frozen source '+sha+'.\nActual source-bound gates and limitations: evidence/DEV-09-pr18-summary.md.\nFinancial completeness, commercial feasibility and risk remain separate. No live\nrepricing, acceptance or management approval. Disposable runtime removed after\nverified shutdown. STOP after PR18; PR19 remains NOT_STARTED.\n'
p.write_text(s,encoding='utf-8')
print(json.dumps(dict(status='VERIFIED',source_hash=sha,static_checks=len(checks),gates={k:v['passed'] for k,v in gates.items()})))
