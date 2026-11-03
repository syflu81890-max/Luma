import sys,tempfile,unittest,json,sqlite3,shutil,subprocess,io
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'collector'))
from store import Store,normalize,now
from service import Library,next_run
from worker import ScanState
from media_utils import ffmpeg_path
from PIL import Image,ImageDraw

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root/'library');self.photo=self.root/'sample.jpg';Image.new('RGB',(120,200),(92,110,87)).save(self.photo)
    def tearDown(self):self.store.db.close();self.tmp.cleanup()
    def ingest(self,post=1,author='author_a',path=None,task=''):
        return self.store.ingest([path or self.photo],f'https://x.com/{author}/status/{post}',{'tweet_id':post,'num':1,'date':'2026-11-01T12:00:00+00:00','content':'original post','author':{'name':author,'id':111 if author=='author_a' else 222,'nick':'Display '+author}},task)
    def one(self):return self.store.list_photos({})['items'][0]
    def task(self):
        ident='task1';self.store.write('INSERT INTO tasks(id,url,limit_count,status,created,mode) VALUES(?,?,?,?,?,?)',(ident,'https://x.com/author_a/media',100,'queued',now(),'latest'));return ident
    def test_content_dedup_keeps_all_accounts_posts_and_note(self):
        self.assertEqual(self.ingest()['added'],1);p=self.one();self.store.edit({'ids':[p['id']],'note':'my private note','tags':'travel'})
        self.assertEqual(self.ingest(2,'author_b')['duplicates'],1);detail=self.store.detail(p['id']);self.assertEqual(len(detail['sources']),2);self.assertEqual(detail['note'],'my private note')
        self.assertEqual(self.store.list_photos({'account':'x:222'})['total'],1)
        self.assertEqual(detail['sources'][0]['content'],'original post')
    def test_category_and_rating_must_match_same_account(self):
        self.ingest();self.ingest(2,'author_b');self.store.save_account(dict(id='x:111',rating=1,categories='shoes'));self.store.save_account(dict(id='x:222',rating=5,categories='food'))
        self.assertEqual(self.store.list_photos({'accountCategory':'shoes','accountRating':'5'})['total'],0)
        self.assertEqual(self.store.list_photos({'accountCategory':'shoes','accountRating':'1'})['total'],1)
        self.assertEqual(self.store.accounts({'rating':'4+'})['items'][0]['handle'],'author_b')
    def test_deletion_survives_purge_and_new_account_repost(self):
        self.ingest();ident=self.one()['id'];self.store.edit({'ids':[ident],'trash':1});self.store.purge([ident])
        self.assertEqual(self.ingest(3,'author_b')['excluded'],1);self.assertEqual(self.store.stats()['total'],0)
        self.assertTrue(self.store.query('SELECT 1 FROM excluded_media WHERE media_key=?',('3:1',)))
        self.assertFalse((self.store.root/'originals'/(ident+'.jpg')).exists())
    def test_restore_and_undo_keep_private_information(self):
        self.ingest();ident=self.one()['id'];self.store.edit({'ids':[ident],'note':'keep'});self.store.edit({'ids':[ident],'trash':1});self.store.undo()
        self.assertEqual(self.one()['note'],'keep');self.assertEqual(self.store.query('SELECT * FROM excluded_content'),[])
    def test_batch_tags_append_remove_replace(self):
        self.ingest();ident=self.one()['id'];self.store.edit({'ids':[ident],'tags':'a,b'});self.store.edit({'ids':[ident],'tags':'b,c','tagMode':'add'});self.assertEqual(self.one()['tags'],'a,b,c');self.store.edit({'ids':[ident],'tags':'b','tagMode':'remove'});self.assertEqual(self.one()['tags'],'a,c')
    def test_crash_between_photo_and_batch_record_is_recoverable(self):
        task=self.task()
        with patch.object(self.store,'record_item',side_effect=RuntimeError('simulated crash')):
            with self.assertRaises(RuntimeError):self.ingest(task=task)
        self.assertEqual(self.store.stats()['total'],1);self.assertEqual(self.store.query('SELECT outcome FROM task_items')[0]['outcome'],'pending_new')
        self.ingest(task=task);self.assertEqual(self.store.query('SELECT imported FROM tasks')[0]['imported'],1)
        with self.store.transaction() as db:self.store.record_item(task,'1:1',self.one()['id'],'duplicate',db)
        self.assertEqual(self.store.query('SELECT imported FROM tasks')[0]['imported'],1)
        self.ingest(task=task);self.assertEqual(self.store.query('SELECT imported FROM tasks')[0]['imported'],1)
    def test_snapshot_preserves_notes_exclusions_and_relative_paths(self):
        self.ingest();ident=self.one()['id'];self.store.edit({'ids':[ident],'note':'private','trash':1});self.store.snapshot(self.root/'backup');restored=Store(self.root/'backup')
        try:self.assertEqual(restored.detail(ident)['note'],'private');self.assertEqual(restored.ingest([self.photo])['excluded'],1);self.assertTrue(restored.file_paths([ident]))
        finally:restored.db.close()
    def test_rename_uses_stable_account_id(self):
        old=self.store.ensure_account('before',{'id':123,'nick':'Name'});self.store.save_account(dict(id=old,rating=5,note='keep'));new=self.store.ensure_account('after',{'id':123,'nick':'Name'})
        self.assertEqual(old,new);self.assertEqual(self.store.account_detail(new)['rating'],5)
    def test_pagination_and_page_independent_selection(self):
        for n in range(125):self.store.write('INSERT INTO photos(id,path,created,kind,tags) VALUES(?,?,?,?,?)',(f'{n:064x}','dummy',f'2026-11-01T00:00:{n:03}', 'image','test'))
        data=self.store.list_photos({'page':2,'limit':60});self.assertEqual(len(data['items']),60);self.assertEqual(data['pages'],3);self.assertEqual(len(self.store.select_ids({})),125)
        statements=[];self.store.db.set_trace_callback(statements.append);self.store.list_photos({'limit':60});self.store.db.set_trace_callback(None);self.assertEqual(len(statements),2)
    def test_album_remove_does_not_delete_original(self):
        self.ingest();ident=self.one()['id'];album=self.store.album({'name':'reference'});self.store.album({'action':'add','album':album,'ids':[ident]});self.assertEqual(self.store.list_photos({'album':album})['total'],1);self.store.album({'action':'remove','album':album,'ids':[ident]});self.assertEqual(self.store.stats()['total'],1)
    def test_video_and_gif_have_separate_types(self):
        video=self.root/'test.mp4';subprocess.run([ffmpeg_path(),'-v','error','-f','lavfi','-i','color=c=blue:s=160x120:d=1','-r','6','-c:v','mpeg4','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True,timeout=30)
        a=Image.new('RGB',(80,60),'red');b=Image.new('RGB',(80,60),'blue');gif=self.root/'test.gif';a.save(gif,save_all=True,append_images=[b],duration=100,loop=0)
        self.assertEqual(self.store.ingest([video,gif])['added'],2);self.assertEqual(self.store.list_photos({'kind':'video'})['total'],1);self.assertEqual(self.store.list_photos({'kind':'gif'})['total'],1)
        row=self.store.list_photos({'kind':'video'})['items'][0];self.assertGreater(row['duration'],.5);self.assertTrue(self.store.image(row['id']).startswith('data:image/jpeg'))
    def test_original_export_is_byte_identical(self):
        self.ingest();p=self.one();result=self.store.export({'ids':[p['id']],'path':str(self.root)});out=Path(result['path']);self.assertEqual((out/(p['id']+'.jpg')).read_bytes(),self.photo.read_bytes());self.assertIn('original post',(out/'metadata.json').read_text())
    def test_bad_input_and_corrupt_media(self):
        self.assertEqual(normalize('@hello'),'https://x.com/hello/media')
        for value in ['https://x.com.evil.test/a','file:///tmp/a','https://x.com@evil.test/a','--help','https://x.com/home']:
            with self.assertRaises(ValueError):normalize(value)
        self.photo.write_bytes(b'bad');self.assertEqual(self.store.ingest([self.photo])['failed'],1)

class MigrationTests(unittest.TestCase):
    def test_real_v01_schema_migrates_without_losing_old_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'originals').mkdir();p=root/'originals'/'old.jpg';Image.new('RGB',(50,60),'red').save(p)
            with sqlite3.connect(root/'library.db') as db:
                db.executescript("CREATE TABLE photos(id TEXT PRIMARY KEY,path TEXT,width INT,height INT,size INT,created TEXT,tags TEXT DEFAULT '',favorite INT DEFAULT 0,trash INT DEFAULT 0,note TEXT DEFAULT '',color TEXT,author TEXT DEFAULT '');CREATE TABLE sources(photo TEXT,url TEXT,metadata TEXT,UNIQUE(photo,url));CREATE TABLE tasks(id TEXT PRIMARY KEY,url TEXT,limit_count INT,status TEXT,created TEXT,message TEXT DEFAULT '',imported INT DEFAULT 0);")
                db.execute('INSERT INTO photos VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',('legacy',str(p),50,60,p.stat().st_size,now(),'tag',1,0,'private','#ff0000','old_user'));db.execute('INSERT INTO sources VALUES(?,?,?)',('legacy','https://x.com/old_user/status/1',json.dumps({'tweet_id':1,'content':'old text','author':{'name':'old_user','id':77}})));db.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)',('oldtask','https://x.com/old_user',100,'completed',now(),'done',9))
            db.close();store=Store(root)
            try:
                self.assertEqual(store.detail('legacy')['note'],'private');self.assertEqual(store.detail('legacy')['sources'][0]['content'],'old text');self.assertEqual(store.query('SELECT imported,mode FROM tasks')[0],{'imported':9,'mode':'legacy'});self.assertTrue(list((root/'backups').glob('before-v2-*.db')));self.assertEqual(store.file_paths(['legacy']),[str(p)])
            finally:store.db.close()

class ScanTests(unittest.TestCase):
    def payload(self,**kw):return dict(limit=2,mode='latest',watermark='100',known=['105:1'],options={},**kw)
    def meta(self,n,**kw):return dict(tweet_id=n,num=1,extension='jpg',**kw)
    def test_known_items_do_not_consume_new_download_limit(self):
        s=ScanState(self.payload());self.assertEqual(s.decide('',self.meta(105)),'known');self.assertEqual(s.decide('',self.meta(104)),'download');self.assertEqual(s.decide('',self.meta(103)),'download');self.assertEqual(s.decide('',self.meta(102)),'stop');self.assertTrue(s.capped)
    def test_older_item_does_not_immediately_stop_new_scan(self):
        s=ScanState(self.payload());self.assertEqual(s.decide('',self.meta(5)),'old');self.assertEqual(s.decide('',self.meta(106)),'download');self.assertFalse(s.boundary)
    def test_boundary_and_retweet_ids(self):
        s=ScanState(self.payload());self.assertEqual(s.decide('',self.meta(5,retweet_id=110)),'download')
        for n in range(90,80,-1):value=s.decide('',self.meta(n))
        self.assertEqual(value,'stop');self.assertTrue(s.boundary)

class SchedulerTests(unittest.TestCase):
    def test_timezone_and_coalescing_and_manual_pause(self):
        self.assertEqual(next_run({'enabled':True,'type':'daily','time':'09:00','offset':480},datetime(2026,11,1,2,tzinfo=timezone.utc)),'2026-11-02T01:00:00+00:00')
        with tempfile.TemporaryDirectory() as tmp:
            lib=Library(tmp)
            try:
                aid=lib.ensure_account('scheduled');lib.schedule({'id':aid,'rule':{'enabled':True,'type':'interval','hours':6,'limit':10}});lib.write('UPDATE accounts SET next_run=? WHERE id=?',('2026-01-01',aid));self.assertEqual(len(lib.schedule_tick({})),1);self.assertEqual(lib.schedule_tick({}),[])
                task=lib.query('SELECT * FROM tasks')[0];lib.task_action({'id':task['id'],'action':'pause'});lib.write('UPDATE accounts SET next_run=? WHERE id=?',('2026-01-01',aid));self.assertEqual(lib.schedule_tick({}),[])
            finally:lib.call('shutdown',{});lib.analyzer.thread.join();lib.db.close()

if __name__=='__main__':unittest.main()
