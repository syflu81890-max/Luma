"""Exercise the distributable Python host against temporary images only."""
import json,subprocess,tempfile,time,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from PIL import Image

def main():
    exe=Path(__file__).resolve().parents[1]/'backend-dist'/'luma-backend'/'luma-backend.exe'
    with tempfile.TemporaryDirectory(prefix='luma-frozen-assistant-') as temporary:
        root=Path(temporary);source=root/'source.jpg';output=root/'output.png';Image.new('RGB',(120,180),'red').save(source);Image.new('RGB',(240,360),'blue').save(output)
        process=subprocess.Popen([str(exe),'--root',str(root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));serial=0
        def call(method,**a):
            nonlocal serial
            serial+=1;process.stdin.write(json.dumps(dict(id=serial,method=method,args=a))+'\n');process.stdin.flush();line=process.stdout.readline()
            if not line:raise RuntimeError('Frozen host exited: '+process.stderr.read())
            reply=json.loads(line)
            if reply.get('error'):raise RuntimeError(reply['error'])
            return reply['result']
        try:
            assert call('import',paths=[str(source)])['added']==1
            ident=call('list')['items'][0]['id'];plan=call('assistantPlan',ids=[ident],action='tags',value='鞋子');call('assistantApply',id=plan['id']);assert '鞋子' in call('detail',id=ident)['tags'];call('assistantUndo',id=plan['id'])
            job=call('assistantEditPrepare',ids=[ident],prompt='test handoff');result=call('assistantEditCommit',id=job['id'],index=0,path=str(output));assert call('detail',id=result['photo'])['parent']==ident;assert call('stats')['total']==2
            account=call('addAccount',value='@sample');call('saveAccount',id=account,categories='测试合集',rating=5);assert call('accounts')['items'][0]['rating']==5;assert call('collections')[0]['name']=='测试合集';assert call('dashboard')['accounts']['total']==1;assert call('accountHealthStatus')['status']=='idle'
            call('saveView',name='本地视图',query=dict(filters=dict(kind='image')));assert len(call('savedViews'))==1
            class DenyProxy(BaseHTTPRequestHandler):
                requests=0
                def do_CONNECT(self):type(self).requests+=1;self.send_error(403,'Synthetic offline test proxy')
                def log_message(self,*args):pass
            proxy=ThreadingHTTPServer(('127.0.0.1',0),DenyProxy);threading.Thread(target=proxy.serve_forever,daemon=True).start()
            try:
                call('saveSettings',proxy='http://127.0.0.1:'+str(proxy.server_port));state=call('followingStart',owner='fixture',cookies=dict(auth_token='synthetic-fixture'));assert state['id'];deadline=time.monotonic()+25
                while state['status']=='running' and time.monotonic()<deadline:time.sleep(.2);state=call('followingStatus')
                assert state['status']=='interrupted',state
                assert DenyProxy.requests>0,('Collector did not reach the local deny proxy',state)
                assert 'No module named' not in state.get('message',''),state
            finally:proxy.shutdown();proxy.server_close()
            call('shutdown');process.stdin.close();assert process.wait(timeout=30)==0;print('FROZEN_ASSISTANT_OK: import, plan, undo, edit version, saved views and real following subprocess lifecycle through local deny proxy')
        finally:
            if process.poll() is None:process.terminate();process.wait(timeout=10)
            for stream in (process.stdin,process.stdout,process.stderr):
                if stream and not stream.closed:stream.close()

if __name__=='__main__':main()
