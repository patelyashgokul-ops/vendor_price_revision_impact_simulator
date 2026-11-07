import subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for phase in ('fresh','helpers_verify','targeted','upgrade','concurrency','operations'):
 print('PR14_FINAL_PHASE='+phase,flush=True)
 subprocess.run([sys.executable,str(root/'evidence/pr14-verification-driver.py'),phase,*(['5'] if phase=='fresh' else [])],check=True,cwd=root)
print('PR14_FINAL_SEQUENCE=PASS',flush=True)
