"""Publish PR21 only after genuine final-source gates have passed."""
import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parents[1]
rp = R / 'TEST_REPORT.json'
r = json.loads(rp.read_text(encoding='utf-8'))
ledger = json.loads((R / 'evidence/pr21-verified-source-sha256.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((R/n).read_bytes()).hexdigest() == h for n, h in ledger['files'].items())
static = json.loads((R / 'evidence/pr21-static-checks.json').read_text(encoding='utf-8'))
assert static['status'] == 'PASS' and static['source_hash'] == ledger['source_hash']
gates = {}
for scope in ('FRESH', 'HELPERS_VERIFY', 'TARGETED', 'UPGRADE', 'UPGRADE-PRESERVATION', 'CONCURRENCY', 'OPERATIONAL-SAFETY', 'PERFORMANCE', 'APPROVED-PERFORMANCE'):
    records = [v for v in r['history'] if v.get('verification_scope') == 'PR21_'+scope or (scope == 'UPGRADE' and v.get('verification_scope') in ('PR21_UPGRADE_RESUME', 'PR21_UPGRADE_VERIFY'))]
    assert records, 'Missing '+scope
    v = records[-1]
    assert v['result_status'] == 'PASS' and v.get('passed', 0) > 0, (scope, v)
    assert v.get('source_hash') == ledger['source_hash'] and not v.get('source_changed_during_run'), scope+' source mismatch'
    assert (R / v['evidence_reference']).is_file()
    if v.get('probe_script_sha256'):
        assert hashlib.sha256((R / v['invocation'].removeprefix('Odoo shell ')).read_bytes()).hexdigest() == v['probe_script_sha256'], scope+' probe changed'
    gates[scope] = dict(status='PASS', passed=v['passed'], evidence=v['evidence_reference'], test_unit=v.get('test_unit', 'Odoo selected tests'))
audit = json.loads((R / 'evidence/pr21-predevelopment-audit.json').read_text(encoding='utf-8'))
archive_hash = hashlib.sha256((R / 'evidence/pr20-source-baseline.zip').read_bytes()).hexdigest()
assert archive_hash == audit['archive_sha256']
for scope in ('PR20_BASELINE_PREPARATION', 'PR21_UPGRADE-SEED', 'PR21_UPGRADE-COLD-CAPTURE'):
    v = next(x for x in reversed(r['history']) if x.get('verification_scope') == scope)
    assert v['result_status'] == 'PASS' and v['source_hash'] == archive_hash, scope
    # Working PR21 code is not an input to archived PR20 preparation. The exact
    # immutable archive hash, separate addon path and probe hashes are retained.
    if v.get('probe_script_sha256'):
        assert hashlib.sha256((R/v['invocation'].removeprefix('Odoo shell ')).read_bytes()).hexdigest() == v['probe_script_sha256']
upgrade = next(x for x in reversed(r['history']) if x.get('evidence_reference') == gates['UPGRADE']['evidence'])
for filename in ('test_application_planning.py', 'test_approval.py', 'test_approval_decisions.py'):
    tree = ast.parse((R/'tests'/filename).read_text(encoding='utf-8'))
    expected = {c.name+'.'+f.name for c in tree.body if isinstance(c, ast.ClassDef) and c.name.startswith('Test') for f in c.body if isinstance(f, ast.FunctionDef) and f.name.startswith('test_')}
    assert expected <= set(upgrade['test_names']), filename+' incomplete milestone selection'
cleanup = json.loads((R/'evidence/pr21-runtime-disposition.json').read_text(encoding='utf-8-sig'))
assert cleanup['status'] == 'PASS' and cleanup['stopped_server_status'] == 3 and not cleanup['removed_paths'] and len(cleanup['retained_paths']) == 7
assert all(Path(p).exists() and Path(p).resolve().parent == R.resolve() for p in cleanup['retained_paths'])
performance_log = (R/gates['PERFORMANCE']['evidence']).read_text(encoding='utf-8')
performance = []
for count in (10, 100, 500, 2000):
    matches = re.findall(r'^PR21_PERFORMANCE_'+str(count)+r'=(\{.*\})$', performance_log, re.M)
    assert len(matches) == 1
    performance.append(json.loads(matches[0]))
real = re.findall(r'^PR21_REAL_WORKFLOW=(\{.*\})$', performance_log, re.M)
assert len(real) == 1
approved_log = (R/gates['APPROVED-PERFORMANCE']['evidence']).read_text(encoding='utf-8')
approved_setup_matches=re.findall(r'^PR21_APPROVED_SCALE_SETUP=(\{.*\})$',approved_log,re.M)
assert len(approved_setup_matches)==1
approved_setup=json.loads(approved_setup_matches[0]);assert approved_setup['source_rows']==2000 and approved_setup['no_double_counting']
approved_performance=[]
for count in (10,100,500,2000):
    matches=re.findall(r'^PR21_APPROVED_PERFORMANCE_'+str(count)+r'=(\{.*\})$',approved_log,re.M)
    assert len(matches)==1
    item=json.loads(matches[0]);assert item['genuinely_approved'] and item['planned_lines']==count and item['source_gate_calls']==1
    approved_performance.append(item)
ops_log = (R/gates['OPERATIONAL-SAFETY']['evidence']).read_text(encoding='utf-8')
matches = re.findall(r'^PR21_HANDOFF_SAMPLE=(\{.*\})$', ops_log, re.M)
assert len(matches) == 1
sample = json.loads(matches[0])
(R/'evidence/pr21-plan-sample.json').write_text(json.dumps(sample, indent=2)+'\n', encoding='utf-8')
upgrade_log = (R/gates['UPGRADE']['evidence']).read_text(encoding='utf-8')
for ref in 'ABCDEFGHIJ':
    assert 'PR21_REFERENCE_'+ref+' ' in upgrade_log, 'missing reference '+ref
preserve_log = (R/gates['UPGRADE-PRESERVATION']['evidence']).read_text(encoding='utf-8')
preserved = re.findall(r'^PR21_PRESERVED_MODELS=(\d+)$', preserve_log, re.M)
assert len(preserved) == 1
limits = ['Browser UAT NOT_RUN; FULL release NOT_RUN', 'Production/cold/parallel RPC capacity NOT_MEASURED', 'Synthetic matching benchmark runs after all10000 native references are read for the safety snapshot: warm ORM cache. It excludes source/UoM resolution, native selector sampling and plan persistence; genuine approved planning measured separately', 'Actual10/100/500/2000-line plans use independently approved subsets of one genuine2000-row, single-product quantity-tier source; fixed full source gate cost retained for all subsets; warm single transaction, no RPC/cold capacity claim', 'Native existing-only selector samples maximum20 contexts; no hypothetical future RFQ winner guarantee', 'Performance PASS means assertion/count/no-mutation checks completed; no latency/query/RSS SLA', 'Immutable previews describe a coherent transaction snapshot; future execution must revalidate and lock exact targets/creation scope']
report_path = 'evidence/DEV-11-pr21-summary.md'
failures = [dict(status=v['result_status'], evidence=v.get('evidence_reference'), reason=v.get('blocking_reason')) for v in r['history'] if v.get('prompt_id') == 'PR-21' and v.get('result_status') in ('FAIL', 'BLOCKED')]
r['pr21_handoff'] = dict(status='VERIFIED', completed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), source_hash=ledger['source_hash'], source_files=len(ledger['files']), static_checks=static['checks'], gates=gates, performance=performance, approved_performance=approved_performance, approved_source_setup=approved_setup, real_workflow=json.loads(real[0]), prior_models_preserved=int(preserved[0]), limits=limits, runtime=cleanup, report=report_path, handoff_sample='evidence/pr21-plan-sample.json', prior_failure_history=failures, pr22='NOT_STARTED', operational_application='NOT_IMPLEMENTED_NOT_EXECUTED')
r['current_status'] = 'PASS'
r['current_status_detail'] = 'PR21 verified for documented read-only planning scope; PR22 NOT_STARTED; FULL/browser UAT NOT_RUN.'

def link(path):
    return '['+path+']('+str((R/path).as_posix())+')'

lines = ['# APP06 PR21 / DEV11 — verified read-only vendor application foundation', '',
 '## A — Environment', '',
 'Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4. Existing major version retained; official stable baseline checked at development start (https://nightly.odoo.com/). Addon: vendor_price_revision_impact_simulator. Dedicated locally created allowlisted databases on loopback55452, role codex_vpr_pr21; no HTTP, cron or external operational integration. Controlled price-planning business date is2026-10-28; actual runtime/approval timestamps are recorded separately. Production planning uses the frozen company calendar and current date. Runtime retained stopped, no database deletion.', '',
 'Native supplierinfo has company/variant-or-template/vendor/currency/UoM/MOQ/inclusive dates/price/discount/delay/sequence/vendor code/name. Native selector uses UoM quantity conversion, applicable dates, vendor hierarchy and discounted comparable price, then sequence/id. Odoo20 selector returns a mapping; Purchase may fall back to a last confirmed PO. Field precision and selector implementation fingerprints are checked. Financial normalized cost is never substituted for the original-currency operational price.', '',
 '## B — Implementation', '',
 'Immutable application.plan, .line and .issue store exact source rows, observed material target values, planned after-values, classifications, allowlisted changes, issues and source/target/authority/schema hashes. PR20 get_current_approval() remains the complete source/financial/decision gate. Explicit vendor application intent is captured before approval and frozen inside the payload; existing legacy approvals stay byte-compatible and cannot invent application authority.', '',
 'Target discovery is one bounded batched original-user search for exact approved variants, vendor hierarchy conflicts and company-or-shared references. Exact identities include vendor, variant/template, company, MOQ, currency, UoM and dates. Shared/template/hierarchy broadening and ambiguity block. Metadata is preserved; only price/explicit discount may change on updates. Creation and metadata require explicit approval. Source-unit price and quantity conversion are exact and native precision checked. Company calendar is frozen; caller timezone cannot rewrite historical boundaries. Historical periods require safe new dated rules. All approved changes are evaluated together in a complete analytical after-state.', '',
 'Unchanged dry-runs reuse the latest immutable version; changed evidence creates a linked version. Strict getter/current status rebuild current evidence; older versions are superseded. Expiry at completion and date rollover block. No stored READY plan is execution authority. See '+link('docs/APPROVED_VENDOR_PRICE_APPLICATION_FOUNDATION.md')+'.', '',
 '## C — Files changed', '']
for path, purpose in [('models/application_math.py','deterministic identity, classification, UoM conversion and effective after-state tier analysis'),('models/application_engine.py','approved payload resolution, bounded target discovery, conflicts and current evidence'),('models/application_plan.py','preapproval intent, immutable plans/currentness/projections and protected attachments'),('models/application_ui.py','creator-bound explicit intent wizard and read-only navigation'),('security/application_security.xml','company/source scope and role permissions'),('views/application_views.xml','read-only plan/line/issue displays and explicit declaration wizard'),('tests/test_application_planning.py','meaningful approval/financial/security/identity/currentness/no-write regression'),('__manifest__.py','append planning security/views'),('models/__init__.py','append application modules'),('tests/__init__.py','append application tests'),('docs/APPROVED_VENDOR_PRICE_APPLICATION_FOUNDATION.md','architecture, scope, limits and future handoff'),('TEST_REPORT.json','genuine source-bound runtime evidence/history'),('DEVELOPMENT_PROGRESS.md','PR21 status and stop boundary')]:
    lines.append('- '+link(path)+': '+purpose+'.')
lines += ['', 'All120 other prior source files, including all old test files, are byte-identical to archived PR20. Only3 old integration files extended. Seven new application source files; final130-file hash '+ledger['source_hash']+'. Evidence drivers/probes/static ledger and reproduction logs are retained under evidence/.', '', '## D — Controlled actual reference dry-runs', '', '| Case | Actual asserted result |', '|---|---|', '| A | INR100 → frozen approved INR109, exact MOQ100: UPDATE_CANDIDATE, unchanged native row |', '| B | New MOQ100 tier with lower MOQ1 preserved: CREATE_CANDIDATE, no native creation |', '| C | Exact approved109 already present: NO_CHANGE |', '| D | Shared company-less row: BLOCKED |', '| E | Template-wide rule against variant-only approval: BLOCKED |', '| F | Expired approval, including exact end boundary: BLOCKED; old snapshot retained |', '| G | Approved109, current scenario112: frozen109 retained and BLOCKED;112 never planned |', '| H | Target changed100 →105: current before105, conflict/BLOCKED; original100 history retained |', '| I | Old100 through Oct31, new109 from Nov1: explicit creation preview preserves history |', '| J | Genuine customer-repricing approval: wrong vendor authority, BLOCKED |', '', 'Each case is logged PR21_REFERENCE_A–J inside '+link(gates['UPGRADE']['evidence'])+'. Package integration also verifies an explicitly selected approved vendor component without changing customer prices.', '', '## E — Conflicts', '', 'Ambiguous exact targets, duplicate approved identities, shared records, template scope, vendor hierarchy changes, wrong company/vendor/product, overlapping cheaper MOQ tiers, currency/UoM competition, changed/deleted native targets, stale source/approval/policy/schema, missing intent and unsupported precision block readiness. Warehouse/PO conditional terms, hypothetical FX/landed adjustments, tax-inclusive representation and ambiguous discounted scenario gross-price representation are unsupported. Missing evidence never becomes zero exposure or guessed eligibility.', '', '## F — Security', '', 'Purchase/Finance managers may prepare in their authorized selected company and native source scopes. Director/Auditor roles read subject to the same source scope. Sales-only, portal/public and foreign-company read/export/group/prepare attempts are denied. Public ORM create/write/unlink/copy cannot forge plans, lines, readiness or actors. Source access and protected attachment guards remain original-user enforced; mutable plan attachments/reassignment are denied. The sole metadata-only attachment sudo is inherited-pattern identification, never price discovery.', '', '## G — Testing', '', '| Gate | Actual passed units | Evidence |', '|---|---:|---|']
for scope, g in gates.items():
    lines.append('| '+scope+' | '+str(g['passed'])+' '+g['test_unit']+' | '+link(g['evidence'])+' |')
lines += ['', 'Static '+str(static['checks'])+' checks PASS: '+link('evidence/pr21-static-checks.json')+'. Actual archived PR20 install/real approvals, delegated Finance vote and subsequent revocation, cold capture, update and exact preservation of '+preserved[0]+' registered prior models; some models legitimately empty. Old original approval remains valid; no automatic plans. No old business fields or security grants waived. Baseline preparation records may note edits in the unrelated current PR21 working tree; the executed archived123-file PR20 source is separately hash verified and untouched.', '', 'Concurrency uses independent real database cursors for duplicate planning, future-rule phantom insertion, native target edits and governed approval invalidation, with fresh-transaction serialization retries and strict stale checks. Separate company-isolation assertions are labelled separately. New discovery introduces no native target write locks; existing PR20 financial baseline share locks remain.', '', 'Measured local performance:', '', '| Synthetic DTO lines | Actual native references | Seconds | SQL |', '|---|---:|---:|---:|']
for v in performance:
    lines.append('| '+str(v['lines'])+' | '+str(v['actual_native_references'])+' | '+str(round(v['seconds'], 4))+' | '+str(v['sql'])+' |')
lines += ['', 'Each scale workload uses one batched discovery. Actual10000 native fixture references are compared before/after. These are warm discovery/matching benchmarks, not full approved planning. The separately measured one-row dry-run from a genuine approval is '+json.dumps(json.loads(real[0]), sort_keys=True)+'.', '', 'Prior failed attempts retained without relabelling:']
index=lines.index('Prior failed attempts retained without relabelling:')
block=['Genuine approved planning (real import, independent decisions and full dry-run persistence):', '', '| Approved plan lines | Dry-run seconds | SQL | Source gate calls | Approval setup seconds |', '|---|---:|---:|---:|---:|']
for item in approved_performance:
    block.append('| '+str(item['planned_lines'])+' | '+str(round(item['seconds'],3))+' | '+str(item['sql'])+' | '+str(item['source_gate_calls'])+' | '+str(round(item['approval_setup_seconds'],3))+' |')
block += ['', 'The genuine2000-row import/commercial/financial/reconciliation setup took '+str(round(approved_setup['seconds'],3))+'s. Projected revenue450 and baseline/revised profit240 remain unchanged across2000 proposal tiers (no demand/cost double counting). All four independently approved subsets retain the fixed2000-row financial source; one product with distinct MOQ tiers, warm same-transaction caches. This differs from2000 distinct products and cold/parallel RPC capacity. RSS and sampled existing selectors are retained in TEST_REPORT.json. Source revalidation dominates these full planning timings; matching-only figures cannot substitute for full dry-run latency. All native22-model snapshots and native create/write/unlink tripwires passed.', '']
lines[index:index]=block
for v in failures:
    lines.append('- '+str(v['status'])+' '+(link(v['evidence']) if v['evidence'] else str(v['reason'])))
lines += ['', 'Initial new numeric-string assertion and menu nesting regressions were corrected; old passing tests were preserved. The first concurrency probe used the restricted planner as its external native-change injector; native create access was correctly denied. Only that fixture injector was switched to an authorized test admin, retaining the original unprivileged application planner and all race/currentness assertions. The first genuine-scale setup omitted action_validate_commercial_prices() after context verification; the fixture was corrected to execute that real required stage, preserving all2000-row assertions. Actual failed attempts and reruns remain visible in TEST_REPORT.json history.', ''] + ['- '+v for v in limits]
lines += ['', '## H — Business safety', '', 'Application service created0, updated0 and deleted0 product.supplierinfo records. Actual native create/write/unlink tripwires surround dry-run/current getter/repeat/revalidation. Exact22-model native counts/values/write_dates plus27 upstream analytical models and approval business fields are preserved on positive synthetic confirmed SO/PO, valued stock receipt3500, reservations and posted journal entry fixtures. No vendor/customer pricelist application, PO/SO repricing, stock valuation or accounting posting is performed by planning. Native records are created/edited only by explicit isolated test-fixture setup and concurrent-change injectors, before analytical safety snapshots or as documented race inputs.', '', '## I — Progress', '', 'PR21 VERIFIED for the documented read-only foundation. TEST_REPORT.json.pr21_handoff and DEVELOPMENT_PROGRESS.md contain genuine evidence and failed-run history. Runtime stopped/status3, seven owned paths retained under TESTING_POLICY.md:51. Browser UAT/FULL remain NOT_RUN; production/cold/parallel RPC capacity is NOT_MEASURED. PR22 NOT_STARTED. No operational application implemented or executed.', '', '## J — PR22 handoff', '', 'Exact synthetic disposable sample: '+link('evidence/pr21-plan-sample.json')+', request '+str(sample['request_id'])+', authorization '+str(sample['authorization_id'])+', plan '+str(sample['plan_id'])+'. Full immutable evidence contains request/version, current-at-capture validity/expiry, approved payload hash, company/vendor/product identities, observed target IDs, original currency/UoM/MOQ/dates, explicit operation and metadata, before/after fields, conflicts and source/target/approval/schema hashes. The operational sample is CREATE_CANDIDATE USD11/Unit MOQ10 from approved USD110/Box10; financial INR1034 is not a native price. The probe rolled back its final planning transaction; IDs are evidence references, not usable operational authority.', '', 'PR22 must obtain separate execution authorization and the native supplierinfo permissions required for each create/write operation; this foundation adds no native pricing rights. It must revalidate latest plan/current approval, complete approved payload/source/financial reconciliation, company and original-user native scope immediately before writes. Lock exact update targets, compare all approved material before-values, serialize creation scope/phantoms, enforce exact dates/tiers/currency/UoM and field allowlists, and never substitute current unapproved prices. Use an idempotency key and transaction-wide all-or-nothing rollback; failed application is never success. Fresh retries must revalidate authority and prevent duplicate creates. Verify exact post-write native values and retain before/after, actor/principal, source supplier evidence, approvals and failure audit; corrections append history. PO/customer amendments, external consent and accounting/valuation remain separate authorized workflows. STOP after PR21; do not begin PR22.']
(R/report_path).write_text('\n'.join(lines)+'\n', encoding='utf-8')
p=R/'DEVELOPMENT_PROGRESS.md'
s=p.read_text(encoding='utf-8');old=next(v for v in s.splitlines() if v.startswith('| PR-21 |'))
s=s.replace(old, '| PR-21 | DEV-11 approved vendor application planning and read-only dry-run | VERIFIED | Final-source fresh/QUICK/TARGETED/PR19-20 milestone/actual PR20 update/preservation/races/no-write/performance PASS | evidence/DEV-11-pr21-summary.md; TEST_REPORT.json | Read-only planning; FULL/browser UAT NOT_RUN; cold/parallel RPC capacity NOT_MEASURED | None for documented scope | '+datetime.now(timezone.utc).date().isoformat()+' | STOP after PR21; PR22 NOT_STARTED |')
s=s.split('\n\n## PR21 verified handoff')[0]
s+='\n\n## PR21 verified handoff\n\nFinal130-file source '+ledger['source_hash']+'; actual gates, A-J cases, original PR20 approval/delegation preservation, concurrency, positive native no-write snapshots and measured resolver limits in evidence/DEV-11-pr21-summary.md and TEST_REPORT.json.pr21_handoff. All120 old nonintegration source files/tests unchanged. No supplier price application; runtime retained stopped. STOP after PR21; PR22 NOT_STARTED.\n'
p.write_text(s, encoding='utf-8')
p=R/'docs/APPROVED_VENDOR_PRICE_APPLICATION_FOUNDATION.md';s=p.read_text(encoding='utf-8');at=s.index('IN_PROGRESS. Actual source-bound') if 'IN_PROGRESS. Actual source-bound' in s else s.index('PR21 VERIFIED for the documented read-only scope.')
s=s[:at]+'PR21 VERIFIED for the documented read-only scope. Actual source-bound gates, A-J examples, failure history, genuinely approved10/100/500/2000-tier planning, separate10000-reference matching measurements and workload limits are recorded in TEST_REPORT.json.pr21_handoff and evidence/DEV-11-pr21-summary.md. Browser UAT/FULL NOT_RUN; production and cold/parallel RPC capacity NOT_MEASURED. Runtime retained stopped; no database deletion. PR22 NOT_STARTED.\n';p.write_text(s, encoding='utf-8')
rp.write_text(json.dumps(r, indent=2)+'\n', encoding='utf-8')
print('PR21_HANDOFF=VERIFIED source='+ledger['source_hash'])
