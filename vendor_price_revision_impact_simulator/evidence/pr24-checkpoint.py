"""Record only executed PR24 evidence; deliberately do not certify full PR24."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
path = ROOT/'TEST_REPORT.json'
report = json.loads(path.read_text(encoding='utf-8-sig'))
ledger = json.loads((ROOT/'evidence/pr24-source-ledger.json').read_text(encoding='utf-8'))
source_hash = ledger['source_hash']
history = [record for record in report['history'] if record.get('prompt_id') == 'PR-24']
current = [record for record in history if record.get('source_hash') == source_hash and record.get('result_status') == 'PASS' and not record.get('source_changed_during_run')]
quick = next(record for record in reversed(current) if record.get('verification_scope') == 'PR24_FINAL_UPGRADE')
outputs_run = next(record for record in reversed(current) if record.get('verification_scope') == 'pr24-output-probe_PR24')
preservation = next(record for record in reversed(current) if record.get('verification_scope') == 'pr24-preservation-probe_PR24')
assert quick['passed'] > 0 and outputs_run['passed'] == 7 and preservation['passed'] == 2
targeted = next(record for record in reversed(history) if record.get('verification_scope') == 'PR24_TARGETED' and record['result_status'] == 'PASS' and not record.get('source_changed_during_run'))
fresh = next(record for record in reversed(history) if record.get('verification_scope') == 'PR24_FRESH_MILESTONE' and record['result_status'] == 'PASS' and not record.get('source_changed_during_run'))
assert targeted['passed'] == 17 and fresh['passed'] == 40
outputs = json.loads((ROOT/'evidence/pr24-output-results.json').read_text(encoding='utf-8'))
assert len(outputs) == 7 and sum(len(row['artifacts']) for row in outputs) == 21
for row in outputs:
    for artifact in row['artifacts']:
        file = ROOT/'evidence'/artifact['file']
        assert file.resolve().is_relative_to(ROOT/'evidence')
        assert file.stat().st_size == artifact['bytes']
        assert hashlib.sha256(file.read_bytes()).hexdigest() == artifact['sha256']
for record in (quick, targeted, fresh, outputs_run, preservation):
    file = Path(record['evidence_reference'])
    if not file.is_absolute():
        file = ROOT/file
    assert file.is_file() and file.stat().st_size > 0
    record['evidence_sha256'] = hashlib.sha256(file.read_bytes()).hexdigest()
assert all(not (ROOT/name/'postmaster.pid').exists() for name in ('.pr23_pgdata', '.pr24_pgdata'))
remaining = [
    'Complete per-adapter source issue and confidence presentation',
    'Full revision-to-execution chronology; current history adapter is incident-event scoped',
    'Richer scenario comparability, friendly source selection and drill-down UI',
    'Remaining report-category integration fixtures and actual report concurrency tests',
    'Explicit decision on optional current-freshness/immutable report-retention scope',
]
gate_records = [{key: record.get(key) for key in ('verification_scope', 'result_status', 'passed', 'failed', 'test_unit', 'source_hash', 'source_changed_during_run', 'evidence_reference', 'evidence_sha256')} for record in (quick, targeted, fresh, outputs_run, preservation)]
report['pr24_handoff'].update(status='IN_PROGRESS', verified_subset_status='PASS',
    checkpoint_at=datetime.now(timezone.utc).isoformat(), current_source_hash=source_hash,
    current_source_files=ledger['file_count'], source_ledger='evidence/pr24-source-ledger.json',
    gate_records=gate_records, outputs_manifest='evidence/pr24-output-results.json', output_files=21,
    actual_upgrade=dict(source_database='codex_vpr_pr23_upgrade_4_20261102',
        target_database='codex_vpr_pr24_upgrade_1_20261103', stored_models_preserved=100,
        original_source_files=16, original_source_bytes=114956,
        validated_cold_baseline='evidence/pr24-cold-pr23-preservation-v2.json'),
    runtime_state='Both PR23 and PR24 owned clusters stopped; all databases retained',
    remaining_acceptance=remaining, full_release='NOT_RUN', browser='NOT_RUN', report_concurrency='NOT_RUN',
    next_prompt='PR25 NOT_STARTED', summary='evidence/DEV-12-pr24-summary.md')
report['current_status_detail'] = 'PR24 IN_PROGRESS. Executed reporting subset passes; full acceptance remains open. Source-specific gates are retained without conflating earlier and final source hashes.'
path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
progress = ROOT/'DEVELOPMENT_PROGRESS.md'
text = progress.read_text(encoding='utf-8')
old = '| PR-24 | DEV-12 advanced financial and audit reporting | IN_PROGRESS | Earlier-source TARGETED 17 PASS; final fresh milestone/upgrade pending | evidence/pr24-predevelopment-audit.json; docs/ADVANCED_FINANCIAL_AND_AUDIT_REPORTING.md; TEST_REPORT.json | 17 retained-fact adapters; secure formats; remaining acceptance scope documented | Final-source verification and full report acceptance pending | 2026-11-03 | PR25 NOT_STARTED |'
new = '| PR-24 | DEV-12 advanced financial and audit reporting | IN_PROGRESS | QUICK11, TARGETED17, earlier-source fresh MILESTONE40; actual upgrade/preservation and seven report output groups PASS (source hashes explicit) | evidence/DEV-12-pr24-summary.md; TEST_REPORT.json | 17 retained-fact adapters; 21 validated output files; 100 original models/16 source files preserved | Full chronology, confidence/issues, remaining category fixtures and report concurrency pending | 2026-11-03 | PR25 NOT_STARTED |'
assert old in text
text = text.replace(old, new)
text += '\n## PR24 tested subset handoff\n\nCurrent source '+source_hash+' has 153 source files; 144 prior files remain identical.\nFinal-source QUICK11, seven genuine report/output groups and original-data/source-byte\npreservation pass. TARGETED17 and fresh MILESTONE40 pass on their explicitly recorded\nsource versions; later presentation/precision changes have separate runtime evidence.\nActual PR23 upgrade preserves 100 stored models and all16 original vendor files\n(114956 bytes; nonempty SHA256/native SHA1/size checks). Seven report types produced\n21 validated PDF/XLSX/CSV files; original data hashes remain identical afterward.\nBoth owned clusters are stopped; no databases deleted. Required remaining scope is\nlisted in TEST_REPORT.json.pr24_handoff.remaining_acceptance and the A-J summary.\nPR24 remains IN_PROGRESS. PR25 NOT_STARTED.\n'
progress.write_text(text, encoding='utf-8')
print(json.dumps(dict(status='IN_PROGRESS', source_hash=source_hash, gate_records=gate_records, output_files=21, remaining_acceptance=remaining)))
