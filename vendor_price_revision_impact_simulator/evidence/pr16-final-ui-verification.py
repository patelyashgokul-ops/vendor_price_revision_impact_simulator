import subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
for phase in ('fresh','helpers_verify','targeted'):
 print('PR16_FINAL_UI_PHASE='+phase,flush=True)
 subprocess.run([sys.executable,str(r/'evidence/pr16-verification-driver.py'),phase,*(['4'] if phase=='fresh' else [])],check=True,cwd=r)
print('PR16_FINAL_UI_SEQUENCE=PASS',flush=True)
