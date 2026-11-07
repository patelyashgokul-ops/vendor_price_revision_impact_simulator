"""Fail-closed PR17 evidence and handoff; never infer runtime PASS from code."""
import ast
import hashlib
import json
import re
import zipfile
from pathlib import Path
from datetime import datetime,timezone
from lxml import etree

r=Path(__file__).resolve().parents[1]
started=datetime.now(timezone.utc).isoformat(timespec='seconds')
report=json.loads((r/'TEST_REPORT.json').read_text(encoding='utf-8'))
ledger=json.loads((r/'evidence/pr17-verified-source-sha256.json').read_text(encoding='utf-8'))
sha=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
checks=[]
def check(label,condition):
    assert condition,label
    checks.append(label)
for n,h in ledger.items():
    p=r/n;check('Final source '+n,hashlib.sha256(p.read_bytes()).hexdigest()==h)
    if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8'))
    if p.suffix=='.xml':etree.parse(str(p))
baseline=json.loads((r/'evidence/pr16-verified-source-sha256.json').read_text(encoding='utf-8'))
with zipfile.ZipFile(r/'evidence/pr16-source-baseline.zip') as z:
    check('95-file PR16 archive',len(z.namelist())==len(baseline)==95)
    for n,h in baseline.items():
        check('Exact PR16 archive '+n,hashlib.sha256(z.read(n)).hexdigest()==h)
        if n not in ('__manifest__.py','models/__init__.py','tests/__init__.py','tests/test_reconciliation.py'):
            check('Previous business/security/test unchanged '+n,ledger[n]==h)
    old=z.read('tests/test_reconciliation.py').decode('utf-8').replace('\r\n','\n')
    new=(r/'tests/test_reconciliation.py').read_text(encoding='utf-8')
    def atomic_method(source):
        return next(n for cls in ast.parse(source).body if isinstance(cls,ast.ClassDef) and cls.name=='TestReconciliationLifecycle' for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='test_atomic_publication_failure_retry_no_partial_success')
    om,nm=atomic_method(old),atomic_method(new)
    ol,nl=old.splitlines(keepends=True),new.splitlines(keepends=True)
    check('Only seed-aware reconciliation atomicity test changed',ol[:om.lineno-1]+nl[nm.lineno-1:nm.end_lineno]+ol[om.end_lineno:]==nl)
    method=ast.get_source_segment(new,nm)
    check('Stronger exact retained-data atomicity',all(v in method for v in ('before=retained()', 'self.assertEqual(retained(),before)', "('batch_id','=',m.batch_id.id)", 'for name in (HEADER,CHECK,ISSUE,REVIEW)', "side_effect=UserError('PR16 injected exception publication failure')", 'self.assertTrue(self._reconcile(m).check_ids)')))
check('Archive checksum',hashlib.sha256((r/'evidence/pr16-source-baseline.zip').read_bytes()).hexdigest()==(r/'evidence/pr16-source-baseline.sha256').read_text(encoding='utf-8').split()[0])
# Reuse unchanged broad cases only after proving the precise post-milestone delta.
milestone=json.loads((r/'evidence/pr17-business-milestone-source-sha256.json').read_text(encoding='utf-8'))
milestone_hash=hashlib.sha256(json.dumps(milestone,sort_keys=True).encode()).hexdigest()
allowed={'models/vendor_scenario.py','models/scenario_wizard.py','views/scenario_views.xml','tests/test_vendor_scenarios.py','tests/test_reconciliation.py'}
check('Exact narrow post-milestone delta',{n for n,h in milestone.items() if ledger[n]!=h}==allowed)
with zipfile.ZipFile(r/'evidence/pr17-pre-fx-guard-source.zip') as z:
    for n,h in milestone.items():check('Exact broad source archive '+n,hashlib.sha256(z.read(n)).hexdigest()==h)
    before=ast.parse(z.read('models/vendor_scenario.py').decode('utf-8'))
    after=ast.parse((r/'models/vendor_scenario.py').read_text(encoding='utf-8'))
    expected=ast.parse("if method=='price_only_common_fx' and not po and self.baseline_id.margin_id.financial_id.fx_method!='same_rate':\n    raise ValidationError('Price-only common FX requires a common-rate financial baseline. Select that coherent baseline or document an explicit combined FX assumption.')").body[0]
    class StripGuard(ast.NodeTransformer):
        count=0
        def visit_If(self,node):
            if ast.dump(node)==ast.dump(expected):self.count+=1;return None
            return self.generic_visit(node)
    strip=StripGuard();after=strip.visit(after)
    check('Application delta is only the explicit mixed-FX rejection',strip.count==1 and ast.dump(before)==ast.dump(after))
    before=ast.parse(z.read('tests/test_vendor_scenarios.py').decode('utf-8'))
    after=ast.parse((r/'tests/test_vendor_scenarios.py').read_text(encoding='utf-8'))
    class StripNewTest(ast.NodeTransformer):
        count=0
        ui_count=0
        def visit_FunctionDef(self,node):
            if node.name=='test_two_date_baseline_requires_explicit_combined_fx_not_price_only_label':self.count+=1;return None
            return self.generic_visit(node)
        def visit_Expr(self,node):
            expressions=["self.assertIn('115',w.source_basis)","self.assertIn(self.inr.display_name,w.source_basis)","self.assertIn(self.unit.display_name,w.source_basis)","self.assertIn('100',w.source_basis)"]
            if ast.dump(node) in {ast.dump(ast.parse(v).body[0]) for v in expressions}:
                self.ui_count+=1;return None
            return self.generic_visit(node)
    strip=StripNewTest();after=strip.visit(after)
    check('New-test delta only adds FX regression and four UI basis assertions',strip.count==1 and strip.ui_count==4 and ast.dump(before)==ast.dump(after))
    before=ast.parse(z.read('models/scenario_wizard.py').decode('utf-8'))
    after=ast.parse((r/'models/scenario_wizard.py').read_text(encoding='utf-8'))
    class StripUI(ast.NodeTransformer):
        count=0
        def visit_ImportFrom(self,node):
            if node.module=='odoo':
                if any(v.name=='api' for v in node.names):self.count+=1
                node.names=[v for v in node.names if v.name!='api']
            if node.module=='commercial_math' and [v.name for v in node.names]==['price']:
                self.count+=1;return None
            return node
        def visit_FunctionDef(self,node):
            if node.name=='_source_basis':self.count+=1;return None
            return self.generic_visit(node)
        def visit_Assign(self,node):
            if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='source_basis':self.count+=1;return None
            return self.generic_visit(node)
    strip=StripUI();after=strip.visit(after)
    check('Wizard delta only adds readonly source-basis display',strip.count==4 and ast.dump(before)==ast.dump(after))
    before=etree.fromstring(z.read('views/scenario_views.xml'))
    after=etree.parse(str(r/'views/scenario_views.xml')).getroot()
    display=after.xpath(".//field[@name='source_basis']")
    check('Only one readonly basis field added to the view',len(display)==1 and display[0].get('readonly')=='1')
    display[0].getparent().remove(display[0])
    check('Other Community UI unchanged',etree.tostring(before)==etree.tostring(after))
broad=[x for x in report['history'] if x.get('verification_scope') in ('PR17_UPGRADE','PR17_UPGRADE_RESUME') and x.get('source_hash')==milestone_hash and x.get('source_changed_during_run') is False]
check('Retained actual 263-test broad attempt',bool(broad) and broad[-1]['result_status']=='FAIL' and broad[-1]['passed']==262 and broad[-1]['failed']==1)
broad_log=(r/broad[-1]['evidence_reference']).read_text(encoding='utf-8')
check('Only known retained-row atomicity failure','FAIL: TestReconciliationLifecycle.test_atomic_publication_failure_retry_no_partial_success' in broad_log and '1 failed, 0 error(s) of 263 tests' in broad_log)
gates={}
for scope in ('FRESH','HELPERS_VERIFY','TARGETED','UPGRADE','UPGRADE-PRESERVATION','CONCURRENCY','OPERATIONAL-SAFETY'):
    scopes={'PR17_UPGRADE','PR17_UPGRADE_RESUME','PR17_UPGRADE_VERIFY'} if scope=='UPGRADE' else {'PR17_'+scope}
    rows=[x for x in report['history'] if x.get('verification_scope') in scopes and x.get('source_hash')==sha and x.get('source_changed_during_run') is False]
    check('Matching-source '+scope,bool(rows) and rows[-1]['result_status']=='PASS' and rows[-1].get('passed',0)>0)
    gates[scope]=rows[-1];check('Retained log '+scope,(r/rows[-1]['evidence_reference']).is_file())
check('Owned runtime removed',not list(r.glob('.pr17*')))
check('Server shutdown retained','database system is shut down' in (r/'evidence/pr17-postgres.log').read_text(encoding='utf-8'))
for name in ('scenario_math','scenario_engine','vendor_scenario','scenario_wizard'):
    source=(r/f'models/{name}.py').read_text(encoding='utf-8')
    check('No native CRUD/elevation/commit '+name,not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('create','write','unlink','sudo','commit','action_confirm','button_confirm','action_post','_action_done') for n in ast.walk(ast.parse(source))))
engine=(r/'models/scenario_engine.py').read_text(encoding='utf-8')
for service in ('Reconciler(self.batch,self.m.id).build()','FinancialEngine.aggregate(helper)','CostEngine.replacement(ce,proxy)','MarginEngine.aggregate(', 'independent_profit(', 'independent_risk('):
    check('Shared/independent service '+service,service in engine)
ops=(r/gates['OPERATIONAL-SAFETY']['evidence_reference']).read_text(encoding='utf-8')
for marker in ('PR17_UPSTREAM_IMMUTABILITY=PASS seventeen','PR17_PORTAL_PUBLIC=PASS','PR17_OPERATIONAL_SAFETY=PASS'):
    check('Actual safety '+marker,marker in ops)
native=re.search(r'PR17_OPERATIONAL_MODELS=(.+)',ops).group(1).split(',')
check('22 native models unchanged',len(native)==22)
race=(r/gates['CONCURRENCY']['evidence_reference']).read_text(encoding='utf-8')
races=re.findall(r'PR17_CONCURRENT_([A-Z_]+)=PASS',race)
check('Eleven actual separate-session races',len(races)==len(set(races))==11 and 'ASSUMPTIONS' in races)
fresh=(r/gates['FRESH']['evidence_reference']).read_text(encoding='utf-8')
integration=(r/gates['UPGRADE']['evidence_reference']).read_text(encoding='utf-8')
fixture_logs=fresh+'\n'+integration
for marker in ('PR17_REFERENCE','PR17_MOQ','PR17_FX','PR17_PO_HYPOTHESIS','PR17_LANDED'):
    check('Actual fixture '+marker,marker in fixture_logs)
check('Actual mixed-FX guard regression','PR17_FX_METHOD_GUARD' in fixture_logs)
benchmark=re.search(r'PR17_WORKLOAD scenarios=10 seconds=([\d.]+) details=(\d+)',fixture_logs)
check('Actual measured 10 alternatives',bool(benchmark) and int(benchmark.group(2))==30)
seconds=float(benchmark.group(1))
methods=sum(isinstance(n,ast.FunctionDef) and n.name.startswith('test_') for n in ast.walk(ast.parse((r/'tests/test_vendor_scenarios.py').read_text(encoding='utf-8'))))
changes=[n for n,h in ledger.items() if baseline.get(n)!=h]
table='\n'.join('| '+scope+' | PASS '+str(row['passed'])+' '+('tests' if scope in ('FRESH','HELPERS_VERIFY','TARGETED','UPGRADE') else 'probe groups')+' | '+row['evidence_reference']+' |' for scope,row in gates.items())
failures=[x for x in report['history'] if x.get('prompt_id')=='PR-17' and x.get('result_status') in ('FAIL','BLOCKED')]
history='\n'.join('- '+x['result_status']+': '+str(x.get('passed'))+' passed; '+str(x.get('failed'))+' failed; '+str(x.get('evidence_reference')) for x in failures) or 'No failed PR17 attempts.'
summary=f'''# APP06 PR17 / DEV09 - implementation, testing and PR18 handoff

## A - Environment

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4, Windows. Addon
vendor_price_revision_impact_simulator. Existing major version preserved; no
Enterprise dependencies or version conversion. Official [Community builds](https://nightly.odoo.com/)
and local release/source evidence checked at development start. PR00-16 retained
PASS references and the exact95-file PR16 source ledger were checked before edits;
see pr17-predevelopment-audit.json. All database execution uses owned allowlisted
synthetic databases in a disposable loopback55448 cluster; no production clone,
production credentials, HTTP, cron, outgoing mail, real payments or external writes.
Actual database names/invocations/timestamps appear in TEST_REPORT.json and logs.

## B - Implementation

Immutable scenario identity, versioned input/line records, result/detail snapshots
and append-only analytical selection events preserve the exact PR16 baseline.
Clones receive new identities, independent assumptions and no copied result or
verification. Public ORM history create/write/unlink/copy is denied. Omitted products
inherit their correct original proposal; product/PO overrides stay exact.

Explicit negotiated price, fixed per-source-unit reduction, percentage discount
with explicit proposal/old base and exact verified PR08 MOQ tier modes cannot be
silently compounded. Missing/nonfinite/negative prices, contradictory inputs,
wrong currencies/UoM/vendor/product and invented surplus buying are rejected or
retained as blocked/incomplete. Explicit consolidation groups only same-cohort
residual new procurement by company/vendor/product/UoM/warehouse. No PO creation.

Common-FX price-only, combined price/FX and FX-only are labeled. Governed positive
hypothetical rates use company currency per1 source currency with an explicit
date. Old-rate-first price/FX decomposition reconciles. Commercial effective-date
changes use explicit hypothetical commitment timing/evidence, not delivery dates.
Unknown timing stays incomplete; physical supply timing/reallocation is out of
scope and requires a new upstream cohort. No currency-rate or operational dates
are changed. Exact protected PO amendments are separate unapproved hypotheses,
changing only their already allocated open source quantities in that alternative.

A separate governed scenario_landed_policy preserves the original PR13 net-price
baseline while allowing optional future components. Default excludes them. Unique
future components require the dated published permission, nonrecoverable/
not-already-included assertions and company-currency per comparison-unit evidence.
No existing stock cost or capitalized charge is counted again. Missing source cost
or unavailable original proposal remains incomplete; PR16 cannot be bypassed.

PR08 normalization and PR13 replacement tier eligibility are reused. PR14 calculate
and aggregate services operate on isolated dictionaries, not new live financial
sources. PR15 profitability, risk and amount-ratio aggregation are reused, with
unchanged exact PR11 revenue and current PR04 policy reasons. PR16 Reconciler reruns
source/quantity/cost/revenue/policy controls; independent profit/risk equations and
readiness checks validate each alternative. No divergent replacement financial
engine or context flag overrides readiness. FINANCIALLY_VERIFIED is reproducible
hypothetical analytical evidence, never commercial acceptance or actual costs.

Comparisons require the exact same baseline cohort and current complete reconciled
results. Alternatives are never additive or an opaque commercial recommendation.
Changed price/FX/date/tier/PO/landed dimensions remain disclosed. Incomplete results
cannot rank as definitively superior. Preferred-for-review is analytical selection
only; input/source changes require revalidation and history remains immutable.
Company/batch/scenario serialization and upstream native source locks prevent mixed
versions. Failed detail publication rolls back atomically; fresh retries do not
duplicate unchanged results. No business commits or sudo disclosure.

## C - Relevant files

{chr(10).join('- '+n for n in changes)}

docs/WHAT_IF_VENDOR_PRICE_SCENARIOS.md describes the contract. TESTING_SETUP.md,
DEVELOPMENT_PROGRESS.md and TEST_REPORT.json retain execution/status. Earlier
business engines/security definitions remain unchanged. One prior reconciliation
atomicity test now preserves all existing stored run/check/exception/review values
and rejects leaked results for its own batch; all other existing tests are unchanged.
pr16-source-baseline.zip is an exact checksum-verified archive, not a reconstructed
approximation. pr17-* scripts/logs retain synthetic probes and real results.

## D - Executed reference results

Same confirmed200 units, unchanged revenue INR28000, existing60@100 and protected
incoming40@100, new procurement100, old eligible price100:

| Hypothesis | Old baseline | Projected cost | Incremental vs old | Potential improvement vs proposal | Projected profit | Margin |
|---|---:|---:|---:|---:|---:|---:|
| Original115 |20000|21500|1500|0|6500|23.21428571%|
| Negotiate112 |20000|21200|1200|300|6800|24.28571429%|
| Negotiate109 |20000|20900|900|600|7100|25.35714286%|
| Negotiate105 |20000|20500|500|1000|7500|26.78571429%|

Actual fresh log markers assert all four. Fixed3 discount matches112; ten percent
from115 yields103.50 and cost20350. Old-base5 percent yields95 and negative500
incremental. MOQ100 tier109 is eligible for100 residual, while surplus500 is blocked.
Explicit40+60 buying group preserves distinct demand identities. Box/piece unit
conversion is tested once. FX90->94 on USD10->11 gives90 price +44 FX =134 per unit;
see actual PR17_FX marker for the observed rate. Protected40@100->115 in a separate
hypothesis is600 extra (total22100), with actual PO price unchanged. Missing FIFO
stock cost stays unknown; complete profit/margin and proposal improvement stay blank.
Future freight3 and nonrecoverable duty2 remain explicit hypothetical components,
never accepted landed valuation; actual gating/limitations are described below.

## E - Assumption completeness

Source baseline requires current PR16 readiness. Default strict_verified evidence
does not turn estimated stock/scenario procurement into actual accounting cost.
documented_projection permits complete projected review only. Assumptions remain
hypothetical and all source confidence is retained. Missing negotiated price, FX,
stock/PO basis, uncertain timing, ineligible MOQ or unconsumed product overrides
block complete verified results. Missing data never becomes zero or a favorable
rank. Incomparable baseline/quotation cohorts cannot be combined. Source/header
versions, original proposal, old baseline and every changed dimension remain in
provenance and immutable input/result evidence. No management/supplier acceptance
is certified. Landed policy and inherited PR13 attribution limitations cannot be
bypassed through hypothetical inputs; inspect each result's controls/issues.

## F - Security

Only scoped Finance edits/calculates/selects. Scoped confidential readers/auditors
are read-only. Company isolation, all selected warehouse cost/supply/demand grants,
customer-commercial and native-order rights protect headers and all child history.
Sales-only/Purchase-only receive no derived cost/margin or customer-contract bypass.
Direct ORM mutations, forged state/context, cross-company records, exports and
revoked source grants are tested. Public/portal cannot read scenario result/detail.
Global scope rules apply to search/group access as well. Source drilldown checks
read authority; selection grants no new source permissions. No unrestricted sudo.

## G - Actual automated verification

| Gate | Matching-source result | Evidence |
|---|---|---|
{table}

{methods} new test methods. All final gates bind to source {sha}.
The broader actual PR16 update executed263 tests:262 passed,1 old reconciliation
atomicity test assumed globally empty tables despite deliberately retained PR16
history. The FAIL log is retained, never called263 PASS. Its stronger seed-aware
assertions are executed in the final-source follow-up. The application changes
after that broad run are an explicit rejection of the wrong common-FX label on a
two-date baseline, its regression test, and a readonly wizard source price/currency/
UoM/quantity display with four additional assertions. Existing wizard publication
behavior is AST-identical. An earlier complete39-test cold install passed on the
FX-guard source; the final UI cold install selects eight actual reference/wizard/
foundation tests. Every new scenario case executes in the final-source upgrade
follow-up; no39-test PASS is claimed for the eight-test final cold UI selection. Exact source archives, AST
checks and unchanged-file hashes prove this narrow delta. All new scenario cases,
related FX cases and the PR16 lifecycle class run again on the final-source update;
unchanged upstream tests are not unnecessarily repeated. Broader source reference:
{broad[-1]['evidence_reference']} ({milestone_hash}).
Exact archived PR16 code was installed; operational records/source bytes plus
commercial/supply/allocation/sales/purchase/cost/financial/margin/reconciliation/
exception-review evidence were committed and cold-captured before PR17 schema.
After actual update every retained field and byte was compared. No automatic
scenario acceptance or creation. {len(races)} real two-session races: {', '.join(races)}.
Native22-model and upstream17-model before/after probes PASS. Ten alternatives
measured {seconds:.3f}s after baseline preparation,30 exact allocation contributions.
50/100 scenarios,500/2000 product lines,10000 result references, peak memory and
query-count benchmark NOT_MEASURED. Manual browser UAT NOT_RUN. No release FULL
claim. Prior failed/interrupted attempts remain history (null counts are not PASS):

{history}

The initial fresh run was intentionally stopped after repeated required-empty-
JSON storage failures. Odoo20 treats an empty list as SQL NULL; issue evidence now
uses an explicit object with an items list. The focused diagnostic run exposed an archive guard reading cached display state;
the guard now reads the latest event directly. Policy/permission fixture corrections
preserve exact missing-input and real pure-role denial assertions. Upgrade setup
first hit the Finance-only guard with its retained Purchase actor, then required
explicit owner/selected-company context when resumed. Both failed setup logs are
retained; Finance authorization and company guards were unchanged. Successful
seed/cold capture preceded the actual update. Other failure details remain in
exact logs and TEST_REPORT.json; no passing assertion was weakened.

## H - Business safety

No supplierinfo application, supplier acceptance, actual PO/SO changes, customer
repricing, stock reservations/moves/revaluation, landed-cost posting, accounting
entry/bill or management approval occurs in PR17. Native writes in probes are
explicit synthetic setup or controlled competing changes. Only APP06 analytical
scenario/input/result/detail/event records are published. Owned runtime removed
after confirmed PostgreSQL shutdown. Prior upstream records remain immutable.

## I - Progress and limitations

PR17 VERIFIED for the documented isolated analytical scope; the exact ledger
contains {len(ledger)} source files, SHA256 {sha}. DEV00 report and
progress updated only after matching-source gates and cleanup. Warehouse/lot FIFO
lineage, future acquisition timing, surplus buying optimization, cross-vendor
sourcing and unsupported source adjustments remain incomplete/out of scope.
Hypotheses are not accounting truth. Browser UAT/larger loads/memory are unverified.
No blocker for the documented tested scope. STOP after PR17; PR18 NOT_STARTED.

## J - PR18 handoff

Consume current authorized get_current_scenario results, not stored status alone.
Retain exact PR16 baseline, source IDs/versions/fingerprints, input identity,
product/vendor mappings, confirmed or conditional affected demand, protected stock/
PO and new procurement quantities, original and hypothetical source price, units,
FX/date/tier/landed/amendment assumptions, unchanged revenue/customer protection,
old/proposed/scenario cost and margins, potential improvements/pp changes, current
company thresholds, risk reasons, completeness and independent control outcomes.
Preferred-for-review, if selected, remains hypothetical. Future repricing proposals
need their own missing-input, target-margin, commercial protection, company and
derived-cost confidentiality controls; never mutate baseline or native sources.
No recommendations, approval routing, decisions or application implemented.
PR18 remains NOT_STARTED.
'''
(r/'evidence/DEV-09-pr17-summary.md').write_text(summary,encoding='utf-8')
(r/'evidence/DEV-09-pr17-static-validation.txt').write_text('\n'.join('PASS '+x for x in checks)+f'\nTOTAL_CHECKS={len(checks)}\nSOURCE_HASH={sha}\n',encoding='utf-8')
now=datetime.now(timezone.utc).isoformat(timespec='seconds')
record=dict(prompt_id='PR-17',phase='DEV-09',odoo_version='20.0',module=r.name,environment=dict(os='Windows',edition='Community',database=None),test_level='QUICK',invocation='python evidence/pr17-finalize.py',started_at=started,completed_at=now,exit_status=0,passed=len(checks),failed=0,skipped=0,result_status='PASS',evidence_reference='evidence/DEV-09-pr17-static-validation.txt',blocking_reason=None,verification_scope='PR17_FINAL_STATIC',source_hash=sha,source_changed_during_run=False,test_unit='static_assertion_groups')
report['history'].append(record);report['latest_run']=record;report['current_status']='PASS';report['current_status_detail']='PR17 VERIFIED: isolated hypothetical vendor alternatives; PR18 NOT_STARTED.'
report['pr17_handoff']=dict(status='VERIFIED',summary='evidence/DEV-09-pr17-summary.md',source_hash=sha,source_files=len(ledger),source_ledger='evidence/pr17-verified-source-sha256.json',benchmark=dict(scenarios=10,seconds=seconds,details=30,larger_loads='NOT_MEASURED',peak_memory='NOT_MEASURED'),not_run=['manual browser UAT'],business_mutations=False,next_prompt='PR-18 NOT_STARTED')
(r/'TEST_REPORT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
p=r/'DEVELOPMENT_PROGRESS.md';progress=p.read_text(encoding='utf-8')
progress=re.sub(r'^\| M3 \|.*$', '| M3 | Financial exposure, margin, what-if | PR14-17 documented analytical scope VERIFIED; broader UAT not claimed |',progress,flags=re.M)
progress=re.sub(r'^\| PR-17 \|.*$',f"| PR-17 | DEV-09 isolated vendor what-if scenarios | VERIFIED | QUICK{gates['HELPERS_VERIFY']['passed']}; TARGETED{gates['TARGETED']['passed']}; fresh{gates['FRESH']['passed']}; actual PR16 update{gates['UPGRADE']['passed']}; preservation,11 races and22-native/17-upstream safety PASS | evidence/DEV-09-pr17-summary.md; TEST_REPORT.json | Hypothetical only; browser UAT NOT_RUN; larger loads/memory NOT_MEASURED | None for documented scope | 2026-10-31 | STOP after PR17; PR18 NOT_STARTED |",progress,flags=re.M)
progress+='\n\n## PR17 completion and PR18 handoff\n\nIsolated immutable assumptions and results preserve exact PR16 baselines.\nShared PR08/13/14/15 services and independent PR16 controls preserve missing-data,\nsource-confidence and protected supply/revenue invariants. Real final-source gates\nand limitations are recorded in evidence/DEV-09-pr17-summary.md.\nSource '+sha+'. Owned runtime removed after confirmed shutdown.\nNo supplier acceptance, operational repricing, approval or application.\nSTOP after PR17; PR18 remains NOT_STARTED.\n'
p.write_text(progress,encoding='utf-8')
print('PR17_FINAL_STATIC=PASS checks='+str(len(checks)))
print('PR17_SOURCE='+sha)
