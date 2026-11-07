"""Serial final-source gates; stop on any unresolved failure."""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[1]
for phase in sys.argv[1:]:
 print('PR23_GATE_START '+phase+' '+datetime.now(timezone.utc).isoformat(),flush=True)
 attempt='5' if phase=='fresh' else '4'
 kind='fresh' if phase=='fresh' else 'upgrade'
 result=subprocess.run([sys.executable,str(root/'evidence/pr23-verification-driver.py'),phase,attempt,kind],cwd=root)
 print('PR23_GATE_FINISH '+phase+' '+str(result.returncode),flush=True)
 if result.returncode:sys.exit(result.returncode)
