"""Reviewable local assistant operations and non-destructive edit handoff.

No image generator or account login lives here. Inputs/results are ordinary
local files that an authorized desktop assistant can pass to its image tool.
"""
import hashlib,itertools,json,os,re,shutil,uuid
from pathlib import Path
from PIL import Image
from store import now,json_text,tags

def digest(file):
    with open(file,'rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def save_json(file,data):
    file.parent.mkdir(parents=True,exist_ok=True);pending=file.with_suffix('.'+uuid.uuid4().hex+'.pending')
    pending.write_text(json_text(data),encoding='utf-8');os.replace(pending,file)

def still_image(value):
    file=Path(value).resolve(strict=True)
    if not file.is_file() or file.suffix.lower() not in {'.jpg','.jpeg','.png','.webp','.bmp'}:raise ValueError('请选择 JPG、PNG、WebP 或 BMP 静态照片')
    with Image.open(file) as im:
        if getattr(im,'n_frames',1)>1:raise ValueError('此功能仅处理静态照片')
        im.verify()
    return file

class Assistant:
    def assistant_home(self):return self.root/'edits'/'assistant'
    def assistant_file(self,kind,ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('无效记录 ID')
        return self.assistant_home()/kind/(ident+'.json') if kind=='plans' else self.assistant_home()/kind/ident/'manifest.json'
    def assistant_read(self,kind,ident):
        file=self.assistant_file(kind,ident)
        if not file.is_file():raise ValueError('记录不存在于当前资料库')
        data=json.loads(file.read_text(encoding='utf-8'))
        if kind=='jobs' and data.get('libraryRoot') and Path(data['libraryRoot'])!=self.root:
            old=Path(data['libraryRoot'])
            def remap(value):
                path=Path(value)
                return str(self.root/path.relative_to(old)) if path.is_relative_to(old) else value
            for item in data['items']:
                for key in ('input','output'):
                    if item.get(key):item[key]=remap(item[key])
            data['references']=[remap(value) for value in data['references']];data['libraryRoot']=str(self.root)
        return data
    def assistant_audit(self,action,**summary):
        file=self.assistant_home()/'activity.jsonl';file.parent.mkdir(parents=True,exist_ok=True)
        with file.open('a',encoding='utf-8') as out:out.write(json_text(dict(time=now(),action=action,**summary))+'\n')
    def assistant_fingerprint(self,ids):
        rows=[]
        for ident in ids:
            data=self.query('SELECT id,tags,favorite,trash,note,reviewed FROM photos WHERE id=?',(ident,))
            if not data or data[0]['trash']==2:raise ValueError('所选媒体不存在或已被彻底删除')
            rows.append(data[0])
        return hashlib.sha256(json_text(rows).encode()).hexdigest(),rows
    def assistant_plan(self,a):
        action=a.get('action');allowed={'tags','trash','restore','reviewed','favorite','note'}
        if action not in allowed:raise ValueError('整理计划支持 tags、trash、restore、reviewed、favorite、note')
        if not a.get('ids') and not isinstance(a.get('filters'),dict):raise ValueError('请明确指定 ids 或 filters；全库操作需 filters:{}')
        ids=list(dict.fromkeys(a.get('ids') or self.select_ids(a['filters'])))
        if not ids or len(ids)>5000:raise ValueError('每个计划需选择 1–5000 项；大量操作请分批')
        values={}
        if action=='tags':
            mode=a.get('mode','add')
            if mode not in {'add','remove','replace'}:raise ValueError('标签模式无效')
            values=dict(tags=','.join(tags(str(a.get('value','')))),tagMode=mode)
        elif action in {'trash','restore'}:values={'trash':int(action=='trash')}
        elif action in {'reviewed','favorite'}:values={action:int(bool(a.get('value',True)))}
        else:
            value=str(a.get('value',''))
            if len(value)>20000:raise ValueError('备注过长')
            values={'note':value}
        fingerprint,before=self.assistant_fingerprint(ids);ident=uuid.uuid4().hex
        plan=dict(id=ident,created=now(),status='planned',action=action,count=len(ids),ids=ids,values=values,fingerprint=fingerprint,before=before)
        save_json(self.assistant_file('plans',ident),plan);self.assistant_audit('plan',id=ident,operation=action,count=len(ids))
        return plan
    def assistant_apply(self,a):
        with self.lock:
            plan=self.assistant_read('plans',a['id'])
            if plan['status']=='applied':return dict(id=plan['id'],status='applied',count=plan['count'],alreadyApplied=True)
            if plan['status']!='planned':raise ValueError('此计划已撤销，请重新生成计划')
            fingerprint,_=self.assistant_fingerprint(plan['ids'])
            if fingerprint!=plan['fingerprint']:raise ValueError('媒体已发生变化，请重新生成整理计划')
            result=self.edit(dict(ids=plan['ids'],**plan['values']));after,_=self.assistant_fingerprint(plan['ids']);plan.update(status='applied',applied=now(),afterFingerprint=after);save_json(self.assistant_file('plans',plan['id']),plan)
            self.assistant_audit('apply',id=plan['id'],operation=plan['action'],count=result['updated'])
            return dict(id=plan['id'],status='applied',count=result['updated'],undo='可在图库撤销最近一次编辑；删除仅进入回收站')
    def assistant_undo(self,a):
        with self.lock:
            plan=self.assistant_read('plans',a['id'])
            if plan['status']=='undone':return dict(id=plan['id'],status='undone',alreadyApplied=True)
            fingerprint,_=self.assistant_fingerprint(plan['ids']);last=self.query('SELECT payload FROM undo ORDER BY created DESC LIMIT 1')
            if plan['status']!='applied' or fingerprint!=plan.get('afterFingerprint') or not last or json.loads(last[0]['payload'])!=plan['before']:raise ValueError('此后已有其他编辑，请生成新的整理/恢复计划，避免撤销其他操作')
            self.undo();plan.update(status='undone',undone=now());save_json(self.assistant_file('plans',plan['id']),plan);self.assistant_audit('undo',id=plan['id'],count=plan['count'])
            return dict(id=plan['id'],status='undone',count=plan['count'])
    def assistant_duplicates(self,a):
        threshold=int(a.get('threshold',4))
        if not 0<=threshold<=12:raise ValueError('相似阈值需在 0–12')
        scope=set(self.select_ids(a.get('filters') or {}));groups=[]
        for group in self.similar(threshold):
            group=[ident for ident in group if ident in scope]
            if len(group)<2:continue
            rows=[self.detail(ident) for ident in group];rows.sort(key=lambda p:(p['favorite'],p['width']*p['height'],p['size']),reverse=True)
            groups.append(dict(suggestedKeep=rows[0]['id'],items=rows))
        offset=max(0,int(a.get('offset',0)));limit=max(1,min(50,int(a.get('limit',20))))
        return dict(total=len(groups),offset=offset,groups=groups[offset:offset+limit],threshold=threshold,exactDuplicates='相同内容在入库时已合并，多账号/分类目录中的硬链接是同一媒体',warning='感知相似不代表同一张图；请查看原图后明确指定待删除 ID。接口不会自动删除相似图')
    def assistant_folder(self,a):
        root=Path(a['path']).resolve(strict=True)
        if not root.is_dir():raise ValueError('请选择文件夹')
        offset=max(0,int(a.get('offset',0)));limit=max(1,min(200,int(a.get('limit',100))));items=[]
        files=(p for p in (root.rglob('*') if a.get('recursive',True) else root.iterdir()) if p.is_file() and p.suffix.lower() in {'.jpg','.jpeg','.png','.webp','.bmp'} and p.resolve().is_relative_to(root))
        for file in itertools.islice(files,offset,offset+limit+1):
            if len(items)==limit:break
            try:
                with Image.open(file) as im:w,h=im.size
                ident=digest(file);rows=self.query('SELECT id,trash FROM photos WHERE id=?',(ident,))
                items.append(dict(path=str(file),sha256=ident,width=w,height=h,size=file.stat().st_size,library=rows[0] if rows else None))
            except (OSError,ValueError):items.append(dict(path=str(file),error='无法识别此照片'))
        return dict(path=str(root),offset=offset,items=items,nextOffset=offset+len(items) if len(items)==limit else None,readOnly=True)
    def assistant_prepare_edit(self,a):
        ids=list(dict.fromkeys(a.get('ids') or []));paths=list(dict.fromkeys(a.get('paths') or []));references=a.get('references') or []
        if not 1<=len(ids)+len(paths)<=100 or len(references)>10:raise ValueError('每批选择 1–100 张照片，人物参考最多 10 张')
        prompt=str(a.get('prompt','')).strip()
        if not prompt or len(prompt)>20000:raise ValueError('请提供修改要求（不超过 20000 字）')
        sources=[]
        for ident in ids:
            row=self.detail(ident);files=self.file_paths([ident])
            if row['trash'] or row['kind']!='image' or not files:raise ValueError('仅可选择在库中的正常静态照片')
            sources.append((still_image(files[0]),ident))
        for value in paths:
            file=still_image(value);sha=digest(file);row=self.query('SELECT id FROM photos WHERE id=? AND trash=0',(sha,));sources.append((file,row[0]['id'] if row else ''))
        ref_files=[still_image(p) for p in references];ident=uuid.uuid4().hex;manifest=self.assistant_file('jobs',ident);directory=manifest.parent;directory.mkdir(parents=True)
        job=dict(id=ident,created=now(),status='awaiting_generation',libraryRoot=str(self.root),prompt=prompt,items=[],references=[],generator='由当前对话中的图片编辑工具执行；Luma 不自行生成')
        for index,(source,parent) in enumerate(sources):
            dest=directory/'inputs'/f'{index:03}{source.suffix.lower()}';dest.parent.mkdir(exist_ok=True);shutil.copy2(source,dest)
            sha=digest(dest)
            if digest(source)!=sha:raise ValueError('原文件在准备时发生变化，请重试')
            job['items'].append(dict(index=index,source=str(source),input=str(dest),sha256=sha,parent=parent,status='pending'))
        for index,source in enumerate(ref_files):
            dest=directory/'references'/f'{index:02}{source.suffix.lower()}';dest.parent.mkdir(exist_ok=True);shutil.copy2(source,dest);job['references'].append(str(dest))
        save_json(manifest,job);self.assistant_audit('prepareEdit',id=ident,count=len(sources));return job
    def assistant_commit_edit(self,a):
        with self.lock:
            job=self.assistant_read('jobs',a['id']);index=int(a['index'])
            if not 0<=index<len(job['items']):raise ValueError('无效图片序号')
            item=job['items'][index]
            if item['status']=='completed':return dict(job=job['id'],index=index,photo=item['result'],alreadyApplied=True)
            original=still_image(item['input'])
            if digest(original)!=item['sha256']:raise ValueError('输入副本已被改动，无法确认原始版本')
            source=still_image(a['path']);sha=digest(source)
            if sha==item['sha256']:raise ValueError('结果与原图完全相同')
            existing=self.query('SELECT id FROM photos WHERE id=?',(sha,))
            if existing and item.get('preparedSha')!=sha:raise ValueError('结果已存在于图库，未修改其原有版本关联')
            if self.query('SELECT 1 FROM excluded_content WHERE photo=?',(sha,)):raise ValueError('结果曾被删除，请先在图库恢复')
            resultfile=self.assistant_file('jobs',job['id']).parent/'results'/f'{index:03}-{sha}{source.suffix.lower()}';resultfile.parent.mkdir(exist_ok=True)
            if source!=resultfile:shutil.copy2(source,resultfile)
            if digest(resultfile)!=sha:raise ValueError('结果复制校验失败')
            item.update(preparedSha=sha,output=str(resultfile));save_json(self.assistant_file('jobs',job['id']),job)
            parent=item['parent']
            if not parent:
                imported=self.import_files([str(original)])
                if imported['failed'] or imported['excluded']:raise ValueError('原图无法入库，或有删除排除记录')
                parent=item['sha256'];item['parent']=parent
            detail=self.detail(parent)
            if detail['trash']:raise ValueError('原始版本已删除，请恢复后重试')
            imported=self.import_files([str(resultfile)])
            if imported['failed'] or imported['excluded']:raise ValueError('修改结果无法入库')
            self.write('UPDATE photos SET parent=?,tags=?,note=?,author=?,reviewed=0 WHERE id=?',(parent,','.join(dict.fromkeys(tags(detail['tags'])+['AI修改'])),f"AI 修改版本 · 作业 {job['id']} · {job['prompt']}",detail['author'],sha))
            # Keep provenance and source-account relationships on the generated version.
            with self.transaction() as db:
                db.execute('INSERT OR IGNORE INTO account_photos SELECT account,?,first_seen FROM account_photos WHERE photo=?',(sha,parent))
                db.execute('INSERT OR IGNORE INTO album_photos SELECT album,? FROM album_photos WHERE photo=?',(sha,parent))
                db.execute('INSERT OR IGNORE INTO sources(photo,url,metadata,account,post_id,published,content) SELECT ?,url,metadata,account,post_id,published,content FROM sources WHERE photo=?',(sha,parent))
            self.mark_layout(sha);self.reconcile_layout(limit=10)
            item.update(status='completed',result=sha,completed=now());job['status']='completed' if all(i['status']=='completed' for i in job['items']) else 'in_progress'
            save_json(self.assistant_file('jobs',job['id']),job);self.assistant_audit('commitEdit',id=job['id'],index=index,photo=sha,parent=parent)
            return dict(job=job['id'],index=index,photo=sha,parent=parent,originalPreserved=True,path=self.file_paths([sha])[0])
    def assistant_call(self,method,a):
        if method=='assistantPlan':
            with self.lock:return self.assistant_plan(a)
        if method=='assistantPlanInfo':return self.assistant_read('plans',a['id'])
        if method=='assistantApply':return self.assistant_apply(a)
        if method=='assistantUndo':return self.assistant_undo(a)
        if method=='assistantDuplicates':return self.assistant_duplicates(a)
        if method=='assistantFolder':return self.assistant_folder(a)
        if method=='assistantEditPrepare':return self.assistant_prepare_edit(a)
        if method=='assistantEditCommit':return self.assistant_commit_edit(a)
        if method=='assistantJob':return self.assistant_read('jobs',a['id'])
        if method=='assistantJobs':
            jobs=[]
            for file in (self.assistant_home()/'jobs').glob('*/manifest.json'):
                data=json.loads(file.read_text(encoding='utf-8'));jobs.append({k:data[k] for k in ('id','created','status','prompt')})
            jobs.sort(key=lambda x:x['created'],reverse=True);return jobs[:100]
        raise ValueError('未知助手操作')
