import runpy,sys,random
from pathlib import Path
from PIL import Image,ImageDraw
runpy.run_path(str(Path(__file__).with_name('seed_management.py')),run_name='__main__')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from store import Store
root=Path(sys.argv[1]);store=Store(root/'library');aid=store.query("SELECT id FROM accounts WHERE handle='source_000'")[0]['id'];store.set_account_health(aid,dict(state='suspended',reason='隔离测试中的明确封禁'))
im=Image.new('RGB',(600,800),'#173a66');draw=ImageDraw.Draw(im);rng=random.Random(24)
for n in range(80):
    x,y=rng.randrange(570),rng.randrange(770);draw.ellipse((x,y,x+30+rng.randrange(60),y+30+rng.randrange(60)),fill=tuple(rng.randrange(256) for _ in range(3)))
for post,dimensions,ext,published in [(200,(600,800),'png','2026-11-03T10:00:00+00:00'),(201,(300,400),'jpg','2025-11-01T10:00:00+00:00')]:
    file=root/f'near-{post}.{ext}';im.resize(dimensions).save(file);store.ingest([file],f'https://x.com/studio_one/status/{post}',dict(tweet_id=post,num=1,date=published,content='相似图与发布日期测试',author={'name':'studio_one','id':1001,'nick':'素材观察室'}))
store.db.close()
