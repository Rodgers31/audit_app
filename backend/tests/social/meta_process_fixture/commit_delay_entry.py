"""Lost-completion fixture: product main commits/emits, then owned exit is delayed."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from graph_entry import main
if __name__=='__main__':
    result=main()
    # No product function patched; parent must still wait for positive exit.
    time.sleep(5)
    raise SystemExit(result)
