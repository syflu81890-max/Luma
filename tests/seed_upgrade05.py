import json,runpy,sys
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name('seed_redesign.py')),run_name='__main__')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from store import Store,now
root=Path(sys.argv[1]);s=Store(root/'library')
s.write("INSERT INTO following_runs(id,owner,created,updated,status,message) VALUES('fixture-following','my_account',?,?,'completed','关注列表读取完成（合成验证数据）')",(now(),now()))
for uid,handle,private in [('1001','studio_one',0),('9001','private_ref',1),('9002','new_source',0)]:s.write('INSERT INTO following_users VALUES(?,?,?,?,?,?)',('fixture-following',uid,handle,'示例 '+handle,'',private))
s.write("INSERT INTO tasks(id,url,account,mode,status,created,updated,options,reason_code,message,result_json) VALUES('private-task','https://x.com/private_ref/media',?,'latest','needs_access',?,?,'{}','access_denied','当前采集身份无权访问，请核对关注权限',?)",(s.ensure_account('private_ref'),now(),now(),json.dumps(dict(counts=dict(known=3,excluded=2,filter=1),complete=False))))
s.db.close()
