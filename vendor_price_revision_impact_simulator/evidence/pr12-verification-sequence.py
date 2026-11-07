"""Sequential isolated PR12 gates; never run two phases concurrently."""
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
for phase,attempt in [('helpers_verify','1'),('targeted','1'),('fresh','2'),('upgrade','1'),('concurrency','1'),('operations','1')]:
    print('PR12_PHASE='+phase,flush=True)
    subprocess.run([sys.executable,str(root/'evidence/pr12-verification-driver.py'),phase,attempt],check=True,cwd=root)
print('PR12_SEQUENCE=PASS',flush=True)
