"""Final fresh/QUICK/changed-security gates after the last audit/lifecycle additions."""
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
for phase,attempt in [('fresh','5'),('helpers_verify','1'),('targeted','1'),('upgrade_verify','1'),('concurrency','1'),('operations','1')]:
    print('PR11_FINAL_SOURCE_PHASE='+phase,flush=True)
    subprocess.run([sys.executable,str(root/'evidence/pr11-verification-driver.py'),phase,attempt],check=True,cwd=root)
print('PR11_FINAL_SOURCE_SEQUENCE=PASS',flush=True)
