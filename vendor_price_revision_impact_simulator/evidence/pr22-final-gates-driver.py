"""Serial isolated verification gates; stop at the first real failure."""
import subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
root=Path(__file__).resolve().parents[1]
args=sys.argv[1:]
attempt=args.pop(0) if args and args[0].isdecimal() else '4'
for phase in args:
 print('PR22_GATE_START '+phase+' '+datetime.now(timezone.utc).isoformat(),flush=True)
 result=subprocess.run([sys.executable,str(root/'evidence/pr22-verification-driver.py'),phase,attempt],cwd=root)
 print('PR22_GATE_FINISH '+phase+' exit='+str(result.returncode),flush=True)
 if result.returncode:sys.exit(result.returncode)
