"""Sequential PR13 final-source gates against the owned disposable cluster."""
import subprocess
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for phase in ('fresh','helpers_verify','targeted','upgrade','concurrency','operations'):
 print('PR13_FINAL_PHASE='+phase,flush=True)
 subprocess.run([sys.executable,str(root/'evidence/pr13-verification-driver.py'),phase,*(['4'] if phase=='fresh' else [])],check=True,cwd=root)
print('PR13_FINAL_SEQUENCE=PASS',flush=True)
