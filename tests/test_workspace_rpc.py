import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path

class WorkspaceRpcTests(unittest.TestCase):
    def test_switch_rejects_active_work_and_preserves_independent_library_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);profile=root/'profile';other=root/'other';serial=0
            command=[os.environ['LUMA_TEST_BACKEND'],'--root',str(profile)] if os.environ.get('LUMA_TEST_BACKEND') else [sys.executable,str(Path(__file__).resolve().parents[1]/'backend/app.py'),'--root',str(profile)]
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            def call(method,args=None,expect_error=False):
                nonlocal serial
                serial+=1;process.stdin.write(json.dumps(dict(id=serial,method=method,args=args or {}))+'\n');process.stdin.flush();line=process.stdout.readline();self.assertTrue(line,'backend stopped unexpectedly');result=json.loads(line)
                if expect_error:self.assertIn('error',result);return result['error']
                self.assertNotIn('error',result,result.get('error'));return result['result']
            try:
                aid=call('addAccount',dict(value='@first'));call('saveAccount',dict(id=aid,note='第一资料库备注',rating=5));call('saveView',dict(name='第一视图',query=dict(filters=dict(kind='image'))));task=call('addTask',dict(url='@first',limit=123))
                self.assertIn('暂停',call('switchLibrary',dict(path=str(other),mode='new'),True));self.assertFalse((other/'library.db').exists())
                call('taskAction',dict(id=task['id'],action='pause'));call('switchLibrary',dict(path=str(other),mode='new'));self.assertEqual(call('accounts')['total'],0);self.assertEqual(call('savedViews'),[])
                second=call('addAccount',dict(value='@second'));call('saveAccount',dict(id=second,note='第二资料库备注'));call('switchLibrary',dict(path=str(profile/'library'),mode='switch'))
                self.assertEqual(call('accounts')['total'],1);self.assertEqual(call('account',dict(id=aid))['note'],'第一资料库备注');self.assertEqual(call('savedViews')[0]['name'],'第一视图');self.assertEqual(call('tasks')[0]['limit_count'],123);self.assertEqual(call('tasks')[0]['status'],'paused')
                capture=call('browserPrepare',dict(id=task['id']));self.assertIn('补采',call('switchLibrary',dict(path=str(other),mode='switch'),True));call('browserFinish',dict(id=capture['id']));call('switchLibrary',dict(path=str(other),mode='switch'));self.assertEqual(call('account',dict(id=second))['note'],'第二资料库备注')
            finally:
                call('shutdown');process.stdin.close();process.wait(timeout=15);process.stdout.close();process.stderr.close()

if __name__=='__main__':unittest.main()
