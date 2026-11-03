import io,json,sqlite3,sys,tempfile,time,threading,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from service import Library
from store import now
from browser_media import extract_candidates,safe_media_url
from collection_results import classify_failure,describe_zero

def tweet(handle='private_ref',post='100',kind='photo'):
    media=dict(type=kind,media_url_https='https://pbs.twimg.com/media/example.jpg',video_info=dict(variants=[dict(content_type='video/mp4',bitrate=100,url='https://video.twimg.com/low.mp4'),dict(content_type='video/mp4',bitrate=900,url='https://video.twimg.com/high.mp4')]))
    return dict(__typename='Tweet',rest_id=post,core=dict(user_results=dict(result=dict(rest_id='99',core=dict(screen_name=handle,name='示例私密账号'),privacy=dict(protected=True)))),legacy=dict(full_text='这是一条带图推文',created_at='Tue Nov 03 10:00:00 +0000 2026',extended_entities=dict(media=[media])))

class UpgradeTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.lib=Library(self.root/'library')
    def tearDown(self):self.lib.call('shutdown',{});self.lib.analyzer.thread.join();self.lib.db.close();self.temp.cleanup()
    def run_row(self,owner='self',status='completed'):
        ident='read-'+owner;self.lib.write('INSERT INTO following_runs(id,owner,created,updated,status) VALUES(?,?,?,?,?)',(ident,owner,now(),now(),status));return ident
    def following_user(self,run,uid,handle,private=0):self.lib.write('INSERT INTO following_users VALUES(?,?,?,?,?,?)',(run,uid,handle,'昵称 '+handle,'',private))
    def photo(self):
        file=self.root/'sample.png';Image.new('RGB',(64,96),'blue').save(file);self.lib.ingest([file]);return self.lib.query('SELECT id FROM photos')[0]['id']
    def test_saved_dynamic_view_roundtrip_excludes_ephemeral_selection(self):
        self.lib.call('saveView',dict(name='穿搭近期',query=dict(filters=dict(accountCategory='穿搭',accountRating='4+',kind='image',ids=['temporary'],sort='published'),semantic=True,text='餐桌吃饭')))
        view=self.lib.call('savedViews',{})[0];self.assertNotIn('ids',view['query']['filters']);self.assertEqual(view['query']['text'],'餐桌吃饭');self.assertTrue(view['query']['semantic'])
        self.lib.call('deleteView',dict(id=view['id']));self.assertEqual(self.lib.saved_views(),[])
    def test_following_import_stable_identity_preserves_notes_and_merges_active_tasks(self):
        aid=self.lib.ensure_account('old_handle',dict(id='99',nick='旧昵称'));self.lib.save_account(dict(id=aid,alias='我的备注名',note='保留',rating=5,categories='穿搭'))
        run=self.run_row();self.following_user(run,'99','new_handle',1);self.following_user(run,'100','another')
        result=self.lib.call('followingImport',dict(id=run,all=True));self.assertEqual(result['succeeded'],2)
        updated=self.lib.account_detail(aid);self.assertEqual(updated['handle'],'new_handle');self.assertEqual(updated['note'],'保留');self.assertEqual(updated['alias'],'我的备注名');self.assertEqual(updated['rating'],5);self.assertEqual(updated['protected'],1)
        again=self.lib.call('followingImport',dict(id=run,all=True));self.assertEqual(again['skipped'],2);self.assertEqual(len(self.lib.query('SELECT id FROM tasks')),2)
    def test_following_pagination_new_filter_banned_skip_and_search_scope(self):
        run=self.run_row();aid=self.lib.ensure_account('banned',dict(id='7'));self.lib.set_account_health(aid,dict(state='suspended'))
        self.following_user(run,'7','banned');self.following_user(run,'8','fresh');self.following_user(run,'9','other')
        self.assertEqual(self.lib.following_page(dict(id=run))['total'],3);self.assertEqual(self.lib.following_page(dict(id=run,onlyNew=True))['total'],2)
        result=self.lib.import_following(dict(id=run,all=True,q='fresh'));self.assertEqual(result['succeeded'],1);self.assertEqual(self.lib.query('SELECT url FROM tasks')[0]['url'],'https://x.com/fresh/media')
        result=self.lib.import_following(dict(id=run,all=True));self.assertEqual(result['skipped'],2);self.assertFalse(result['errors'])
    def test_following_requires_login_and_never_interprets_following_as_media_task(self):
        with self.assertRaisesRegex(ValueError,'登录'):self.lib.start_following(dict(owner='self'))
        self.assertEqual(self.lib.query('SELECT COUNT(*) n FROM tasks')[0]['n'],0)
    def test_private_page_parser_preserves_post_and_selects_best_mp4(self):
        a=tweet();b=tweet(post='101',kind='animated_gif');items=list(extract_candidates(dict(data=[a,a,b]),'private_ref'))
        self.assertEqual(len(items),2);byid={i['key']:i for i in items};self.assertIn('name=orig',byid['100:1']['url']);self.assertEqual(byid['100:1']['metadata']['content'],'这是一条带图推文');self.assertEqual(byid['100:1']['metadata']['date'],'2026-11-03T10:00:00+00:00');self.assertEqual(byid['101:1']['url'],'https://video.twimg.com/high.mp4');self.assertEqual(byid['101:1']['metadata']['type'],'animated_gif')
        self.assertEqual(list(extract_candidates(a,'someone_else')),[])
    def test_page_parser_ignores_unavailable_and_untrusted_urls(self):
        self.assertFalse(safe_media_url('http://pbs.twimg.com/a.jpg'));self.assertFalse(safe_media_url('https://pbs.twimg.com:invalid/a'));self.assertFalse(safe_media_url('https://pbs.twimg.com.attacker.test/a'));self.assertFalse(safe_media_url('https://u:p@pbs.twimg.com/a'))
        a=tweet();a['legacy']['extended_entities']['media'][0]['media_url_https']='https://elsewhere.test/image.jpg';self.assertEqual(list(extract_candidates([a,dict(legacy='malformed')],'')),[])
    def test_browser_capture_is_paused_holds_switch_barrier_and_does_not_advance_boundary(self):
        task=self.lib.add_task(dict(url='@private_ref'));self.lib.task_action(dict(id=task['id'],action='pause'));aid=self.lib.query('SELECT account FROM tasks')[0]['account'];self.lib.write("UPDATE accounts SET watermark='50' WHERE id=?",(aid,))
        capture=self.lib.call('browserPrepare',dict(id=task['id']));self.assertEqual(self.lib.busy_operations,1);self.assertEqual(self.lib.query('SELECT status FROM tasks WHERE id=?',(capture['id'],))[0]['status'],'paused')
        result=self.lib.call('browserCandidates',dict(id=capture['id'],owner='private_ref',data=tweet()));self.assertEqual(result['total'],1)
        with self.assertRaisesRegex(ValueError,'仍在补采'):self.lib.add_task(dict(url='@private_ref',mode='selected',selected=[dict(task=capture['id'],key='100:1')]))
        self.lib.call('browserFinish',dict(id=capture['id']));self.assertEqual(self.lib.busy_operations,0);self.assertEqual(self.lib.account_detail(aid)['watermark'],'50');self.assertEqual(self.lib.query('SELECT status FROM tasks WHERE id=?',(capture['id'],))[0]['status'],'completed')
        self.lib.call('browserFinish',dict(id=capture['id']));self.assertEqual(self.lib.busy_operations,0)
    def test_empty_browser_capture_is_explained_and_not_reported_as_success(self):
        source=self.lib.add_task(dict(url='@sample'));self.lib.task_action(dict(id=source['id'],action='pause'));capture=self.lib.call('browserPrepare',dict(id=source['id']));self.lib.call('browserFinish',dict(id=capture['id']))
        row=self.lib.query('SELECT status,reason_code,message FROM tasks WHERE id=?',(capture['id'],))[0];self.assertEqual(row['status'],'partial');self.assertEqual(row['reason_code'],'browser_empty');self.assertIn('未返回',row['message']);self.assertEqual(self.lib.busy_operations,0)
    def test_browser_finish_is_idempotent_under_concurrent_close_events(self):
        source=self.lib.add_task(dict(url='@sample'));self.lib.task_action(dict(id=source['id'],action='pause'));capture=self.lib.call('browserPrepare',dict(id=source['id']))
        threads=[threading.Thread(target=lambda:self.lib.call('browserFinish',dict(id=capture['id']))) for _ in range(8)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(self.lib.busy_operations,0);self.assertIsNone(self.lib.browser_capture)
    def test_following_cancel_during_process_launch_stops_and_releases_barrier(self):
        entered=threading.Event();release=threading.Event()
        class Process:
            def __init__(self):self.stdin=io.StringIO();self.stdout=io.StringIO();self.stopped=False
            def terminate(self):self.stopped=True
            def poll(self):return 0 if self.stopped else None
            def wait(self,**kwargs):return 0
        child=Process()
        def launch(*a,**kw):entered.set();release.wait(timeout=4);return child
        with patch('catalog.subprocess.Popen',side_effect=launch):
            self.lib.call('followingStart',dict(owner='self',cookies={'auth_token':'fixture'}));self.assertTrue(entered.wait(timeout=3));self.lib.call('followingCancel',{});release.set();deadline=time.monotonic()+3
            while self.lib.following_job_running and time.monotonic()<deadline:time.sleep(.02)
        self.assertTrue(child.stopped);self.assertFalse(self.lib.following_job_running);self.assertEqual(self.lib.busy_operations,0);self.assertEqual(self.lib.following_status()['status'],'interrupted')
    def test_access_login_rate_limit_and_empty_reasons_are_distinct(self):
        for message,expected in [("AuthorizationError: x's Tweets are protected",'needs_access'),('HTTP 401 Could not authenticate you','needs_login'),('HTTP 403 Forbidden','needs_access'),('429 rate limit','waiting')]:self.assertEqual(classify_failure(message)[0],expected)
        self.assertIn('删除',describe_zero(dict(excluded=3)));self.assertIn('已经存在',describe_zero(dict(known=2)));self.assertIn('日期',describe_zero(dict(filter=8)))
    def test_empty_engine_response_cannot_skip_unfinished_range(self):
        task=self.lib.add_task(dict(url='@private_ref'));row=self.lib.query('SELECT * FROM tasks WHERE id=?',(task['id'],))[0];self.lib.write("UPDATE accounts SET watermark='50',pending_top='100' WHERE id=?",(row['account'],))
        events=[dict(type='account_state',state='active',reason='valid'),dict(type='finished',code=0,top='0',capped=False,boundary=False)]
        class Process:
            def __init__(self):self.stdin=io.BytesIO();self.stdout=io.BytesIO(('\n'.join(json.dumps(e) for e in events)+'\n').encode())
            def poll(self):return 0
            def wait(self,**kwargs):return 0
        with patch('service.subprocess.Popen',return_value=Process()):self.lib.run_task(row)
        result=self.lib.query('SELECT status,reason_code FROM tasks WHERE id=?',(task['id'],))[0];self.assertEqual(result,dict(status='partial',reason_code='empty_pending'));self.assertEqual(self.lib.account_detail(row['account'])['watermark'],'50');self.assertEqual(self.lib.account_detail(row['account'])['last_success'],'')
    def test_account_and_album_batch_undo_use_one_history(self):
        aid=self.lib.ensure_account('sample');self.lib.call('accountBatch',dict(ids=[aid],action='rating',rating=5));self.lib.call('undo',{});self.assertEqual(self.lib.account_detail(aid)['rating'],0)
        photo=self.photo();album=self.lib.album(dict(name='参考'));self.lib.album(dict(action='add',album=album,ids=[photo]));self.lib.undo();self.assertEqual(self.lib.query('SELECT * FROM album_photos'),[]);self.assertEqual(self.lib.stats()['total'],1)
    def test_account_publication_order_uses_its_own_post_when_shared_elsewhere(self):
        old=self.root/'old.png';recent=self.root/'recent.png';Image.new('RGB',(50,60),'red').save(old);Image.new('RGB',(50,60),'green').save(recent)
        def ingest(file,author,post,published):self.lib.ingest([file],f'https://x.com/{author}/status/{post}',dict(tweet_id=post,date=published,author=dict(name=author)))
        ingest(old,'first',1,'2020-01-01T00:00:00+00:00');ingest(recent,'first',2,'2024-01-01T00:00:00+00:00');ingest(old,'second',3,'2026-11-03T00:00:00+00:00')
        aid=self.lib.query("SELECT id FROM accounts WHERE handle='first'")[0]['id'];result=self.lib.list_photos(dict(account=aid,sort='published'))
        self.assertEqual([r['published'] for r in result['items']],['2024-01-01T00:00:00+00:00','2020-01-01T00:00:00+00:00'])
    def test_upgrade_backfills_dates_and_keeps_tasks_and_exclusions(self):
        aid=self.lib.ensure_account('sample');task=self.lib.add_task(dict(url='@sample',limit=77));self.lib.write("UPDATE tasks SET status='completed',updated='2026-11-03T01:00:00+00:00' WHERE id=?",(task['id'],));self.lib.db.execute('PRAGMA user_version=4');self.lib.db.commit()
        other=Library(self.lib.root)
        try:
            self.assertEqual(other.account_detail(aid)['last_success'],'2026-11-03T01:00:00+00:00');self.assertEqual(other.query('SELECT limit_count FROM tasks')[0]['limit_count'],77);self.assertTrue(list((self.lib.root/'backups').glob('before-v5-*.db')));self.assertEqual(other.query('PRAGMA user_version')[0]['user_version'],6)
        finally:other.call('shutdown',{});other.analyzer.thread.join();other.db.close()

if __name__=='__main__':unittest.main()
