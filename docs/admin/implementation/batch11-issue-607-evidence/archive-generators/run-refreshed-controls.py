import subprocess,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
for name in ['focused-green-rechecked','pending-original-green-rechecked']:
 command=[sys.executable,str(OUT/'record_v4.py'),name,'450',sys.executable,str(OUT/('run-'+name+'.py'))]
 print('START '+name,flush=True)
 rc=subprocess.call(command)
 print('END '+name+' '+str(rc),flush=True)
 if rc:sys.exit(rc)
