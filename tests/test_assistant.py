import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from service import Library

class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.lib=Library(self.root/'library');self.source=self.root/'person.jpg';Image.new('RGB',(200,300),'red').save(self.source)
        self.lib.ingest([self.source],'https://x.com/example/status/123',{'tweet_id':123,'content':'original tweet','author':{'name':'example','id':1}});self.ident=self.lib.list_photos({})['items'][0]['id']
    def tearDown(self):
        self.lib.call('shutdown',{});self.lib.analyzer.thread.join();self.lib.db.close();self.tmp.cleanup()
    def call(self,method,**a):return self.lib.call(method,a)
    def test_plan_preview_stale_rejection_idempotency_undo(self):
        plan=self.call('assistantPlan',ids=[self.ident],action='tags',value='鞋子, 灵感');self.assertEqual(self.lib.detail(self.ident)['tags'],'竖图')
        self.call('assistantApply',id=plan['id']);self.assertIn('鞋子',self.lib.detail(self.ident)['tags']);self.assertTrue(self.call('assistantApply',id=plan['id'])['alreadyApplied'])
        self.call('assistantUndo',id=plan['id']);self.assertEqual(self.lib.detail(self.ident)['tags'],'竖图');self.assertEqual(self.call('assistantUndo',id=plan['id'])['status'],'undone')
        plan=self.call('assistantPlan',ids=[self.ident],action='trash');self.lib.edit({'ids':[self.ident],'note':'changed'})
        with self.assertRaisesRegex(ValueError,'变化'):self.call('assistantApply',id=plan['id'])
        self.assertEqual(self.lib.stats()['total'],1)
    def test_trash_retains_original_and_exclusions_restore(self):
        plan=self.call('assistantPlan',filters={},action='trash');self.call('assistantApply',id=plan['id']);self.assertEqual(self.lib.stats()['trash'],1);self.assertTrue(self.lib.file_paths([self.ident]));self.assertTrue(self.lib.query('SELECT * FROM excluded_content'))
        plan=self.call('assistantPlan',ids=[self.ident],action='restore');self.call('assistantApply',id=plan['id']);self.assertEqual(self.lib.stats()['total'],1);self.assertEqual(self.lib.query('SELECT * FROM excluded_content'),[])
    def test_explicit_selection_and_invalid_record_ids(self):
        with self.assertRaises(ValueError):self.call('assistantPlan',action='trash')
        with self.assertRaises(ValueError):self.call('assistantPlan',ids=[self.ident],action='purge')
        with self.assertRaises(ValueError):self.call('assistantPlanInfo',id='../library.db')
        self.lib.completion_frozen=True
        with self.assertRaises(ValueError):self.call('assistantPlan',ids=[self.ident],action='trash')
        self.lib.completion_frozen=False
    def test_undo_cannot_revert_someone_elses_latest_edit(self):
        plan=self.call('assistantPlan',ids=[self.ident],action='tags',value='test');self.call('assistantApply',id=plan['id']);self.lib.edit({'ids':[self.ident],'note':'new note'})
        with self.assertRaisesRegex(ValueError,'其他编辑'):self.call('assistantUndo',id=plan['id'])
        self.assertEqual(self.lib.detail(self.ident)['note'],'new note')
    def test_folder_read_only_and_content_dedup(self):
        folder=self.root/'folder';folder.mkdir();(folder/'same.jpg').write_bytes(self.source.read_bytes());(folder/'bad.png').write_text('invalid')
        page=self.call('assistantFolder',path=str(folder));self.assertEqual(len(page['items']),2);self.assertTrue(page['readOnly']);self.assertEqual(self.lib.stats()['total'],1);self.assertEqual(next(i for i in page['items'] if i.get('sha256'))['library']['id'],self.ident)
    def test_edit_handoff_original_hash_metadata_and_retry(self):
        self.lib.edit({'ids':[self.ident],'note':'private note','tags':'鞋子'});album=self.lib.album({'name':'我的素材'});self.lib.album({'action':'add','album':album,'ids':[self.ident]})
        before=Path(self.lib.file_paths([self.ident])[0]).read_bytes();tasks=self.lib.query('SELECT * FROM tasks');job=self.call('assistantEditPrepare',ids=[self.ident],references=[str(self.source)],prompt='把人物替换成参考人物，保留鞋子和场景')
        self.assertEqual(self.lib.query('SELECT * FROM tasks'),tasks);snapshot=Path(job['items'][0]['input']);self.assertEqual(snapshot.read_bytes(),before);self.assertNotEqual(snapshot.stat().st_ino,Path(self.lib.file_paths([self.ident])[0]).stat().st_ino)
        output=self.root/'generated.png';Image.new('RGB',(400,600),'blue').save(output)
        result=self.call('assistantEditCommit',id=job['id'],index=0,path=str(output));self.assertEqual(result['parent'],self.ident);self.assertTrue(result['originalPreserved']);self.assertEqual(Path(self.lib.file_paths([self.ident])[0]).read_bytes(),before);self.assertEqual(self.lib.detail(self.ident)['note'],'private note')
        modified=self.lib.detail(result['photo']);self.assertEqual(modified['parent'],self.ident);self.assertIn('AI修改',modified['tags']);self.assertEqual(modified['sources'][0]['content'],'original tweet');self.assertEqual(modified['albums'][0]['id'],album);self.assertTrue(self.lib.query('SELECT * FROM account_photos WHERE photo=?',(result['photo'],)))
        self.assertTrue(self.call('assistantEditCommit',id=job['id'],index=0,path=str(output))['alreadyApplied']);self.assertEqual(self.lib.stats()['total'],2);self.assertEqual(self.call('assistantJob',id=job['id'])['status'],'completed')
    def test_external_folder_edit_and_no_original_overwrite(self):
        external=self.root/'external.png';Image.new('RGB',(50,80),'green').save(external);before=external.read_bytes();job=self.call('assistantEditPrepare',paths=[str(external)],prompt='修改背景');output=self.root/'result.png';Image.new('RGB',(70,100),'yellow').save(output)
        result=self.call('assistantEditCommit',id=job['id'],index=0,path=str(output));self.assertEqual(external.read_bytes(),before);self.assertEqual(result['parent'],hashlib.sha256(before).hexdigest());self.assertEqual(self.lib.stats()['total'],3)
    def test_changed_input_and_existing_result_rejected(self):
        job=self.call('assistantEditPrepare',ids=[self.ident],prompt='修改');Image.new('RGB',(10,20),'black').save(job['items'][0]['input'])
        with self.assertRaisesRegex(ValueError,'副本'):self.call('assistantEditCommit',id=job['id'],index=0,path=str(self.source))
        job=self.call('assistantEditPrepare',ids=[self.ident],prompt='修改')
        with self.assertRaisesRegex(ValueError,'完全相同'):self.call('assistantEditCommit',id=job['id'],index=0,path=str(self.source))
    def test_edit_job_survives_library_copy_and_reference_paths_are_remapped(self):
        job=self.call('assistantEditPrepare',ids=[self.ident],references=[str(self.source)],prompt='继续修改');newroot=self.root/'migrated';self.lib.snapshot(newroot);other=Library(newroot)
        try:
            recovered=other.call('assistantJob',{'id':job['id']});self.assertTrue(Path(recovered['items'][0]['input']).is_relative_to(newroot));self.assertTrue(Path(recovered['references'][0]).is_file())
            self.assertEqual(Path(recovered['items'][0]['input']).read_bytes(),self.source.read_bytes())
        finally:other.call('shutdown',{});other.analyzer.thread.join();other.db.close()
    def test_similar_read_only_and_different_sources_exactly_deduped(self):
        self.lib.ingest([self.source],'https://x.com/another/status/234',{'tweet_id':234,'author':{'name':'another','id':2}});self.assertEqual(self.lib.stats()['total'],1);report=self.call('assistantDuplicates');self.assertEqual(report['total'],0);self.assertIn('硬链接',report['exactDuplicates'])

if __name__=='__main__':unittest.main()
