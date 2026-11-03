"""Conservative near-duplicate review, with directly verified representatives."""
import threading,uuid
from collections import OrderedDict
from PIL import Image,ImageOps,ImageChops,ImageStat
from store import now

class Similarity:
    def similar_status(self):
        job=getattr(self,'similar_job',None)
        return {k:v for k,v in job.items() if k not in {'groups','files'}} if job else dict(status='idle',scanned=0,total=0,groupCount=0,duplicateCount=0,excluded=0)
    def start_similar_scan(self,a):
        if self.similar_status()['status']=='running':return self.similar_status()
        rows=self.query("SELECT id,path,width,height,size,phash,favorite,parent FROM photos WHERE trash=0 AND kind='image' AND phash<>'' ORDER BY width*height DESC,size DESC,id")
        job=dict(id=uuid.uuid4().hex,status='running',created=now(),scanned=0,total=len(rows),groupCount=0,duplicateCount=0,excluded=0,groups=[],files={},error='')
        self.similar_job=job;self.busy_operations+=1;self.completion_generation+=1
        def scan():
            buckets={};cache=OrderedDict();groups=[]
            def features(row):
                ident=row['id']
                if ident in cache:cache.move_to_end(ident);return cache[ident]
                file=self.path(row['path']);stat=file.stat()
                with Image.open(file) as im:rgb=ImageOps.exif_transpose(im).convert('RGB').resize((128,128),Image.Resampling.LANCZOS)
                gray=rgb.convert('L');hist=gray.histogram()
                if ImageStat.Stat(gray).stddev[0]<10 or sum(hist[245:])/16384>.85:return None
                cache[ident]=rgb;job['files'][ident]=dict(size=stat.st_size,mtime=stat.st_mtime_ns)
                if len(cache)>256:cache.popitem(last=False)
                return rgb
            try:
                for row in rows:
                    if self.closed or job.get('cancelled'):job['status']='cancelled';return
                    job['scanned']+=1
                    if row['parent'] or row['width']<=0 or row['height']<=0:job['excluded']+=1;continue
                    value=int(row['phash'],16);candidates=set()
                    # Five disjoint bands guarantee one equal band for Hamming distance <= 4.
                    for band in range(5):candidates.update(buckets.get((band,(value>>(band*13))&8191),()))
                    matched=False
                    try:
                        image=features(row)
                        if image is None:job['excluded']+=1;continue
                        for index in sorted(candidates):
                            group=groups[index];keep=group['keep'];other=int(keep['phash'],16)
                            if (value^other).bit_count()>4 or abs((row['width']/row['height'])/(keep['width']/keep['height'])-1)>.02:continue
                            reference=features(keep)
                            if reference is None:continue
                            difference=ImageStat.Stat(ImageChops.difference(image,reference))
                            if max(difference.mean)>7 or max(difference.rms)>16:continue
                            group['items'].append(row);matched=True;job['duplicateCount']+=1
                            if len(group['items'])==2:job['groupCount']+=1
                            break
                        if not matched:
                            index=len(groups);groups.append(dict(id=row['id'],keep=row,items=[row]))
                            for band in range(5):buckets.setdefault((band,(value>>(band*13))&8191),[]).append(index)
                    except (OSError,ValueError):job['excluded']+=1
                job['groups']=[group for group in groups if len(group['items'])>1];job['status']='completed'
            except Exception as exc:job.update(status='failed',error=str(exc)[:240])
            finally:self.busy_operations-=1;cache.clear()
        threading.Thread(target=scan,daemon=True).start();return self.similar_status()
    def similar_page(self,a):
        job=getattr(self,'similar_job',None);groups=job.get('groups',[]) if job and job['status']=='completed' else [];size=12;page=max(1,int(a.get('page',1)));result=[]
        for group in groups[(page-1)*size:page*size]:
            rows=[]
            for row in group['items']:
                current=self.query('SELECT trash FROM photos WHERE id=?',(row['id'],))
                if current and not current[0]['trash']:rows.append(row)
            if len(rows)<2:continue
            rows.sort(key=lambda r:(r['width']*r['height'],r['size']),reverse=True)
            result.append(dict(id=group['id'],keep=rows[0]['id'],items=rows[:8],ids=[r['id'] for r in rows],count=len(rows)))
        return dict(items=result,total=len(groups),page=page,pages=max(1,(len(groups)+size-1)//size),scan=self.similar_status())
    def similar_plan(self,a):
        job=getattr(self,'similar_job',None)
        if not job or job['status']!='completed':raise ValueError('请先完成一次相似图检查')
        chosen=set(a.get('groups') or []);remove=[];keeps=[];protected=0
        for group in job['groups']:
            if chosen and group['id'] not in chosen:continue
            active=[]
            for row in group['items']:
                current=self.query('SELECT * FROM photos WHERE id=? AND trash=0',(row['id'],))
                if current:
                    current=current[0];file=self.path(current['path'])
                    if not file.is_file():raise ValueError('媒体位置发生变化，请重新检查相似图')
                    stat=file.stat();fingerprint=job['files'].get(row['id'])
                    if fingerprint!=dict(size=stat.st_size,mtime=stat.st_mtime_ns):raise ValueError('原文件在扫描后发生变化，请重新检查')
                    active.append(current)
            if len(active)<2:continue
            active.sort(key=lambda r:(r['width']*r['height'],r['size']),reverse=True);keep=active[0];keeps.append(keep['id'])
            for row in active[1:]:
                if a.get('protectFavorites',True) and row['favorite']:protected+=1
                else:remove.append(row['id'])
        if not remove:raise ValueError('没有可处理的重复项；收藏保护中的图片会继续保留')
        if len(remove)>5000:raise ValueError('候选超过 5000 项，请按页或按组选取后分批处理')
        plan=self.assistant_plan(dict(action='trash',ids=remove))
        return dict(id=plan['id'],count=len(remove),keeps=keeps,remove=remove,protected=protected,groups=len(keeps),message='保留每组像素数最高的照片，其余移入回收站；收藏保护默认开启')
