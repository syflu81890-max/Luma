import sys,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from store import Store
from media_utils import ffmpeg_path
from PIL import Image,ImageDraw
import imageio_ffmpeg
root=Path(sys.argv[1]);store=Store(root/'library')
for n,color in enumerate(['#d9c6ae','#8c9c91','#c9cedd','#b6a4aa']):
    width,height=[(1080,1430),(1920,1080),(480,640),(480,640)][n]
    im=Image.new('RGB',(width,height),color);d=ImageDraw.Draw(im);d.rounded_rectangle((width*.13,height*.25,width*.87,height*.72),radius=40,fill='#f1eae0');d.ellipse((width*.36,height*.37,width*.64,height*.57),fill=color);p=root/f'fixture-{n}.png';im.save(p)
    store.ingest([p],f'https://x.com/studio_one/status/{100+n}',{'tweet_id':100+n,'num':1,'content':f'这是第 {n+1} 条示例推文，照片与来源分别保存。','date':'2026-11-02T08:00:00+00:00','author':{'name':'studio_one','id':1001,'nick':'素材观察室'}})
account=store.query('SELECT id FROM accounts')[0]['id'];store.save_account(dict(id=account,rating=4,categories='穿搭,摄影',note='账号备注与图片备注分开保存。'))
# H.264 matches common X MP4s; Chromium cannot play MPEG-4 Part 2. The
# development-only encoder generates synthetic test input, never product code.
video=root/'fixture-video.mp4';subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i','color=c=blue:s=320x180:d=2','-r','12','-c:v','libx264','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True,timeout=30);store.ingest([video]);store.album(dict(name='鞋子参考'));store.db.close()
