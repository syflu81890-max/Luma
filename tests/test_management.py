import sys,tempfile,unittest,json,sqlite3
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'collector'))
from service import Library
from store import now
from worker import ScanState

class ManagementTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.lib=Library(self.tmp.name)
    def tearDown(self):self.lib.call('shutdown',{});self.lib.analyzer.thread.join();self.lib.db.close();self.tmp.cleanup()
    def add(self,name='sample',**kw):return self.lib.add_task(dict(url='@'+name,**kw))['id']
    def complete(self,ident):self.lib.write("UPDATE tasks SET status='completed',updated=? WHERE id=?",(now(),ident))
    def test_account_paging_filters_and_ids_match(self):
        for n in range(125):
            aid=self.lib.ensure_account(f'user_{n:03}');self.lib.save_account(dict(id=aid,rating=5 if n%2 else 1,categories='shoes' if n%3 else 'food'))
        data=self.lib.call('accounts',dict(page=2,limit=100,sort='name',direction='asc'))
        self.assertEqual(len(data['items']),25);self.assertEqual(data['pages'],2);self.assertEqual(data['items'][0]['handle'],'user_100')
        filters=dict(category='shoes',rating='4+',sort='rating');rows=self.lib.call('accounts',filters)
        self.assertEqual(rows['total'],len(self.lib.call('accountIds',filters)));self.assertTrue(all(r['rating']==5 and r['categories']=='shoes' for r in rows['items']))
        first=rows['items'][0];self.assertEqual(first['images'],0);self.assertEqual(first['videos'],0);self.assertEqual(first['gifs'],0)
    def test_task_history_pagination_and_hiding_keeps_relations(self):
        for n in range(225):
            self.lib.write('INSERT INTO tasks(id,url,status,created,mode,limit_count) VALUES(?,?,?,?,?,?)',(f'{n:05}','https://x.com/sample/media','completed' if n%2 else 'failed',f'2026-11-01T00:{n:04}','latest',0))
        data=self.lib.call('taskPage',dict(status='all',page=2,limit=100));self.assertEqual(len(data['items']),100);self.assertEqual(data['pages'],3)
        failed=self.lib.call('taskPage',dict(status='failed'));self.assertEqual(failed['total'],113)
        done=self.lib.call('taskIds',dict(status='completed'));self.assertEqual(len(done),112)
        result=self.lib.call('taskBatch',dict(action='hide',ids=[done[0],'00000']));self.assertEqual((result['succeeded'],result['skipped']),(1,1));self.assertEqual(len(self.lib.query('SELECT * FROM tasks')),225)
        self.assertEqual(self.lib.call('taskPage',dict(status='all'))['total'],224)
    def test_unlimited_default_finite_preserved_and_preview_paged(self):
        a=self.add();b=self.add('finite',limit=50)
        self.assertEqual(self.lib.query('SELECT limit_count FROM tasks WHERE id=?',(a,))[0]['limit_count'],0);self.assertEqual(self.lib.query('SELECT limit_count FROM tasks WHERE id=?',(b,))[0]['limit_count'],50)
        for n in range(251):self.lib.write('INSERT INTO candidates VALUES(?,?,?,?)',(a,str(n),'https://pbs.twimg.com/test','{}'))
        self.assertEqual(len(self.lib.call('candidatePage',dict(id=a,page=2))['items']),100);self.assertEqual(len(self.lib.call('candidateIds',dict(id=a))),251)
        s=ScanState(dict(limit=0,mode='history'))
        for n in range(15000):self.assertEqual(s.decide('',dict(tweet_id=n+1,num=1,extension='jpg')),'download')
        self.assertFalse(s.capped)
    def test_worker_detects_repeated_results_and_date_boundary(self):
        s=ScanState({});m=dict(tweet_id=1,num=1,extension='jpg');s.decide('',m)
        with self.assertRaisesRegex(RuntimeError,'游标'):
            for n in range(100):s.decide('',m)
        s=ScanState(dict(mode='history',options={'from':'2026-11-01'}))
        for n in range(10):r=s.decide('',dict(tweet_id=n+1,num=1,extension='jpg',date='2026-10-01'))
        self.assertEqual(r,'stop');self.assertTrue(s.boundary);self.assertFalse(s.capped)
    def test_batch_rating_categories_schedules_and_merge(self):
        ids=[self.lib.ensure_account(name) for name in ['one','two']]
        self.lib.call('accountBatch',dict(ids=ids,action='rating',rating=4));self.lib.call('accountBatch',dict(ids=ids,action='categories',categories='shoes,photo'))
        self.lib.call('accountBatch',dict(ids=ids,action='categories',categories='shoes',tagMode='remove'))
        self.assertTrue(all(r['categories']=='photo' and r['rating']==4 for r in self.lib.call('accounts',{})['items']))
        r=self.lib.call('accountBatch',dict(ids=ids,action='collect'));self.assertEqual(r['succeeded'],2)
        r=self.lib.call('accountBatch',dict(ids=ids,action='collect'));self.assertEqual(r['skipped'],2)
        self.lib.call('accountBatch',dict(ids=ids,action='pause'));self.assertTrue(all(t['status']=='paused' for t in self.lib.query('SELECT status FROM tasks')))
        self.lib.call('accountBatch',dict(ids=ids,action='scheduleToggle',enabled=True));self.assertTrue(all(json.loads(r['schedule'])['enabled'] for r in self.lib.call('accounts',{})['items']))
    def test_completion_requires_work_and_holds_future_schedule(self):
        with self.assertRaises(ValueError):self.lib.completion(dict(action='arm'))
        t=self.add();self.lib.completion(dict(action='arm'));aid=self.lib.ensure_account('future');self.lib.schedule(dict(id=aid,rule={'enabled':True,'hours':1,'onOpen':True}))
        self.assertEqual(self.lib.schedule_tick({}),[])
        second=self.add('second');s=self.lib.completion({});self.assertEqual(s['total'],2);self.assertFalse(s['ready'])
        self.complete(t);self.complete(second);self.assertTrue(self.lib.completion({})['ready'])
        self.lib.completion(dict(action='cancel'));self.assertEqual(len(self.lib.schedule_tick({})),1)
    def test_completion_paused_failed_preview_and_mutations(self):
        t=self.add();self.lib.completion(dict(action='arm'));self.lib.task_action(dict(id=t,action='pause'));self.assertTrue(self.lib.completion({})['reason'])
        self.lib.completion(dict(action='cancel'));self.lib.task_action(dict(id=t,action='resume'));self.lib.completion(dict(action='arm'));self.lib.write("UPDATE tasks SET status='failed' WHERE id=?",(t,));self.assertTrue(self.lib.completion({})['reason'])
        self.lib.completion(dict(action='cancel'));self.lib.task_action(dict(id=t,action='resume'));self.lib.completion(dict(action='arm'));self.lib.write("UPDATE tasks SET status='completed',mode='preview' WHERE id=?",(t,));self.assertIn('预览',self.lib.completion({})['reason'])
    def test_prepare_waits_for_writes_and_analysis_then_freezes(self):
        t=self.add();self.lib.completion(dict(action='arm'));self.complete(t);self.lib.busy_operations=1;self.assertFalse(self.lib.completion({})['ready']);self.lib.busy_operations=0
        self.lib.analyzer.paused=False;self.lib.analyzer.busy=True
        self.assertFalse(self.lib.completion(dict(action='prepare'))['ready']);self.assertTrue(self.lib.completion_frozen)
        with self.assertRaises(ValueError):self.lib.call('saveSettings',{'test':1})
        self.lib.analyzer.busy=False;self.assertTrue(self.lib.completion(dict(action='prepare'))['ready']);self.lib.completion(dict(action='cancel'));self.assertFalse(self.lib.maintenance);self.assertFalse(self.lib.analyzer.paused)
    def test_disk_reserve_stops_task_creation(self):
        with patch('service.shutil.disk_usage',return_value=type('Disk',(),{'free':1000})()):
            with self.assertRaisesRegex(ValueError,'空间不足'):self.add()
        self.assertEqual(self.lib.query('SELECT id FROM tasks'),[])
    def test_v2_migration_keeps_limit_and_backups(self):
        self.add(limit=88);self.lib.db.execute('PRAGMA user_version=2');self.lib.db.commit()
        other=Library(self.tmp.name)
        try:
            self.assertEqual(other.query('SELECT limit_count FROM tasks')[0]['limit_count'],88);self.assertTrue(list((Path(self.tmp.name)/'backups').glob('before-v3-*.db')))
        finally:other.call('shutdown',{});other.analyzer.thread.join();other.db.close()
    def test_power_adapter_is_not_forcing_and_is_mocked(self):
        import win_power
        with patch.object(win_power.subprocess,'run') as run:
            win_power.execute('shutdown');args=run.call_args.args[0];self.assertEqual(args[-3:],['/s','/t','0']);self.assertNotIn('/f',args)
        with patch.object(win_power,'sleep_windows') as sleep:win_power.execute('sleep');sleep.assert_called_once()

if __name__=='__main__':unittest.main()
