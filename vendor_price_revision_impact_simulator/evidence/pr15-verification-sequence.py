import subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
for phase in ('fresh','helpers_verify','targeted','upgrade','concurrency','operations'):
 print('PR15_PHASE='+phase,flush=True)
 subprocess.run([sys.executable,str(r/'evidence/pr15-verification-driver.py'),phase,*(['3'] if phase=='fresh' else [])],check=True,cwd=r)
print('PR15_FINAL_SEQUENCE=PASS',flush=True)
