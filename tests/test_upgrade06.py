import io,json,random,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from service import Library
from workspace_host import WorkspaceHost

class Upgrade06Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.lib=Library(self.root/'library')
    def tearDown(self):
        self.lib.call('shutdown',{});self.lib.analyzer.thread.join(timeout=5)
        deadline=time.monotonic()+5
        while self.lib.busy_operations and time.monotonic()<deadline:time.sleep(.01)
        self.lib.avatar_pool.shutdown(wait=True,cancel_futures=True);self.lib.db.close();self.tmp.cleanup()
    def media(self,name='pattern.png',width=480,height=640,handle='one',post=1,language='ja'):
        image=Image.new('RGB',(480,640));draw=ImageDraw.Draw(image);rng=random.Random(61)
        for y in range(0,640,40):
            for x in range(0,480,40):draw.rectangle((x,y,x+40,y+40),fill=tuple(rng.randrange(40,230) for _ in range(3)))
        target=self.root/name;image.resize((width,height)).save(target)
        self.lib.ingest([target],f'https://x.com/{handle}/status/{post}',dict(tweet_id=post,num=1,lang=language,date='2026-11-01T11:30:00+00:00',author=dict(name=handle)))
        return self.lib.query('SELECT photo FROM media WHERE media_key=?',(f'{post}:1',))[0]['photo']
    def scan(self,**options):
        self.lib.start_similar_scan(options);deadline=time.monotonic()+10
        while self.lib.similar_status()['status']=='running' and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(self.lib.similar_status()['status'],'completed',self.lib.similar_status());return self.lib.similar_page({})
    def test_collections_order_notes_and_manual_region_survive_restart(self):
        account=self.lib.ensure_account('one');a=self.lib.collection_action(dict(action='create',name='Shoes'));b=self.lib.collection_action(dict(action='create',name='Food'))
        self.lib.collection_action(dict(action='reorder',ids=[b['id'],a['id']]))
        self.lib.save_account(dict(id=account,categories='Shoes,Food',alias='My alias',note='Daily references',country='GB'))
        self.lib.remember_note('Daily references');self.assertEqual(self.lib.note_presets()[0]['text'],'Daily references')
        self.assertEqual([c['name'] for c in self.lib.collections()],['Food','Shoes']);self.assertEqual(self.lib.account_detail(account)['country'],'GB')
        other=Library(self.lib.root)
        try:self.assertEqual([c['name'] for c in other.collections()],['Food','Shoes']);self.assertEqual(other.account_detail(account)['note'],'Daily references');self.assertTrue(other.note_presets())
        finally:other.call('shutdown',{});other.analyzer.thread.join();other.db.close()
    def test_language_is_only_a_region_suggestion_and_manual_choice_wins(self):
        self.media();account=self.lib.query("SELECT id FROM accounts WHERE handle='one'")[0]['id'];result=self.lib.infer_account_region(account)
        self.assertEqual(result['country'],'JP');self.lib.save_account(dict(id=account,country='CA'));self.lib.infer_account_region(account)
        row=self.lib.account_detail(account);self.assertEqual(row['country'],'CA');self.assertEqual(row['suggested_country'],'JP')
        self.lib.write('UPDATE sources SET metadata=?',(json.dumps(dict(tweet_id=1,lang='en')),));self.assertEqual(self.lib.infer_account_region(account)['country'],'')
    def test_new_account_collection_limit_does_not_damage_legacy_memberships(self):
        account=self.lib.ensure_account('one');self.lib.save_account(dict(id=account,categories='A,B,C'))
        with self.assertRaisesRegex(ValueError,'3'):self.lib.save_account(dict(id=account,categories='A,B,C,D'))
        self.lib.write('UPDATE accounts SET categories=? WHERE id=?',('A,B,C,D',account));self.lib.save_account(dict(id=account,categories='Renamed,B,C,D'));self.assertEqual(self.lib.account_detail(account)['categories'],'Renamed,B,C,D')
    def test_display_avatar_stays_pinned_while_latest_identity_is_recorded(self):
        account=self.lib.ensure_account('one');(self.lib.root/'avatars/first.jpg').write_bytes(b'first');(self.lib.root/'avatars/new.jpg').write_bytes(b'new')
        self.lib.save_account(dict(id=account,pinned_avatar='avatars/first.jpg',avatar_path='avatars/new.jpg'))
        result=self.lib.call('avatar',dict(id=account));self.assertIn('Zmlyc3Q=',result)
        self.lib.save_account(dict(id=account,custom_avatar='avatars/new.jpg'));self.assertIn('bmV3',self.lib.call('avatar',dict(id=account)))
    def test_account_remove_protects_shared_media_and_undo_restores_identity(self):
        shared=self.media();exclusive=self.media('different.png',width=240,height=320,post=2)
        self.lib._source(shared,'https://x.com/two/status/3',dict(tweet_id=3,num=1,author=dict(name='two')))
        account=self.lib.query("SELECT id FROM accounts WHERE handle='one'")[0]['id'];self.lib.save_account(dict(id=account,note='Private note',country='JP'));self.lib.add_task(dict(url='@one'))
        plan=self.lib.account_remove_plan(dict(id=account));self.assertEqual((plan['media'],plan['shared'],plan['exclusive']),(2,1,1))
        with self.assertRaisesRegex(ValueError,'账号名'):self.lib.remove_account(dict(id=account,confirmHandle='wrong'))
        self.lib.remove_account(dict(id=account,confirmHandle='one'));self.assertFalse(self.lib.query('SELECT 1 FROM accounts WHERE id=?',(account,)))
        self.assertEqual(self.lib.detail(shared)['trash'],0);self.assertEqual(self.lib.detail(exclusive)['trash'],1);self.assertTrue(self.lib.file_paths([shared,exclusive]));self.assertTrue(self.lib.query('SELECT 1 FROM excluded_content WHERE photo=?',(exclusive,)))
        self.lib.undo();self.assertEqual(self.lib.account_detail(account)['note'],'Private note');self.assertEqual(self.lib.account_detail(account)['country'],'JP');self.assertEqual(self.lib.detail(exclusive)['trash'],0);self.assertEqual(self.lib.account_detail(account)['tasks'][0]['status'],'paused')
    def test_similar_scan_reuses_completed_work_after_restart_and_scans_only_new(self):
        self.media();self.media('low.jpg',width=240,height=320,post=2);first=self.scan();self.assertEqual(first['total'],1)
        with patch('similarity_cache.Image.open',side_effect=AssertionError('previous images must not be reopened')):self.scan()
        self.assertEqual(self.lib.similar_status()['total'],0)
        other=Library(self.lib.root)
        try:
            self.assertEqual(other.similar_page({})['total'],1)
            with patch('similarity_cache.Image.open',side_effect=AssertionError('restart must reuse results')):other.start_similar_scan({});deadline=time.monotonic()+5
            while other.similar_status()['status']=='running' and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(other.similar_status()['total'],0)
        finally:other.call('shutdown',{});other.analyzer.thread.join();other.db.close()
        self.media('new.jpg',width=360,height=480,post=4);self.scan();self.assertEqual(self.lib.similar_status()['total'],1);self.assertEqual(self.lib.similar_page({})['items'][0]['count'],3)
    def test_ignored_similar_groups_remain_ignored_until_new_members_arrive(self):
        self.media();self.media('low.jpg',width=240,height=320,post=2);group=self.scan()['items'][0]
        self.lib.ignore_similar(dict(groups=[group['id']]));self.assertEqual(self.lib.similar_page({})['total'],0);self.scan();self.assertEqual(self.lib.similar_page({})['total'],0)
        self.media('new.jpg',width=360,height=480,post=5);self.assertEqual(self.scan()['total'],1)

class HandoverTests(unittest.TestCase):
    def test_slow_candidate_can_be_observed_and_cancelled_without_changing_pointer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();entered=threading.Event();release=threading.Event();errors=[]
            def factory(path):
                if path==root/'slow':entered.set();release.wait(5)
                return Library(path,defer_recovery=True)
            host=WorkspaceHost(root/'profile',factory);old=host.library
            # Let deferred recovery settle before starting a switch.
            deadline=time.monotonic()+3
            while old.recovery_pending and time.monotonic()<deadline:time.sleep(.01)
            def switch():
                try:host.call('switchLibrary',dict(path=str(root/'slow'),mode='new'))
                except Exception as exc:errors.append(str(exc))
            worker=threading.Thread(target=switch);worker.start()
            try:
                self.assertTrue(entered.wait(3));start=time.monotonic();self.assertEqual(host.call('switchStatus')['phase'],'opening');self.assertLess(time.monotonic()-start,.1)
                with self.assertRaisesRegex(ValueError,'切换'):host.call('stats')
                host.call('cancelSwitch');release.set();worker.join(5);self.assertFalse(worker.is_alive());self.assertIn('取消',errors[0]);self.assertIs(host.library,old);self.assertEqual(host.call('stats')['total'],0);self.assertFalse(host.config.exists())
            finally:
                release.set();worker.join(5);WorkspaceHost.dispose(host.library,host.queue).join(5)
                for thread in host.retired:thread.join(5)
    def test_handover_waits_for_old_readers_before_closing_and_preserves_target_notes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();host=WorkspaceHost(root/'profile',lambda path:Library(path,defer_recovery=True));old=host.library;entered=threading.Event();release=threading.Event();original=old.call;errors=[]
            deadline=time.monotonic()+3
            while old.recovery_pending and time.monotonic()<deadline:time.sleep(.01)
            def slow(method,args):
                if method=='slowRead':entered.set();release.wait(5);return old.query('SELECT COUNT(*) n FROM accounts')[0]['n']
                return original(method,args)
            old.call=slow;reader=threading.Thread(target=lambda:host.call('slowRead'));reader.start();self.assertTrue(entered.wait(2))
            def switch():
                try:host.call('switchLibrary',dict(path=str(root/'other'),mode='new'))
                except Exception as exc:errors.append(str(exc))
            worker=threading.Thread(target=switch);worker.start()
            try:
                deadline=time.monotonic()+2
                while host.status()['phase']!='waiting' and time.monotonic()<deadline:time.sleep(.01)
                self.assertFalse(old.closed);release.set();reader.join(5);worker.join(5);self.assertFalse(errors);self.assertFalse(worker.is_alive());self.assertTrue(old.closed)
                self.assertEqual(Path(json.loads(host.config.read_text())['path']),root/'other');self.assertEqual(host.call('stats')['total'],0)
            finally:
                release.set();reader.join(5);worker.join(5);WorkspaceHost.dispose(host.library,host.queue).join(5)
                for thread in host.retired:thread.join(5)

if __name__=='__main__':unittest.main()
