"""Benchmark a temporary database copy. The actual library is opened read-only."""
import json,sqlite3,sys,tempfile,time
from pathlib import Path
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from store import Store
from management import Management
class Bench(Management,Store):pass
if '--live-copy' not in sys.argv:raise SystemExit('Requires --live-copy; never initializes the actual library')
profile=Path.home()/'.luma-desktop'/'UserData';root=Path(json.loads((profile/'library-location.json').read_text(encoding='utf-8-sig'))['path'])
with tempfile.TemporaryDirectory(prefix='luma-account-bench-') as temporary:
    with closing(sqlite3.connect((root/'library.db').as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(Path(temporary)/'library.db')) as target:source.backup(target)
    started=time.perf_counter();bench=Bench(temporary);migration=round((time.perf_counter()-started)*1000,1);samples=[]
    try:
        for _ in range(3):
            started=time.perf_counter();data=bench.account_rows(dict(limit=64,sort='name',direction='asc'));samples.append(round((time.perf_counter()-started)*1000,1))
        rows=bench.query('SELECT COUNT(*) n FROM photos')[0]['n']
    finally:bench.db.close()
    report=dict(mediaRows=rows,accounts=data['total'],pageSize=len(data['items']),oneTimeMigrationMs=migration,queryMs=samples,actualLibraryReadOnly=True)
    Path(__file__).resolve().parents[1].joinpath('output/account-performance-0.5.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
