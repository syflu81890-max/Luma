import runpy,sys
from pathlib import Path
from PIL import Image
runpy.run_path(str(Path(__file__).with_name('seed_upgrade05.py')),run_name='__main__')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from store import Store
root=Path(sys.argv[1]);store=Store(root/'library');store.write("UPDATE accounts SET avatar_url=''")
account=store.ensure_account('studio_one');Image.new('RGB',(100,100),'#6d81ab').save(store.root/'avatars/pinned.jpg')
store.save_account(dict(id=account,avatar_path='avatars/pinned.jpg',pinned_avatar='avatars/pinned.jpg'))
store.remember_note('Indoor photography')
for name in ('First collection','Second collection'):store.collection_action(dict(action='create',name=name))
store.db.close();other=Store(root/'second');other.ensure_account('second_account');other.db.close()
