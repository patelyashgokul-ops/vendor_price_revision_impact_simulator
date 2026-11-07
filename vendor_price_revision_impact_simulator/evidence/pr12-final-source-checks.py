"""Final installation/QUICK/changed-security gates after metadata hardening."""
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
for phase,attempt in [('fresh','3'),('helpers_verify','1'),('upgrade_verify','1'),('concurrency','1'),('operations','1')]:
    print('PR12_FINAL_SOURCE_PHASE='+phase,flush=True)
    subprocess.run([sys.executable,str(root/'evidence/pr12-verification-driver.py'),phase,attempt],check=True,cwd=root)
print('PR12_FINAL_SOURCE_CHECKS=PASS',flush=True)
