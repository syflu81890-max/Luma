import sys,tempfile,unittest,json,sqlite3,subprocess
from pathlib import Path
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from store import Store,now
from service import Library
from profile_info import inspect_profile,snapshot_library

class ProfileRecoveryTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_inspection_is_read_only_and_includes_old_task_states(self):
        profile=self.root/'profile';store=Store(profile/'library')
        for n,state in enumerate(['queued','queued','paused','completed']):store.write('INSERT INTO tasks(id,url,status,created) VALUES(?,?,?,?)',(str(n),'https://x.com/example/media',state,now()))
        store.db.close();db=profile/'library/library.db';before=db.read_bytes();result=inspect_profile(profile)
        self.assertEqual(result['tasks'],4);self.assertEqual(result['statuses']['queued'],2);self.assertEqual(db.read_bytes(),before)
    def test_restart_keeps_queue_and_manual_pause_while_pausing_only_interrupted_running(self):
        store=Store(self.root/'library')
        for n,state in enumerate(['queued','queued','paused','running','cancelled']):store.write('INSERT INTO tasks(id,url,status,created,message) VALUES(?,?,?,?,?)',(str(n),'https://x.com/example/media',state,now(),'manual' if state=='paused' else ''))
        store.db.close();lib=Library(self.root/'library')
        try:
            states={r['id']:r['status'] for r in lib.query('SELECT id,status FROM tasks')};self.assertEqual(states,{'0':'queued','1':'queued','2':'paused','3':'paused','4':'cancelled'});self.assertFalse(lib.session_ready)
        finally:lib.call('shutdown',{});lib.analyzer.thread.join();lib.db.close()
    def test_recovers_only_queue_entries_auto_paused_by_030(self):
        store=Store(self.root/'library');created=now()
        for ident in ['queued-before','manually-paused','manually-changed']:
            store.write('INSERT INTO tasks(id,url,status,created,updated,mode) VALUES(?,?,?,?,?,?)',(ident,'https://x.com/example/media','queued',created,created,'latest'))
        backup=store.root/'backups/before-v3-test.db'
        with closing(sqlite3.connect(backup)) as dst:store.db.backup(dst)
        store.write("UPDATE tasks SET status='paused',message='上次运行中断；已保存的图片保留，可继续'")
        store.write("UPDATE tasks SET message='已手动暂停' WHERE id='manually-paused'");store.write("UPDATE tasks SET updated='changed' WHERE id='manually-changed'");store.write("DELETE FROM settings WHERE key='queueRecoveryVersion'");store.db.close()
        lib=Library(self.root/'library')
        try:self.assertEqual({r['id']:r['status'] for r in lib.query('SELECT id,status FROM tasks')},{'queued-before':'queued','manually-paused':'paused','manually-changed':'paused'})
        finally:lib.call('shutdown',{});lib.analyzer.thread.join();lib.db.close()
    def test_offline_location_is_not_replaced_and_fresh_flag_is_consumed(self):
        profile=self.root/'profile';profile.mkdir();location=self.root/'offline';(profile/'library-location.json').write_text(json.dumps({'path':str(location)}))
        request=json.dumps({'id':1,'method':'stats','args':{}})+'\n'
        command=[sys.executable,str(Path(__file__).resolve().parents[1]/'backend/app.py'),'--root',str(profile)]
        r=subprocess.run(command,input=request,capture_output=True,text=True,encoding='utf-8',timeout=20);result=json.loads(r.stdout.splitlines()[0])['result'];self.assertTrue(result['offline']);self.assertFalse(location.exists())
        (profile/'library-location.json').write_text(json.dumps({'path':str(location),'createIfMissing':True}));r=subprocess.run(command,input=request,capture_output=True,text=True,encoding='utf-8',timeout=20);self.assertEqual(r.returncode,0,r.stderr);self.assertTrue((location/'library.db').exists());self.assertNotIn('createIfMissing',json.loads((profile/'library-location.json').read_text()))
    def test_default_library_snapshot_keeps_source_and_queue(self):
        store=Store(self.root/'old');store.write('INSERT INTO tasks(id,status,created) VALUES(?,?,?)',('keep','queued',now()));store.db.close();before=(self.root/'old/library.db').read_bytes();snapshot_library(self.root/'old',self.root/'copy')
        self.assertEqual((self.root/'old/library.db').read_bytes(),before)
        with closing(sqlite3.connect(self.root/'copy/library.db')) as db:self.assertEqual(db.execute('SELECT status FROM tasks').fetchone()[0],'queued')

if __name__=='__main__':unittest.main()
