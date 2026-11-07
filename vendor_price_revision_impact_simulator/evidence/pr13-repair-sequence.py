import subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for phase in ('helpers_verify','upgrade_verify','concurrency','operations'):
 print('PR13_REPAIR_PHASE='+phase,flush=True)
 subprocess.run([sys.executable,str(root/'evidence/pr13-verification-driver.py'),phase],check=True,cwd=root)
print('PR13_REPAIR_SEQUENCE=PASS',flush=True)
