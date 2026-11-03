import sys,tempfile,unittest,os,hashlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from store import Store
from storage_layout import folder_name
from PIL import Image

class StorageLayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root/'library');self.file=self.root/'input.jpg';Image.new('RGB',(80,120),'navy').save(self.file)
    def tearDown(self):self.store.db.close();self.tmp.cleanup()
    def ingest(self,handle='one',post=1):
        self.store.ingest([self.file],f'https://x.com/{handle}/status/{post}',dict(tweet_id=post,num=1,author={'name':handle}));return self.store.query('SELECT * FROM photos')[0]['id']
    def locations(self,ident):return [self.store.path(r['path']) for r in self.store.query('SELECT path FROM media_locations WHERE photo=?',(ident,))]
    def test_multi_account_categories_share_one_file(self):
        first=self.store.ensure_account('one');self.store.save_account(dict(id=first,categories='穿搭,鞋子'));ident=self.ingest();self.ingest('two',2)
        locations=self.locations(ident);self.assertEqual(len(locations),3);self.assertEqual(len({(p.stat().st_dev,p.stat().st_ino) for p in locations}),1)
        self.assertTrue(all(p.is_file() for p in locations));self.assertTrue(any('/@one/穿搭/照片/' in p.as_posix() for p in locations));self.assertTrue(any('/@two/未分类/照片/' in p.as_posix() for p in locations));self.assertEqual(len(self.store.query('SELECT id FROM photos')),1)
        self.assertEqual(list((self.store.root/'originals').glob('*.jpg')),[])
    def test_category_change_removes_old_links_and_snapshot_preserves_links(self):
        ident=self.ingest();old=self.locations(ident)[0];aid=self.store.ensure_account('one');self.store.save_account(dict(id=aid,categories='A,B'));self.store.reconcile_layout(limit=None)
        self.assertFalse(old.exists());locations=self.locations(ident);self.assertEqual(len(locations),2);self.assertTrue(all(p.exists() for p in locations))
        result=self.store.snapshot(self.root/'backup');copy=Store(result['path'])
        try:
            paths=[copy.path(r['path']) for r in copy.query('SELECT path FROM media_locations WHERE photo=?',(ident,))];self.assertTrue(os.path.samefile(*paths));self.assertEqual(copy.file_paths([ident]),[str(copy.path(self.store.query('SELECT path FROM photos')[0]['path']))])
        finally:copy.db.close()
    def test_trash_restore_purge_remove_every_reference(self):
        ident=self.ingest();self.ingest('two',2);before=self.locations(ident);self.store.edit(dict(ids=[ident],trash=1));self.assertTrue(all('_回收站' in p.parts for p in self.locations(ident)));self.assertTrue(all(not p.exists() for p in before))
        self.store.undo();self.assertTrue(all('_回收站' not in p.parts for p in self.locations(ident)));self.store.edit(dict(ids=[ident],trash=1));self.store.purge([ident]);self.assertEqual(self.locations(ident),[]);self.assertEqual(list((self.store.root/'originals').rglob('*.jpg')),[]);self.assertEqual(self.store.ingest([self.file])['excluded'],1)
    def test_interrupted_relayout_recovers_without_losing_original(self):
        ident=self.ingest();old=self.store.file_paths([ident])[0];aid=self.store.ensure_account('one');self.store.save_account(dict(id=aid,categories='new'))
        with patch.object(self.store,'transaction',side_effect=RuntimeError('crash before database switch')):
            with self.assertRaises(RuntimeError):self.store.organize_photo(ident)
        self.assertTrue(Path(old).is_file());self.assertEqual(self.store.file_paths([ident]),[old]);self.store.reconcile_layout(limit=None);self.assertIn('/new/',self.store.file_paths([ident])[0].replace('\\','/'));self.assertFalse(Path(old).exists())
    def test_unsupported_hardlinks_preserve_primary_without_extra_copies(self):
        aid=self.store.ensure_account('one');self.store.save_account(dict(id=aid,categories='A,B'))
        with patch('storage_layout.os.link',side_effect=OSError('unsupported')):ident=self.ingest()
        self.assertEqual(len(self.locations(ident)),1);self.assertEqual(len(list((self.store.root/'originals').rglob('*.jpg'))),1);self.assertGreater(self.store.storage_status()['aliasWarnings'],0)
    def test_missing_primary_recovers_from_remaining_link(self):
        ident=self.ingest();self.ingest('two',2);primary=Path(self.store.file_paths([ident])[0]);primary.unlink();self.assertTrue(self.store.file_paths([ident]));self.store.reconcile_layout(limit=None);self.assertTrue(primary.exists());self.assertEqual(self.store.storage_status()['pending'],0)
    def test_folder_names_are_safe_and_do_not_collide(self):
        for value in ['../escape','CON','A/B','A?B','trailing.','a'*100,'..']:
            safe=folder_name(value);self.assertNotIn('/',safe);self.assertNotIn('\\',safe);self.assertNotIn(safe,['.','..','CON'])
        self.assertNotEqual(folder_name('A/B'),folder_name('A?B'))
    def test_old_database_paths_recover_after_tree_migration(self):
        ident=self.ingest();self.store.write('DELETE FROM media_locations');self.store.write('UPDATE photos SET path=? WHERE id=?',('originals/'+ident+'.jpg',ident));self.store.mark_layout(ident);self.store.reconcile_layout(limit=None)
        self.assertEqual(self.store.storage_status()['pending'],0);self.assertTrue(Path(self.store.file_paths([ident])[0]).is_file())

if __name__=='__main__':unittest.main()
