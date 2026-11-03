import runpy,sys,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
runpy.run_path(str(Path(__file__).with_name('seed_fixture.py')),run_name='__main__')
from store import Store
root=Path(sys.argv[1]);store=Store(root/'library')
for n in range(225):
    aid=store.ensure_account(f'source_{n:03}');store.save_account(dict(id=aid,alias=f'素材账号 {n:03}',rating=n%6,categories='穿搭,鞋子' if n%2 else '摄影',note='此行为独立测试数据，支持账号备注预览。'))
    if n%3==0:store.write('UPDATE accounts SET schedule=?,next_run=? WHERE id=?',(json.dumps(dict(enabled=True,hours=6,limit=0,onOpen=False)),'2099-01-01T00:00:00+00:00',aid))
    status=['completed','failed','paused','needs_login'][n%4]
    store.write('INSERT INTO tasks(id,url,account,status,created,updated,mode,limit_count,imported,scanned,message) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(f'fixture_{n:03}',f'https://x.com/source_{n:03}/media',aid,status,(datetime(2026,11,1,tzinfo=timezone.utc)+timedelta(minutes=n)).isoformat(),(datetime(2026,11,1,tzinfo=timezone.utc)+timedelta(minutes=n)).isoformat(),'latest',0,n%18,n+20,'测试任务详情：已有内容保留；该测试不会连接 X。'))
store.db.close()
