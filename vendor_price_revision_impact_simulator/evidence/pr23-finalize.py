"""Fail-closed final handoff assembled only from real, source-bound executed gates."""
import ast
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime,timezone
from pathlib import Path
root=Path(__file__).resolve().parents[1]
report_path=root/'TEST_REPORT.json'
report=json.loads(report_path.read_text(encoding='utf-8-sig'))
for old_run in report['history']:
 if (old_run.get('invocation') in ('Odoo shell evidence/pr23-preservation-probe.py','Odoo shell evidence/pr23-capture-probe.py') and
     old_run.get('environment',{}).get('database') in ('codex_vpr_pr23_upgrade_1_20261102','codex_vpr_pr23_upgrade_2_20261102')):
  old_run.update(evidence_invalidated=True,valid_for_handoff=False,
   invalidation_reason='Synthetic clone filestore was missing during the original cold capture. The source-byte subclaim compared empty content and is invalid; original model hashes were checked, but this gate cannot qualify file preservation. Replaced by direct final-source PR22 clone4 update with copied filestore, nonempty checks and all-original-file checksum evidence.')
ledger=json.loads((root/'evidence/pr23-source-ledger.json').read_text(encoding='utf-8'))
source=ledger['source_hash']
assert ledger['result_status']=='PASS'
assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==fp for n,fp in ledger['files'].items())
records=[r for r in report['history'] if r.get('prompt_id')=='PR-23' and r.get('source_hash')==source and
 r.get('result_status')=='PASS' and not r.get('source_changed_during_run') and not r.get('evidence_invalidated')]
def select(predicate):
 rows=[r for r in records if predicate(r)]
 assert rows,'Missing required source-bound actual gate'
 r=dict(rows[-1]);assert r.get('passed',0)>0 and r.get('failed')==0
 return r
gates={
 'QUICK':select(lambda r:r.get('verification_scope') in ('PR23_QUICK','PR23_CLONE_UPGRADE') and 'upgrade_4_' in r.get('environment',{}).get('database','')),
 'PRESERVATION':select(lambda r:r.get('invocation')=='Odoo shell evidence/pr23-preservation-probe.py'),
 'SOURCE_FILES':select(lambda r:r.get('invocation')=='Odoo shell evidence/pr23-filestore-probe.py'),
 'TARGETED':select(lambda r:r.get('invocation')=='Odoo shell evidence/pr23-probe-probe.py'),
 'SECURITY':select(lambda r:r.get('invocation')=='Odoo shell evidence/pr23-security-probe.py'),
 'CONCURRENCY':select(lambda r:r.get('invocation')=='Odoo shell evidence/pr23-concurrency-probe.py'),
 'SUCCESSOR':select(lambda r:r.get('invocation')=='Odoo shell evidence/pr23-successor-probe.py'),
 'SUPERSEDED_DEDUP':select(lambda r:r.get('invocation')=='Odoo shell evidence/pr23-superseded-dedup-probe.py'),
 'PERFORMANCE':select(lambda r:r.get('invocation')=='Odoo shell evidence/pr23-performance-probe.py'),
 'MILESTONE':select(lambda r:r.get('verification_scope')=='PR23_MILESTONE'),
 'FRESH':select(lambda r:r.get('verification_scope')=='PR23_FRESH'),
}
classes={}
for path in (root/'tests').glob('test_*.py'):
 for node in ast.parse(path.read_text(encoding='utf-8')).body:
  if isinstance(node,ast.ClassDef):classes[node.name]={node.name+'.'+m.name for m in node.body if isinstance(m,ast.FunctionDef) and m.name.startswith('test_')}
base=('TestModuleFoundation','TestMonitorMath','TestMonitorPending')
milestone=base+('TestExecutionQuick','TestExecutionControls','TestApplicationQuick','TestDecisionQuick','TestDecisionValidity','TestDecisionSecurity')
contents={}
for name,gate in gates.items():
 original=gate['evidence_reference'];path=Path(original);path=path if path.is_absolute() else root/path
 raw=path.read_bytes();content=raw.decode('utf-8');contents[name]=content
 assert gate['exit_status']==0 and gate.get('source_hash')==source
 if name in ('QUICK','MILESTONE','FRESH'):
  expected=set().union(*(classes[c] for c in (milestone if name=='MILESTONE' else base)))
  actual=set(re.findall(r'Starting (Test[A-Za-z0-9_]+\.test_[A-Za-z0-9_]+) \.\.\.',content))
  assert actual==expected,(name,sorted(expected-actual),sorted(actual-expected))
  assert gate['passed']==len(expected),(name,gate['passed'],len(expected))
  gate['test_names']=sorted(actual)
 reference=('evidence/'+path.name if path.name.startswith('pr23-final-'+name.lower()+'-') else
            'evidence/pr23-final-'+name.lower()+'-'+path.name)
 destination=root/reference
 if path.resolve()!=destination.resolve():shutil.copyfile(path,destination)
 gate.update(evidence_reference=reference,evidence_sha256=hashlib.sha256(raw).hexdigest())
 for history in report['history']+[report['latest_run']]:
  if history.get('started_at')==gate['started_at'] and history.get('evidence_reference')==original:
   history.update(evidence_reference=reference,evidence_sha256=gate['evidence_sha256'])
   if gate.get('test_names'):history['test_names']=gate['test_names']
performance=[json.loads(line.split('=',1)[1]) for line in contents['PERFORMANCE'].splitlines() if line.startswith('PR23_PERFORMANCE=')]
assert [p['actual_applied_lines'] for p in performance]==[10,100,500,2000]
assert all(p['observed_lines']>0 and p['observed_lines']<=p['actual_applied_lines'] for p in performance)
assert all(set(p['counts'])<={'PASS','EXPECTED_CHANGE'} for p in performance)
lookup=next(json.loads(line.split('=',1)[1]) for line in contents['PERFORMANCE'].splitlines() if line.startswith('PR23_PERFORMANCE_REFERENCE_LOOKUP='))
assert lookup['reference_count']==10000
pg=Path(r'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe')
runtime={}
for cluster in ('.pr22_pgdata','.pr23_pgdata'):
 result=subprocess.run([str(pg),'-D',str(root/cluster),'status'],capture_output=True,text=True)
 assert result.returncode==3,(cluster,result.stdout,result.stderr)
 runtime[cluster]=dict(status_exit_code=result.returncode,state='STOPPED_RETAINED')
now=datetime.now(timezone.utc).isoformat()
(root/'evidence/pr23-runtime-disposition.json').write_text(json.dumps(dict(checked_at=now,clusters=runtime,
 databases_deleted=False,production_used=False),indent=2)+'\n',encoding='utf-8')
failed=[r for r in report['history'] if r.get('prompt_id')=='PR-23' and r.get('result_status') in ('FAIL','BLOCKED')]
invalidated=[r for r in report['history'] if r.get('prompt_id')=='PR-23' and r.get('evidence_invalidated')]
file_proof=next(json.loads(line.split('=',1)[1]) for line in contents['SOURCE_FILES'].splitlines() if line.startswith('PR23_SOURCE_FILES='))
assert file_proof['original_source_files']>0 and file_proof['total_verified_bytes']>0
limitations=[
 'Odoo20 native supplierinfo has no active field: native-target archive scenario is NOT_APPLICABLE; product archiving and optional archive-aware code are separate.',
 'Benchmark budgets can leave PARTIAL coverage. Unobserved records are NOT_RUN, not PASS. No production throughput/RPC capacity qualification.',
 '10000 reference lookup repeats real authorized lines; it is not10000 distinct application events or10000 full integrity observations.',
 'No notification activities/emails, documented-exception waivers, automatic correction, complete forensic reconstruction, browser UAT or release-level FULL suite.',
 'Existing warehouse/cost/customer-order source scope and native Sales read authority are prerequisites; shared products do not grant access.',
 'A snapshot observation is not a permanent guarantee. A single native selector/source validation can exceed the cooperative chunk time budget.',
]
handoff=dict(status='VERIFIED',completed_at=now,source_hash=source,source_files=len(ledger['files']),static_checks=ledger['checks'],
 gates=[dict(name=n,**g) for n,g in gates.items()],performance=performance,reference_lookup=lookup,
 retained_failed_or_blocked_runs=len(failed),prior_failures_retained=True,unresolved_functional_failures=[],limitations=limitations,
 invalidated_earlier_source_byte_subclaims=len(invalidated),source_file_verification=file_proof,
 native_price_writes_by_monitoring=False,production_application=False,automatic_restore=False,next_prompt='PR-24 NOT_STARTED',
 runtime_evidence='evidence/pr23-runtime-disposition.json',documentation='docs/POST_APPLICATION_PRICE_MONITORING.md')
report['pr23_handoff']=handoff;report['current_status']='PASS';report['current_status_detail']='PR23 VERIFIED for documented read-only functional scope; bounded coverage/performance limits disclosed; PR24 NOT_STARTED.'
report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
progress_path=root/'DEVELOPMENT_PROGRESS.md';progress=progress_path.read_text(encoding='utf-8')
progress='\n'.join('| PR-23 | DEV-12 post-application monitoring and operational integrity | VERIFIED | Final-source QUICK/TARGETED/security/races/successor/performance/MILESTONE/fresh and actual PR22-data preservation PASS | evidence/DEV-12-pr23-summary.md; TEST_REPORT.json | Read-only scope; bounded benchmark coverage; supplierinfo archive N/A; FULL/browser NOT_RUN | None for documented functional scope | 2026-11-02 | STOP after PR23; PR24 NOT_STARTED |' if line.startswith('| PR-23 |') else line for line in progress.split('\n'))
progress=progress.split('\n\n## PR23 verified handoff\n')[0]
progress+='\n\n## PR23 verified handoff\n\nFinal source '+source+'; '+str(ledger['checks'])+' static checks and exact source-bound gates are recorded in TEST_REPORT.json.pr23_handoff and evidence/DEV-12-pr23-summary.md. Monitoring never changes operational prices; synthetic setup and separately authorized PR22 fixture applications are distinguished. Benchmark partial coverage is explicitly retained. Both owned clusters stopped; all databases retained. STOP after PR23; PR24 NOT_STARTED.\n'
progress_path.write_text(progress,encoding='utf-8')
counts='\n'.join('| '+n+' | '+str(g['passed'])+' | '+g['test_level']+' | ['+Path(g['evidence_reference']).name+']('+Path(g['evidence_reference']).name+') |' for n,g in gates.items())
bench='\n'.join('| '+str(p['actual_applied_lines'])+' | '+str(p['observed_lines'])+' | '+format(p['duration_seconds'],'.3f')+' | '+p['coverage']+' | '+str(p['sql_client_count'])+' |' for p in performance)
summary=f'''# PR23 / DEV12 implementation, testing and handoff

Status: VERIFIED for the documented read-only functional scope. Completed {now}.
Final source `{source}`; {len(ledger['files'])} business files; {ledger['checks']} static checks.
PR24 is NOT_STARTED. No production database or production application was used.

## A — Environment

Odoo20.0 Community, retained existing repository; official [stable Community builds](https://nightly.odoo.com/) verified at development start. Python3.14.6, PostgreSQL18.4, existing Community dependencies base/product/purchase_stock/sale_stock/mail and openpyxl/lxml. Final-source dedicated loopback synthetic databases: codex_vpr_pr23_upgrade_4_20261102 (direct PR22 update, file preservation, functional/integration probes) and codex_vpr_pr23_fresh_4_20261102 (fresh installation). Earlier attempts remain retained separately. The exact archived139-file PR22 source and its retained synthetic database supplied genuine committed applications, protected operational history and original source files. Both owned clusters are stopped and all databases retained.

Supplierinfo has the15 PR22 material fields and normal write_uid/write_date; no native active field. Odoo20 returns a dictionary from its pure native supplier selector. Price uses minimum display digits rather than fixed storage rounding; UoM conversion definitions are captured separately from display labels.

## B — Implementation

Immutable source/company-scoped runs, checks, incident events and correction proposals reuse existing guards. Committed receipt/authorization/plan/line fingerprints remain the original authority, independent of current approval expiry. Exact target existence, permissions, company, vendor, variant/template, price, discount, currency, MOQ, dates, units and recorded commercial metadata are checked. Frozen unit factors/hierarchy and product eligibility scope are also compared. Missing and inaccessible targets are distinct; no similar-name substitution occurs.

Native selector comparisons retain exact quantity/date/vendor/product/company/UoM contexts and detect selection drift and duplicate expected identities. Unsupported schema/selector evidence is BLOCKED. Current configuration at a historical reference date is not a full historical reconstruction. write_uid/write_date are supplementary observations, never proof of unauthorized conduct.

Later independently approved committed PR22 events replace compatible expectations while retaining the earlier event. Incidents preserve first detection, latest observations, recurring material changes, reasons and review history. Verified closure needs clean revalidation and a fresh closure check. Repeated anomalies deduplicate; verified-closed recurrence reopens. Source-authorized owners can investigate or plan a correction; proposals never grant price authority or choose the old price automatically.

Old and current observations bind a current anomaly to the verified effective execution line, preventing duplicate active cases across superseded events. Stepwise price/boundary/price comparison is covered by an isolated comparator unit with authorization deliberately assumed valid; it is not a claim of four real approvals. The separate committed two-event successor probe exercises actual independent governance and PR22 execution.

Manual exact/selected observations and owner/company-scoped periodic revalidation are bounded. Scheduler and policy are disabled by default. Progress uses execution-line IDs and cyclic rechecks, not target write_date. No sudo in services, no business commits, no external messages or automatic activities. Overlapping monitor/review operations use nonblocking execution locks, policy progress locks, unique incident keys and versioned ORM writes.

## C — Files changed

Three existing integration files only: __manifest__.py adds security/data/views; models/__init__.py registers monitoring; tests/__init__.py registers new tests. All prior test modules and all other prior business files remain byte-identical.

New business files: models/monitor_math.py (comparisons/classification), monitor_models.py (immutable history and lifecycle), monitor_service.py (read-only source/current checks), monitor_policy.py (bounded scheduling), monitor_ui.py (secure review input/files), security/monitor_security.xml (role/company/source ACLs), data/monitor_cron.xml (inactive cron), views/monitor_views.xml (Community UI/navigation), tests/test_price_monitoring.py (precision/registration/pending-source tests). Supporting reproducible probes, drivers, ledgers and logs live under evidence/. Documentation: [POST_APPLICATION_PRICE_MONITORING.md](../docs/POST_APPLICATION_PRICE_MONITORING.md). Progress and test evidence are in DEVELOPMENT_PROGRESS.md and TEST_REPORT.json.

## D — Actual reference results

| Reference | Actual synthetic result |
|---|---|
| A | Committed109 current109 PASS; original scope is USD per Box10, declared rather than relabelled INR/Piece. |
| B |109 to112: PRICE_DRIFT, +USD3/Box10; no restoration. |
| C | A separate fully approved PR22 application commits112; original109 event retained and current112 recognized as AUTHORIZED_SUCCESSOR. |
| D | A genuine applied MOQ100 Unit rule changed to10: MOQ_DRIFT. |
| E | Genuine USD11/Unit changed to INR11/Unit: CURRENCY_DRIFT; no false numeric equivalence/FX conversion. |
| F | Native supplierinfo archiving is NOT_APPLICABLE on this schema. Archived product eligibility is separately detected; exact missing and inaccessible target cases both pass. |
| G | A real native-selected competing rule with gross115 and90% discount changes the winner; RULE_SELECTION_DRIFT and duplicate identity detected. Odoo20's default price-first selector would not choose undiscounted115 over109 merely because sequence changed. |
| H | Future approved rule before activation remains intact; no unauthorized-change claim. |
| I | Repeated scan keeps one incident per exact anomaly key; changed observations and recurrence retained. |
| J | Unestablished agreement produces EVIDENCE_REQUIRED proposal with no invented target price; fresh approval/dry-run required and no operational write. |

## E — Incidents

Deterministic scope-critical, commercial-high and metadata/unsupported-selection warning categories. Detecting manager initially owns the case; assignment requires existing active company/source authority. No arbitrary monetary threshold or realized-loss inference. Investigation, evidence requests, correction planning, revalidation, verified closure and reopening are server-controlled. Comment-only and proposal-only closure are denied. Documented-exception waiver is unsupported by the implemented policy. Test-created recurring cases remain retained in the synthetic database; their retained state is test evidence, not a production incident claim.

## F — Monitoring and measured performance

At most100 admitted lines per exact window,1–100 schedule batch size,1–168 hour configured frequency, periodic deterministic cursor reset,20-second cooperative observation budget and explicit partial state. A single native operation can exceed that budget. No notification spam is possible because this scope emits no automatic activities or emails.

Warm registry, original-user native selectors, actual committed PR22 data, tracemalloc overhead included, client SQL count only; pages rolled back after measurement. These are observations, not production/RPC throughput qualification.

| Applied lines | Actually observed | Seconds | Coverage | Client SQL |
|---|---|---|---|---|
{bench}

The10000-reference read-only indexed lookup used {lookup['distinct_authorized_lines']} distinct real authorized lines repeated to10000 references, in {lookup['duration_seconds']:.6f}s. It is not10000 distinct application events or10000 full integrity checks. No synthetic successful history was forged to fill a benchmark.

## G — Security

Company and all constituent warehouse/cost/customer-order source rules apply to read/search/group/export and drill-down. Public/portal/sales-only/purchase-user access is denied; auditors read only with their independently granted source/native Sales authority and cannot review. Foreign-company ownership and source-line injection fail. Direct evidence CRUD/copy, guessed context capabilities, verified-status forgery and extra monitoring attachments fail. Services never grant native supplierinfo permissions. Cron executes only its original authenticated schedule owner in authorized company scope.

## H — Executed tests and evidence

| Gate | Passed | Level | Evidence |
|---|---|---|---|
{counts}

Runner test names equal the AST-derived exact selection for QUICK, MILESTONE and FRESH; successful exits alone are not treated as evidence. The actual PR22 database and its original filestore were copied into a dedicated clone, captured under archived PR22 code, directly updated with final PR23 source, and checked against original stored-field/relation hashes and nonempty source bytes. Source-file verification covers all {file_proof['original_source_files']} original supplier files / {file_proof['total_verified_bytes']} bytes against immutable source SHA256, native SHA1 and size. {len(failed)} earlier FAIL/BLOCKED runs remain in history. Separately, {len(invalidated)} earlier capture/preservation subclaims are explicitly invalidated: the initial database-only clone omitted its filestore and an empty-read comparison did not prove source-byte preservation. Original files were retained;157 original physical files were copied/verified, the harness was corrected and a new direct upgrade/file gate replaced that evidence. Other corrected issues include sandbox TCP/log placement, JSON empty-list/empty-proposal representation, immutable CREATE before-null versus ORM-False comparison and synthetic successor account/warehouse/grant setup. No relevant functional failure remains unresolved. FULL release/browser UAT and10000 distinct historical applications are NOT_RUN.

Reproduce using evidence/pr23-static-check.py and evidence/pr23-verification-driver.py. Invocations and real timestamps, database identities and source/evidence hashes are retained in TEST_REPORT.json.pr23_handoff. Test runner configurations explicitly disable outgoing email, external API mutation, cron processing, real payments and live accounting.

## I — Business safety

Monitoring, incident review, cron and correction planning perform no supplierinfo create/write/unlink, restore or rollback; no PO/RFQ/SO/customer-pricelist mutation; no stock/reservation/valuation changes; no accounting postings or currency/UoM changes; no unapproved application or external messages. Operational CRUD tripwires cover these models in actual monitor/lifecycle tests. Synthetic fixture setup and the separately authorized PR22 successor application are the only intentional test operational changes and are distinct from PR23 feature execution. Production use: none.

## J — Progress and limitations

PR23 VERIFIED for documented functional scope; TEST_REPORT.json and DEVELOPMENT_PROGRESS.md updated from actual evidence. No functional blocker. Coverage and capacity limits, unavailable native archiving, no waiver/notification integration, snapshot-time interpretation and unexecuted release/browser qualification remain explicit. Runtime disposition: [pr23-runtime-disposition.json](pr23-runtime-disposition.json).

## K — PR24 handoff

Use the original approval/plan/execution audit with separate current checks, successor links, incident observations, recurrence, resolution events, correction proposals and schedule versions. Any management totals must reconcile to authorized company/source detail and distinguish clean, drift, blocked and partial coverage. Preserve currency/UoM/quantity basis and confidence; unit-price drift is not realized financial loss. Future audit exports must enforce the same access/attachment/formula boundaries and retention policy. Notification/waiver/correction governance, management analytics, compliance exports, archival policy and release-level integration require separate scope. PR24 has not been started.
'''
(root/'evidence/DEV-12-pr23-summary.md').write_text(summary,encoding='utf-8')
print(json.dumps(dict(status=handoff['status'],source_hash=source,gates={n:g['passed'] for n,g in gates.items()},
 summary='evidence/DEV-12-pr23-summary.md',runtime=runtime),indent=2))
