"""Persistent, resumable near-duplicate review. New scans reuse prior work."""
import hashlib,json,threading,uuid
from collections import OrderedDict
from PIL import Image,ImageOps,ImageChops,ImageStat
from store import now,json_text
from similarity import Similarity

ALGORITHM='verified-pixels-v2'

def group_signature(group):return hashlib.sha256(','.join(sorted(r['id'] for r in group['items'])).encode()).hexdigest()

class PersistentSimilarity(Similarity):
    def _cached_groups(self):
        groups={};files={};processed=set()
        active={r['id']:r for r in self.query("SELECT id,path,width,height,size,phash,favorite,parent FROM photos WHERE trash=0 AND kind='image'")}
        for saved in self.query('SELECT * FROM similar_scan_items WHERE algorithm=?',(ALGORITHM,)):
            if saved['photo'] not in active:continue
            metadata=json.loads(saved['metadata']);current=active[saved['photo']]
            if any(metadata.get(key)!=current.get(key) for key in ('parent','width','height','phash')):continue
            row={**metadata,**current};ident=row['id'];processed.add(ident)
            files[ident]=json.loads(saved['fingerprint'])
            if saved['excluded']:continue
            group=groups.setdefault(saved['group_id'],dict(id=saved['group_id'],items=[]));group['items'].append(row)
        for group in groups.values():
            group['items'].sort(key=lambda r:(r['width']*r['height'],r['size']),reverse=True);group['keep']=group['items'][0]
        return list(groups.values()),files,processed

    def similar_status(self):
        if getattr(self,'similar_job',None) is None:
            groups,files,processed=self._cached_groups();previous=self.settings().get('similarLastRun') or {}
            if not processed:return dict(status='idle',scanned=0,total=0,groupCount=0,duplicateCount=0,excluded=0,cached=0)
            duplicates=[g for g in groups if len(g['items'])>1]
            self.similar_job=dict(id=previous.get('id') or uuid.uuid4().hex,status='completed',created=previous.get('created',''),scanned=previous.get('scanned',0),total=previous.get('total',0),cached=len(processed),groupCount=len(duplicates),duplicateCount=sum(len(g['items'])-1 for g in duplicates),excluded=0,groups=duplicates,files=files,error='',resumeAvailable=previous.get('status') in ('running','cancelled','failed'))
        return super().similar_status()

    def start_similar_scan(self,a):
        if self.similar_status()['status']=='running':return self.similar_status()
        mode=a.get('mode','new')
        if mode not in ('new','all','selected','account'):raise ValueError('无效相似图检查范围')
        if mode=='selected' and not a.get('ids'):raise ValueError('请先选择要检查的图片')
        if mode=='account' and not a.get('account'):raise ValueError('请选择要检查的账号')
        if len(a.get('ids',[]))>5000:raise ValueError('每次最多选择 5000 张图片')
        rows=self.query("SELECT id,path,width,height,size,phash,favorite,parent FROM photos WHERE trash=0 AND kind='image' AND phash<>'' ORDER BY width*height DESC,size DESC,id")
        if mode=='selected':wanted=set(a['ids']);rows=[r for r in rows if r['id'] in wanted]
        if mode=='account':wanted={r['photo'] for r in self.query('SELECT photo FROM account_photos WHERE account=?',(a['account'],))};rows=[r for r in rows if r['id'] in wanted]
        if mode=='all':self.write('DELETE FROM similar_scan_items WHERE algorithm=?',(ALGORITHM,))
        groups,files,processed=self._cached_groups()
        if mode=='selected':
            reset={r['id'] for r in rows};groups=[{**g,'items':[r for r in g['items'] if r['id'] not in reset]} for g in groups];groups=[g for g in groups if g['items']]
            for group in groups:group['keep']=group['items'][0]
            processed-=reset
        pending=[row for row in rows if row['id'] not in processed]
        job=dict(id=uuid.uuid4().hex,status='running',created=now(),mode=mode,scanned=0,total=len(pending),cached=len(processed),groupCount=0,duplicateCount=0,excluded=0,groups=[],files=files,error='')
        self.similar_job=job;self.busy_operations+=1;self.completion_generation+=1
        def checkpoint():
            current=[g for g in groups if len(g['items'])>1];job['groups']=current;job['groupCount']=len(current);job['duplicateCount']=sum(len(g['items'])-1 for g in current)
            self.write("INSERT OR REPLACE INTO settings VALUES('similarLastRun',?)",(json_text({k:v for k,v in job.items() if k not in ('groups','files')}),))
        def scan():
            buckets={};cache=OrderedDict()
            def register(index):
                value=int(groups[index]['keep']['phash'],16)
                for band in range(5):buckets.setdefault((band,(value>>(band*13))&8191),set()).add(index)
            def features(row):
                ident=row['id']
                if ident in cache:cache.move_to_end(ident);return cache[ident]
                path=self.path(row['path']);stat=path.stat();fingerprint=dict(size=stat.st_size,mtime=stat.st_mtime_ns)
                if ident in processed and files.get(ident)!=fingerprint:raise RuntimeError('已检查的文件发生变化，请选择重新检查全库')
                with Image.open(path) as im:rgb=ImageOps.exif_transpose(im).convert('RGB').resize((128,128),Image.Resampling.LANCZOS)
                gray=rgb.convert('L');hist=gray.histogram();files[ident]=fingerprint
                if ImageStat.Stat(gray).stddev[0]<10 or sum(hist[245:])/16384>.85:return None
                cache[ident]=rgb
                if len(cache)>256:cache.popitem(last=False)
                return rgb
            def same(image,row,other):
                if (int(row['phash'],16)^int(other['phash'],16)).bit_count()>4 or abs((row['width']/row['height'])/(other['width']/other['height'])-1)>.02:return False
                reference=features(other)
                if reference is None:return False
                difference=ImageStat.Stat(ImageChops.difference(image,reference));return max(difference.mean)<=7 and max(difference.rms)<=16
            def persist(row,group_id='',excluded=0):
                self.write('INSERT OR REPLACE INTO similar_scan_items VALUES(?,?,?,?,?,?)',(row['id'],ALGORITHM,group_id,json_text(row),json_text(files.get(row['id'],{})),excluded))
            try:
                for index in range(len(groups)):register(index)
                checkpoint()
                for row in pending:
                    if self.closed or job.get('cancelled'):job['status']='cancelled';return
                    job['scanned']+=1
                    if row['parent'] or row['width']<=0 or row['height']<=0:job['excluded']+=1;persist(row,excluded=1);continue
                    value=int(row['phash'],16);candidates=set()
                    for band in range(5):candidates.update(buckets.get((band,(value>>(band*13))&8191),()))
                    try:
                        image=features(row)
                        if image is None:job['excluded']+=1;persist(row,excluded=1);continue
                        matched=None
                        for index in sorted(candidates):
                            group=groups[index]
                            if same(image,row,group['keep']) and all(same(image,row,item) for item in group['items'] if item['id']!=group['keep']['id']):matched=group;break
                        if matched is None:
                            matched=dict(id=row['id'] if row['id'] not in {g['id'] for g in groups} else uuid.uuid4().hex,keep=row,items=[]);groups.append(matched);register(len(groups)-1)
                        matched['items'].append(row);matched['items'].sort(key=lambda r:(r['width']*r['height'],r['size']),reverse=True)
                        if matched['keep']['id']!=matched['items'][0]['id']:
                            matched['keep']=matched['items'][0];register(groups.index(matched))
                        persist(row,matched['id'])
                    except (OSError,ValueError):job['excluded']+=1;persist(row,excluded=1)
                    if job['scanned']%16==0:checkpoint()
                job['status']='completed'
            except Exception as exc:job.update(status='failed',error=str(exc)[:240])
            finally:
                try:checkpoint()
                finally:self.busy_operations-=1;cache.clear()
        threading.Thread(target=scan,daemon=True).start();return self.similar_status()

    def similar_page(self,a):
        self.similar_status();job=getattr(self,'similar_job',None)
        if not job:return dict(items=[],total=0,page=1,pages=1,scan=self.similar_status())
        active={r['id'] for r in self.query('SELECT id FROM photos WHERE trash=0')};ignored={r['signature'] for r in self.query('SELECT signature FROM similar_ignored')};groups=[]
        for group in job.get('groups',[]):
            items=[r for r in group['items'] if r['id'] in active]
            if len(items)<2:continue
            current={**group,'items':items}
            if not a.get('showIgnored') and group_signature(current) in ignored:continue
            groups.append(current)
        size=12;pages=max(1,(len(groups)+size-1)//size);page=min(pages,max(1,int(a.get('page',1))));result=[]
        for group in groups[(page-1)*size:page*size]:
            items=sorted(group['items'],key=lambda r:(r['width']*r['height'],r['size']),reverse=True)
            result.append(dict(id=group['id'],keep=items[0]['id'],items=items[:8],ids=[r['id'] for r in items],count=len(items)))
        job.update(groupCount=len(groups),duplicateCount=sum(len(g['items'])-1 for g in groups))
        return dict(items=result,total=len(groups),page=page,pages=pages,scan=self.similar_status())

    def ignore_similar(self,a):
        self.similar_status();selected=set(a.get('groups',[]))
        for group in getattr(self,'similar_job',{}).get('groups',[]):
            if group['id'] in selected:self.write('INSERT OR REPLACE INTO similar_ignored VALUES(?,?)',(group_signature(group),now()))
        return self.similar_page({})

    def similar_plan(self,a):
        self.similar_status()
        if not a.get('groups'):
            active={r['id'] for r in self.query('SELECT id FROM photos WHERE trash=0')};ignored={r['signature'] for r in self.query('SELECT signature FROM similar_ignored')};chosen=[]
            for group in self.similar_job.get('groups',[]):
                items=[r for r in group['items'] if r['id'] in active]
                if len(items)>1 and group_signature(dict(items=items)) not in ignored:chosen.append(group['id'])
            if not chosen:raise ValueError('没有可处理的重复项；已忽略的组会继续保留')
            a={**a,'groups':chosen}
        return super().similar_plan(a)
