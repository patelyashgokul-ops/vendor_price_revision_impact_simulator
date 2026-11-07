"""Sequential, fail-fast verification; each audited driver phase owns its cluster."""
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
for phase,attempt in [('targeted','1'),('helpers_verify','1'),('fresh','3'),('upgrade','1'),('concurrency','1'),('operations','1')]:
    print('PR11_VERIFICATION_PHASE='+phase,flush=True)
    subprocess.run([sys.executable,str(root/'evidence/pr11-verification-driver.py'),phase,attempt],check=True,cwd=root)
print('PR11_VERIFICATION_SEQUENCE=PASS',flush=True)
