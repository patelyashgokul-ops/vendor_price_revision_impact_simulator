"""Sequential final-source PR17 gates; fail immediately, retain every failure."""
import hashlib,json,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
ledger=json.loads((r/'evidence/pr17-verified-source-sha256.json').read_text(encoding='utf-8'))
sha=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
report=json.loads((r/'TEST_REPORT.json').read_text(encoding='utf-8'))
fresh=[v for v in report['history'] if v.get('verification_scope')=='PR17_FRESH' and v.get('source_hash')==sha and v.get('source_changed_during_run') is False]
assert fresh and fresh[-1]['result_status']=='PASS','Complete final-source fresh installation first'
for phase in ('helpers_verify','targeted','upgrade_verify','concurrency','operations'):
 print('PR17_FINAL_PHASE='+phase,flush=True)
 subprocess.run([sys.executable,str(r/'evidence/pr17-verification-driver.py'),phase],cwd=r,check=True)
print('PR17_VERIFICATION_SEQUENCE=PASS',flush=True)
