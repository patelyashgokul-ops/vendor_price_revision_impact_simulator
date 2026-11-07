"""Run only outstanding authorized PR19 gates sequentially; stop on any failure."""
import subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for phase,attempt in [('activity_guard','2'),('fresh','2'),('helpers_verify','2'),('targeted','2'),('upgrade','1'),('operations','4'),('concurrency','5'),('performance','1')]:
 print('PR19_NEXT_GATE='+phase,flush=True)
 subprocess.run([sys.executable,str(root/'evidence/pr19-verification-driver.py'),phase,attempt],cwd=root,check=True)
print('PR19_SEQUENTIAL_GATES=COMPLETE',flush=True)
