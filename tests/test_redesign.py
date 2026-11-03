import io,json,random,sqlite3,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'collector'))
from service import Library
from account_health import user_state

class RedesignTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.lib=Library(self.root/'library')
    def tearDown(self):self.lib.call('shutdown',{});self.lib.analyzer.thread.join();self.lib.db.close();self.tmp.cleanup()
    def pattern(self,file,w=600,h=800):
        im=Image.new('RGB',(600,800),'#173a66');draw=ImageDraw.Draw(im);rng=random.Random(24)
        for n in range(80):
            x,y=rng.randrange(570),rng.randrange(770);draw.ellipse((x,y,x+30+rng.randrange(60),y+30+rng.randrange(60)),fill=tuple(rng.randrange(256) for _ in range(3)))
        im.resize((w,h)).save(file);return file
    def photo(self,file,post=1,author='sample',published='2026-11-01T10:00:00+00:00'):
        self.lib.ingest([file],f'https://x.com/{author}/status/{post}',dict(tweet_id=post,date=published,author={'name':author,'id':123},content='post'))
        return self.lib.query('SELECT photo FROM media WHERE media_key=?',(str(post)+':1',))[0]['photo']
    def scan(self):
        self.lib.call('similarScan',{});deadline=time.monotonic()+8
        while self.lib.similar_status()['status']=='running' and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(self.lib.similar_status()['status'],'completed');return self.lib.call('similarPage',{})
    def test_collections_roundtrip_rename_memberships_and_legacy_filters(self):
        aid=self.lib.ensure_account('sample');self.lib.save_account(dict(id=aid,categories='穿搭,鞋子',rating=4,note='keep'))
        collections=self.lib.collections();shoes=next(c for c in collections if c['name']=='鞋子');self.assertEqual(self.lib.account_rows(dict(collection=shoes['id']))['total'],1)
        self.lib.collection_action(dict(action='rename',id=shoes['id'],name='鞋履灵感'));self.assertEqual(self.lib.account_rows(dict(category='鞋履灵感'))['total'],1);self.assertEqual(self.lib.account_detail(aid)['rating'],4)
        self.lib.collection_action(dict(action='remove',id=shoes['id'],ids=[aid]));self.assertEqual(self.lib.account_detail(aid)['categories'],'穿搭');self.assertEqual(self.lib.account_detail(aid)['note'],'keep')
    def test_only_explicit_suspension_is_a_ban(self):
        for raw in [{},{'errors':[{'code':88}]},{'__typename':'UserUnavailable','message':'Not found'},{'__typename':'UserUnavailable','reason':'Protected'}]:self.assertNotEqual(user_state(raw)['state'],'suspended')
        self.assertEqual(user_state({'__typename':'UserUnavailable','reason':'Suspended','message':'User is suspended.'})['state'],'suspended');self.assertEqual(user_state({'__typename':'User','rest_id':'1'})['state'],'active')
    def test_suspended_pool_collection_guard_scheduler_and_recovery(self):
        task=self.lib.add_task(dict(url='@banned',limit=125));aid=self.lib.query('SELECT account FROM tasks WHERE id=?',(task['id'],))[0]['account'];self.lib.schedule(dict(id=aid,rule=dict(enabled=True,onOpen=True,hours=1)))
        self.lib.set_account_health(aid,dict(state='suspended',reason='explicit'));self.assertEqual(self.lib.account_rows({})['total'],0);self.assertEqual(self.lib.account_rows(dict(pool='suspended'))['total'],1);self.assertEqual(self.lib.query('SELECT status FROM tasks')[0]['status'],'blocked_account')
        with self.assertRaisesRegex(ValueError,'封禁池'):self.lib.add_task(dict(url='@banned'))
        self.assertEqual(self.lib.schedule_tick({}),[]);self.lib.set_account_health(aid,dict(state='unknown',reason='network'));self.assertEqual(self.lib.account_rows(dict(pool='suspended'))['total'],1)
        self.lib.set_account_health(aid,dict(state='active',reason='restored'));self.assertEqual(self.lib.account_rows({})['total'],1);self.assertEqual(self.lib.query('SELECT status,limit_count FROM tasks')[0],dict(status='paused',limit_count=125))
    def test_health_requires_login_no_unintentional_detection(self):
        with self.assertRaisesRegex(ValueError,'登录'):self.lib.start_health_check({})
        self.assertEqual(self.lib.health_status()['status'],'idle')
    def test_background_probe_restores_pool_without_resuming_blocked_task(self):
        task=self.lib.add_task(dict(url='@recover'));aid=self.lib.query('SELECT account FROM tasks WHERE id=?',(task['id'],))[0]['account'];self.lib.set_account_health(aid,dict(state='suspended'))
        fake=type('Probe',(),{'communicate':lambda s,*a,**kw:(json.dumps(dict(state='active',reason='confirmed')), ''),'poll':lambda s:0})()
        with patch('organization.subprocess.Popen',return_value=fake):
            self.lib.call('accountHealthCheck',dict(ids=[aid],cookies={'auth_token':'fixture'}));deadline=time.monotonic()+5
            while self.lib.health_status()['status']=='running' and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(self.lib.health_status()['restored'],1);self.assertEqual(self.lib.health_status()['status'],'completed');self.assertEqual(self.lib.account_rows({})['total'],1);self.assertEqual(self.lib.query('SELECT status FROM tasks')[0]['status'],'paused');self.assertEqual(self.lib.busy_operations,0)
    def test_identity_and_avatar_content_history_preserved(self):
        with patch.object(self.lib,'request_avatar'):aid=self.lib.ensure_account('before',dict(id=124,nick='旧名字',profile_image='https://pbs.twimg.com/old.jpg'))
        self.lib.save_account(dict(id=aid,rating=5,note='private'))
        image=Image.new('RGB',(80,80),'red');out=io.BytesIO();image.save(out,format='PNG');response=type('Response',(),{'content':out.getvalue(),'raise_for_status':lambda s:None})()
        with patch('requests.get',return_value=response):self.lib.fetch_avatar(aid)
        old=self.lib.account_detail(aid)['avatar_path'];before=(self.lib.root/old).read_bytes()
        with patch.object(self.lib,'request_avatar'):self.assertEqual(self.lib.ensure_account('after',dict(id=124,nick='新名字',profile_image='https://pbs.twimg.com/new.jpg')),aid)
        image=Image.new('RGB',(80,80),'blue');out=io.BytesIO();image.save(out,format='PNG');response.content=out.getvalue()
        with patch('requests.get',return_value=response):self.lib.fetch_avatar(aid)
        records=self.lib.account_history(dict(id=aid));self.assertIn('before',[r['handle'] for r in records]);self.assertIn('after',[r['handle'] for r in records]);self.assertTrue(any(r['avatar_path']==old for r in records));self.assertEqual((self.lib.root/old).read_bytes(),before);self.assertEqual(self.lib.account_detail(aid)['rating'],5)
    def test_latest_publication_sort_and_large_page(self):
        a=self.photo(self.pattern(self.root/'a.png'),1,published='2026-11-02T10:00:00+00:00');b=self.photo(self.pattern(self.root/'b.png',300,400),2,published='2026-10-01T10:00:00+00:00')
        self.lib.write("UPDATE photos SET created='2026-12-01' WHERE id=?",(b,));self.assertEqual(self.lib.list_photos(dict(sort='published'))['items'][0]['id'],a)
        for n in range(245):self.lib.write('INSERT INTO photos(id,path,created,kind) VALUES(?,?,?,?)',(f'{n:064x}','dummy','2026-01-01','image'))
        self.assertEqual(len(self.lib.list_photos(dict(limit=240))['items']),240)
    def test_verified_similar_keep_resolution_protect_favorites_undo(self):
        high=self.photo(self.pattern(self.root/'high.png'),1);low=self.photo(self.pattern(self.root/'low.jpg',300,400),2);self.lib.edit(dict(ids=[low],favorite=1));report=self.scan();self.assertEqual(len(report['items']),1);self.assertEqual(report['items'][0]['keep'],high)
        with self.assertRaisesRegex(ValueError,'收藏'):self.lib.similar_plan({})
        plan=self.lib.similar_plan(dict(protectFavorites=False));self.assertEqual(plan['remove'],[low]);self.lib.assistant_apply(dict(id=plan['id']));self.assertEqual(self.lib.stats()['total'],1);self.assertTrue(self.lib.file_paths([low]));self.lib.assistant_undo(dict(id=plan['id']));self.assertEqual(self.lib.stats()['total'],2)
    def test_similar_protects_ai_variants_flat_images_and_changed_originals(self):
        high=self.photo(self.pattern(self.root/'high.png'),1);low=self.photo(self.pattern(self.root/'low.jpg',300,400),2)
        self.lib.write('UPDATE photos SET parent=? WHERE id=?',(high,low));self.assertEqual(self.scan()['total'],0);self.lib.write("UPDATE photos SET parent='' WHERE id=?",(low,));self.assertEqual(self.scan()['total'],1)
        file=Path(self.lib.file_paths([low])[0]);file.write_bytes(file.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'发生变化'):self.lib.similar_plan({})
    def test_dashboard_and_bulk_latest_skip_suspended_and_existing_queue(self):
        one=self.lib.ensure_account('normal');banned=self.lib.ensure_account('banned');self.lib.set_account_health(banned,dict(state='suspended'));self.lib.add_task(dict(url='@normal',limit=52));r=self.lib.collect_all({});self.assertEqual((r['succeeded'],r['skipped']),(0,1));d=self.lib.dashboard();self.assertEqual(d['accounts']['suspended'],1);self.assertEqual(d['tasks']['queued'],1);self.assertEqual(self.lib.query('SELECT limit_count FROM tasks')[0]['limit_count'],52)
    def test_incremental_account_counts_follow_trash_restore_purge_and_multi_source(self):
        photo=self.photo(self.pattern(self.root/'photo.png'),1);account=self.lib.query('SELECT account FROM account_photos')[0]['account']
        def counts():return self.lib.account_rows({})['items'][0]
        self.assertEqual((counts()['retained'],counts()['images']),(1,1));self.lib.edit(dict(ids=[photo],trash=1));self.assertEqual((counts()['retained'],counts()['deleted']),(0,1));self.lib.undo();self.assertEqual(counts()['retained'],1)
        self.lib.edit(dict(ids=[photo],trash=1));self.lib.purge([photo]);self.assertEqual((counts()['retained'],counts()['deleted'],counts()['storage']),(0,1,0))
    def test_v3_upgrade_keeps_queue_notes_rating_and_builds_collections(self):
        aid=self.lib.ensure_account('old');self.lib.write('UPDATE accounts SET categories=?,note=?,rating=? WHERE id=?',('旧合集','keep',5,aid));task=self.lib.add_task(dict(url='@old',limit=77));self.lib.db.execute('PRAGMA user_version=3');self.lib.db.commit();other=Library(self.lib.root)
        try:
            self.assertEqual(other.account_detail(aid)['note'],'keep');self.assertEqual(other.collections()[0]['name'],'旧合集');self.assertEqual(other.query('SELECT limit_count,status FROM tasks WHERE id=?',(task['id'],))[0],dict(limit_count=77,status='queued'));self.assertTrue(list((self.lib.root/'backups').glob('before-v4-*.db')))
        finally:other.call('shutdown',{});other.analyzer.thread.join();other.db.close()

if __name__=='__main__':unittest.main()
