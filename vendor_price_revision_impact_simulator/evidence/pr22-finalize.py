"""Fail-closed final evidence assembly. No success inferred from process exit."""
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return path.read_text(encoding='utf-8-sig')


def save(path, value):
    path.write_text(value, encoding='utf-8')


subprocess.run([sys.executable, str(ROOT/'evidence/pr22-static-check.py')], check=True, cwd=ROOT)
ledger = json.loads(read(ROOT/'evidence/pr22-source-ledger.json'))
source = ledger['source_hash']
report = json.loads(read(ROOT/'TEST_REPORT.json'))
history = [v for v in report['history'] if v.get('prompt_id') == 'PR-22']
required = ('SEPARATION', 'CONCURRENCY', 'FRESH', 'UPGRADE', 'UPGRADE-PRESERVATION',
            'OPERATIONAL-SAFETY', 'COLD-REPLAY', 'HELPERS_VERIFY', 'APPROVED-PERFORMANCE')
gates = []
logs = {}
for scope in required:
    candidates = [v for v in history if v.get('verification_scope') == 'PR22_'+scope
                  and v.get('source_hash') == source and not v.get('source_changed_during_run')]
    assert candidates, 'Missing final-source gate '+scope
    gate = dict(candidates[-1])
    assert gate['result_status'] == 'PASS', 'Gate not PASS: '+scope
    path = ROOT/gate['evidence_reference']
    assert path.is_file(), path
    gate['evidence_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    gates.append(gate)
    logs[scope] = read(path)
expected_tests = json.loads(read(ROOT/'evidence/pr22-expected-milestone-tests.json'))
upgrade_gate = next(v for v in gates if v['verification_scope']=='PR22_UPGRADE')
assert upgrade_gate['passed']==len(expected_tests), 'Integrated count differs from actual configured methods'
assert set(upgrade_gate['test_names'])==set(expected_tests), 'Integrated test method selection incomplete'
for case in 'ABCE':
    assert 'PR22_REFERENCE_'+case in logs['HELPERS_VERIFY'], case
for case in 'DGHIJK':
    assert 'PR22_REFERENCE_'+case in logs['UPGRADE'], case
assert 'PR22_CONCURRENT_SAME_CREATE=PASS' in logs['CONCURRENCY']
assert 'PR22_CONCURRENT_TARGET_UOM=PASS' in logs['CONCURRENCY']
assert 'PR22_UPDATE_OPERATIONAL_SAFETY=PASS' in logs['OPERATIONAL-SAFETY']
performance = {}
for count in (1, 10, 100, 500, 2000):
    match = re.search('PR22_APPROVED_PERFORMANCE_'+str(count)+'=(.+)', logs['APPROVED-PERFORMANCE'])
    assert match, count
    performance[str(count)] = json.loads(match.group(1))
    value = performance[str(count)]
    value['selection_seconds_combined'] = value['phase_seconds']['selection_before']+value['phase_seconds']['selection_after']
    value['selection_timing_interpretation'] = 'The raw selection_after timer includes both calls because their third positional argument is always present. Interpret as combined before+after selector time; separate post-write time NOT_MEASURED.'

match = re.search(r'PR22_HANDOFF_SAMPLE=(.+)', logs['OPERATIONAL-SAFETY'])
assert match
sample = json.loads(match.group(1))
assert sample['state'] == 'VERIFIED' and sample['synthetic_disposable_fixture']
sample.update(source_hash=source, evidence_reference=next(v['evidence_reference'] for v in gates
              if v['verification_scope'] == 'PR22_OPERATIONAL-SAFETY'))
retention = json.loads(read(ROOT/'evidence/pr22-runtime-disposition.json'))
assert retention['status'] == 'PASS' and retention['stopped_server_status'] == 3
assert not retention['removed_paths']
save(ROOT/'evidence/pr22-committed-handoff.json', json.dumps(sample, indent=2)+'\n')
handoff = dict(status='VERIFIED', completed_at=datetime.now(timezone.utc).isoformat(),
               source_hash=source, source_files=len(ledger['files']), static_checks=ledger['checks'],
               gates=gates, performance=performance, committed_sample='evidence/pr22-committed-handoff.json',
               retained_failures=[dict(evidence=v.get('evidence_reference'), reason=v.get('blocking_reason'))
                                  for v in history if v.get('result_status') == 'FAIL'],
               runtime='evidence/pr22-runtime-disposition.json', pr23='NOT_STARTED',
               production_application='NOT_EXECUTED',
               limitations=['Browser/UAT NOT_RUN', 'FULL release suite NOT_RUN',
                            'Cold/RPC production capacity NOT_MEASURED',
                            'Scale uses one variant and distinct equal-price MOQ tiers'])
large = performance['2000']
handoff['measured_capacity_limit'] = dict(lines=2000, apply_and_actual_commit_seconds=large['seconds_including_actual_commit'], source_approval_plan_setup_seconds=large['setup_approval_and_plan_seconds'], retry_seconds=large['retry_seconds'], production_rpc_capacity='NOT_MEASURED', meaning='Functional correctness verified; substantial measured latency, not interactive/production capacity qualification.')
handoff['limitations'].append('2,000-line apply+commit63.68 minutes, setup91.85 minutes; substantial latency.')
report['pr22_handoff'] = handoff
report['current_status'] = 'PASS'
report['current_status_detail'] = 'PR22 VERIFIED for documented scope; PR23 NOT_STARTED; no production application.'
save(ROOT/'TEST_REPORT.json', json.dumps(report, indent=2)+'\n')

parts = ['''# PR22 - Transactional approved vendor price application - VERIFIED

## A - Environment

Odoo20.0 Community, existing repository retained; Python3.14.6 and PostgreSQL18.4.
Addon `vendor_price_revision_impact_simulator`. Own loopback cluster55453 and role
`codex_vpr_pr22`; HTTP/cron/outgoing operations disabled. Applied records are synthetic
fixtures only. Fixture business date2026-10-28 is distinct from the actual November2
approval/verification wall-clock timestamps in logs; no production approval is claimed.
Exact archived PR21 source and prerequisites: `pr22-predevelopment-audit.json`.

Actual native supplierinfo identity: partner, exact variant/template, company, MOQ,
original currency/UoM and inclusive dates. Material values also include price,
discount, delay, sequence and vendor names/codes. Odoo20 selection normalizes unit
prices and returns a dictionary. Last-PO fallback is recorded separately. Quantity
precision uses Product Unit decimal precision; Odoo20 UoM has no rounding field.

## B - Implementation

Immutable PR21 plans execute only under their exact PR20 authorization. Server-side
checks require selected company, explicit pricing operator, separate Purchase/Finance
source role and native operation ACLs; validate current approval/type/expiry/
invalidation, complete financial source, exact approved payload, latest plan/readiness,
persisted hashes and native before values. Optional immutable company policy separates
operator from maker/requester and/or actual approval actors/principals.

UPDATE writes only approved price/discount or expressly approved future date closure.
CREATE preserves exact original currency/UoM/MOQ/date and company/variant scope.
NO_CHANGE verifies without a native write. Shared/template conflicts block execution.
Actual selector results at MOQ and inclusive date boundaries are retained for every
line, including actual selected IDs and explicit fallback status. Equivalent approved
net prices across eligible equal-price tiers are allowed; no exact winning-ID claim
is made when native tie-breaking selects another eligible equal-price tier.

## C - Files changed

New models: `execution.py` (gateway/immutable ledger), `execution_lock.py` (versioned
native-writer scope), `execution_commit.py` (deferred actual-commit check),
`execution_policy.py` (optional separation policy), `execution_boundary.py` (explicit
future closure/create) and `execution_ui.py` (owner confirmation/history/documents).
New resources: `security/execution_security.xml`, `views/execution_views.xml` and
`tests/test_application_execution.py`. Only five old integration files changed:
manifest, model/test imports, existing application engine and intent input. All old
test cases remain byte-identical. Full hashes: `pr22-source-ledger.json`.

## D - Reference results

| Case | Genuine fixture result |
|---|---|
| A | Approved INR100 ->109 UPDATE; exact before/after ledger |
| B | MOQ100 INR109 CREATE; MOQ1 INR115 retained; native selection checked |
| C | NO_CHANGE verified; native write/create tripwires not called |
| D | Ten-line mixed UPDATE/CREATE, failure on line10: all prices/audit roll back; retry succeeds |
| E | Same plan repeated: original receipt returned, no second native mutation |
| F | Two real simultaneous CREATE requests: one rule/receipt, serialization and read-only retry |
| G | Expired authority before application and during write aborts |
| H | Target externally100 ->105: old109 plan blocked,105 retained |
| I | Wrong-variant/field arguments denied; injected defaults/context cannot redirect target |
| J | Shared-company and template-rule conflicts block, old values retained |
| K | Future109 rule inactive early; old100 history retained; explicitly approved closure/create atomic |

The assembler checks A/B/C/E markers in final QUICK, D/G-K in upgrade MILESTONE and F in
the concurrency log below. Template and owner-confirmation cases run in MILESTONE.

## E - Atomicity and recovery

One flushing savepoint covers all native writes, behavior verification and immutable
receipt insertion. No per-line commit, rollback or application cursor. Odoo owns commit.
Sorted company/batch/request, actor/group, vendor/template, explicit target-unit/ancestor and native-row locks protect
authority and targets. Versioned vendor/template epochs intersect normal native ORM
create/write/unlink, including parent/contact/shared/template competitors. Repeatable
Read snapshots serialize after conflicting commits rather than silently reuse old data.
Unique authorization and execution keys prevent duplicate application. Existing native
supplierinfo rules receive no global uniqueness constraint.

A deferred read-only PostgreSQL constraint checks all receipt targets and authority at
actual commit. Pending receipts expose no successful applied timestamp. A fresh cursor
reads VERIFIED only after commit. Genuine late-commit corruption of ten native targets
rolled back all prices and receipt; fresh retry succeeded. Before/approved-after/observed-
after values, fingerprints, exact source, operator and all selector contexts are retained.
Repeated committed requests return the original receipt; external edits are reported
without restoring an old approved price. Rolled-back failure rows cannot be called a
durable failure audit: controlled errors and price-free plan/operator logs remain.

## F - Security

No new native ACL grants or automatic group assignments. Role and native permission
checks are independent. Original-user ORM performs price writes, without native sudo.
Metadata-only attachment inspection retains existing protected-content access. Management/
audit access requires company, warehouse/cost/demand and native Sales-document scope.
Receipt CRUD/copy/forged success and attachment reassignment are denied. Internal receipt
authorship needs an opaque Python capability, not a client context flag. Confirmation
belongs to its creator and binds exact immutable plan hash. Both optional approver
separation and positive confirmation execution passed focused tests. Negative ORM/export/
company/native-permission/context-injection cases ran in the milestone.

## G - Automated tests

All following gates use the same frozen source and real nonzero test/assertion counts.
Source changes invalidate evidence; exit status alone is insufficient. Initial failures
are preserved in TEST_REPORT.json, not overwritten. Browser/UAT and FULL release suite
are NOT_RUN; cold/RPC/production capacity is NOT_MEASURED.

| Gate | Actual passed | Evidence |
|---|---:|---|
''']
for gate in gates:
    parts.append('| '+gate['verification_scope']+' | '+str(gate['passed'])+(' groups' if gate.get('test_unit') else ' tests')+' | '+gate['evidence_reference']+' |\n')
parts.append('''
Operational groups additionally prove only exact supplierinfo additions,21 other native
models unchanged and27 upstream models unchanged. Independent-process replay is tested.
Actual archived PR21 install/seed/cold capture precedes update; retained source bytes,
old financial/commercial/security/decision/delegation records and approved PR21 plan
are compared after upgrade. Zero automatic executions or native price changes on update.

### Measured committed application workload

| Lines | Apply+commit seconds | Setup/approval/plan seconds | Client SQL | Audit JSON bytes | Retry seconds |
|---:|---:|---:|---:|---:|---:|
''')
for count, value in performance.items():
    parts.append('| '+count+' | '+format(value['seconds_including_actual_commit'], '.4f')+' | '+
                 format(value['setup_approval_and_plan_seconds'], '.4f')+' | '+str(value['sql'])+' | '+
                 str(value['audit_json_bytes'])+' | '+format(value['retry_seconds'], '.4f')+' |\n')
parts.append('''
Every line uses actual native ORM creates, selector verification, immutable audit and
deferred commit guard; fresh-cursor success and no-write retry are checked. Timing/RSS
and phase breakdowns are retained in performance JSON logs. The raw selection_after
timer combines before+after selector calls; only the combined value is interpreted,
and separate post-write timing is NOT_MEASURED. The validation sub-timing
measures the PR20 source gate, not every pre-write check. Scope-lock sub-timing
measures the versioned price-scope helper, not all actor/unit/native-row lock SQL. Warm registry, one variant,
flat net price and distinct MOQ tiers; no cold/RPC/multi-SKU production capacity claim.

Retained failures include: Odoo20 UoM precision API and None/False create normalization;
bad synthetic product identity; stale approver field names and fixture group-assignment
actor; strict SQL-NULL versus ORM-zero commit verification (fixed without rewriting native metadata); race scenarios with unconsumed negotiated assumptions and stale Sales visibility
after adding demand. Production financial/access controls and old tests were not relaxed.

## H - Business safety

Supplierinfo changes stay within exact signed operational scope. Real fixture snapshots
cover PO/RFQ, SO/customer pricing, product costs, stock/reservations/moves/packages,
valuation, accounting, FX, mail and cron, plus upstream analytical evidence. No existing
document onchange/repricing, stock operation, valuation adjustment, accounting posting,
external communication or live operation is invoked by the application service.
Synthetic operational setup is separate from application. Applied price rules do not
claim realized savings or accounting profit.

## I - Progress

PR22 VERIFIED for the documented tested scope. TEST_REPORT.json retains actual history,
source hashes, counts, logs, measured limits and failure explanations; DEVELOPMENT_PROGRESS
records the verified handoff. No current mandatory blocker for this scope. Browser/UAT
and FULL release remain NOT_RUN. Owned runtime/filestore are stopped and retained under
TESTING_POLICY.md:51; no databases deleted.

## J - PR23 handoff

`pr22-committed-handoff.json` contains a genuine durable synthetic execution reference,
exact approved source payload and authority, company/vendor/variant, original currency/
UoM/MOQ/dates, created/updated counts, before/after values, source/target fingerprints,
operator, actual selected rule IDs and authoritative-after-commit verification timestamp.
The timestamp records in-transaction verification, becoming authoritative on commit;
it is not claimed to be PostgreSQL's precise commit timestamp.

PR23 must retain historical receipts, compare external edits/missing targets/source and
boundary/selection and target-unit/ancestor factor drift, scope audit per company and preserve original authority.
Incident review must distinguish historical successful execution from current target
integrity. Any compensating write needs current separately approved scope and conflict
review; no blind restoration or duplicate retry. Monitoring, exception/recovery proposals,
long-term reconciliation and response controls are handoff requirements only. No cron,
automatic rollback, historical repair or recovery execution is implemented. STOP after
PR22. PR23 NOT_STARTED.
''')
parts.append('\nFrozen source `'+source+'`; '+str(len(ledger['files']))+' files and '+str(ledger['checks'])+' static checks.\n')
save(ROOT/'evidence/DEV-11-pr22-summary.md', ''.join(parts))
progress = read(ROOT/'DEVELOPMENT_PROGRESS.md').splitlines()
for index, line in enumerate(progress):
    if line.startswith('| PR-22 |'):
        progress[index] = ('| PR-22 | DEV-11 transactional approved vendor price application | VERIFIED | '
                           'Final-source fresh/QUICK/TARGETED, actual PR21 upgrade MILESTONE/preservation, '
                           'races, commit/replay and scale PASS | evidence/DEV-11-pr22-summary.md; TEST_REPORT.json | '
                           'Synthetic applications only; browser/FULL NOT_RUN; no production capacity claim | '
                           'None for documented scope | '+datetime.now(timezone.utc).date().isoformat()+
                           ' | STOP after PR22; PR23 NOT_STARTED |')
save(ROOT/'DEVELOPMENT_PROGRESS.md', '\n'.join(progress)+'\n\n## PR22 verified handoff\n\n'+
     'Final source '+source+'; exact gates/counts, A-K cases, actual PR21 preservation, committed synthetic '
     'execution, no-unrelated-write snapshots, races, scale limits and retained failures are in '
     'evidence/DEV-11-pr22-summary.md and TEST_REPORT.json.pr22_handoff. No production application. '
     'Runtime retained stopped; no databases deleted. STOP after PR22; PR23 NOT_STARTED.\n')
doc = ROOT/'docs/TRANSACTIONAL_VENDOR_PRICE_APPLICATION.md'
text = read(doc).replace('Verification is IN_PROGRESS until the source-bound gates finish.',
                         'Verification is VERIFIED for the source-bound scope in evidence/DEV-11-pr22-summary.md; browser/FULL release tests remain NOT_RUN.')
save(doc, text)
running = ROOT/'evidence/pr22-running-state.json'
if running.exists():
    state = json.loads(read(running))
    state.update(status='VERIFIED', completed_at=handoff['completed_at'], active_exec_session=None,
                 active_phase='COMPLETE', pending=[], remaining_queue=[], final_report='evidence/DEV-11-pr22-summary.md')
    save(running, json.dumps(state, indent=2)+'\n')
print('PR22_FINAL_HANDOFF=PASS '+source)
