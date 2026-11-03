"""Large synthetic-library handover benchmark. No real database or files used."""
import json,sys,tempfile,time
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'backend'))
from store import Store,now
from service import Library
from workspace_host import WorkspaceHost

with tempfile.TemporaryDirectory(prefix='luma-large-switch-') as temporary:
    profile=Path(temporary)/'profile';large=Path(temporary)/'large';small=Path(temporary)/'small'
    s=Store(large)
    with s.lock:
        s.db.executemany('INSERT INTO photos(id,path,width,height,size,created,author) VALUES(?,?,?,?,?,?,?)',[(f'sample-{i}',f'originals/fixture/{i}.jpg',1080,1440,200000,now(),f'fixture_{i%285}') for i in range(61000)])
        s.db.executemany('INSERT INTO tasks(id,url,status,created) VALUES(?,?,?,?)',[(f'task-{i}',f'https://x.com/fixture_{i}/media','paused',now()) for i in range(285)])
        s.db.commit()
    s.db.close();s=Store(small);s.db.close();profile.mkdir()
    (profile/'library-location.json').write_text(json.dumps(dict(path=str(small))),encoding='utf-8')
    host=WorkspaceHost(profile,lambda path:Library(path,defer_recovery=True));times=[]
    try:
        for target in (large,small,large,small,large,small):
            start=time.monotonic();host.call('switchLibrary',dict(path=str(target),mode='switch'));elapsed=round((time.monotonic()-start)*1000);times.append(elapsed)
            assert host.root==target.resolve()
            with host.library.lock:
                assert host.library.db.execute('SELECT COUNT(*) FROM photos').fetchone()[0]==(61000 if target==large else 0)
                assert host.library.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]==(285 if target==large else 0)
            assert elapsed<15000,'Synthetic handover exceeded bound'
        report=dict(ok=True,media=61000,tasks=285,synthetic=True,switchMs=times)
        (root/'output/large-switch-benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
    finally:
        WorkspaceHost.dispose(host.library,host.queue).join(30)
        for thread in host.retired:thread.join(30)
