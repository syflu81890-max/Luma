"""Real frozen collector and engine, using a loopback image fixture only."""
import io,json,os,subprocess,tempfile,threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from PIL import Image

root=Path(__file__).resolve().parents[1];buffer=io.BytesIO();Image.new('RGB',(80,120),'#7464aa').save(buffer,format='PNG');data=buffer.getvalue()
class Images(BaseHTTPRequestHandler):
    requests=0
    def do_GET(self):
        type(self).requests+=1;self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass

server=ThreadingHTTPServer(('127.0.0.1',0),Images);threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    with tempfile.TemporaryDirectory(prefix='luma-frozen-collector-') as temporary:
        entries=[dict(url=f'http://127.0.0.1:{server.server_port}/{n}.png',metadata=dict(tweet_id=n,num=1,extension='png',content='Synthetic post text',date='2026-11-04T12:00:00+00:00')) for n in (1,2,3)]
        payload=dict(url='https://x.com/fixture/media',stage=temporary,cookies={},known=['1:1'],excluded=['2:1'],selected=entries,mode='selected',options=dict(kinds=['image']),ffmpeg=str(root/'vendor/ffmpeg/ffmpeg.exe'))
        env={**os.environ,'LUMA_ENGINE_CACHE':os.environ.get('LUMA_ENGINE_CACHE') or str(root/'.tools/public-engine-fresh3')}
        result=subprocess.run([str(root/'collector-dist/luma-collector/luma-collector.exe'),'--download'],input=json.dumps(payload),capture_output=True,text=True,encoding='utf-8',env=env,timeout=120)
        events=[json.loads(line) for line in result.stdout.splitlines()];finished=events[-1]
        assert result.returncode==0 and finished['type']=='finished' and finished['code']==0,(result.stdout,result.stderr)
        assert Images.requests==1,Images.requests
        assert {item['decision'] for item in events if item['type']=='item'}=={'known','excluded','download'}
        output=list(Path(temporary).glob('*.png'));assert len(output)==1 and output[0].read_bytes()==data
        assert json.loads(Path(str(output[0])+'.json').read_text(encoding='utf-8'))['content']=='Synthetic post text'
        print('FROZEN_COLLECTOR_OK: independent engine loads, loopback download, known/deleted skips and original post metadata')
finally:server.shutdown();server.server_close()
