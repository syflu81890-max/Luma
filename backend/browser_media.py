"""Extract media only from tweets visible in the user's authenticated page."""
import re
from datetime import datetime
from urllib.parse import urlparse,urlunparse,parse_qsl,urlencode

def safe_media_url(value):
    try:
        u=urlparse(str(value))
        return u.scheme=='https' and u.hostname in {'pbs.twimg.com','video.twimg.com'} and not u.username and not u.password and u.port in (None,443)
    except ValueError:return False

def extract_candidates(data,owner='',owner_id='',post_id=''):
    stack=[data];seen=set();visited=0
    while stack and visited<100000:
        node=stack.pop();visited+=1
        if isinstance(node,list):stack.extend(node);continue
        if not isinstance(node,dict):continue
        stack.extend(v for v in node.values() if isinstance(v,(dict,list)))
        legacy=node.get('legacy') or {}
        if not isinstance(legacy,dict):continue
        post=str(node.get('rest_id') or legacy.get('id_str') or '')
        if not post.isdigit() or not legacy.get('extended_entities'):continue
        if post_id and post!=post_id:continue
        raw=(node.get('core') or {}).get('user_results',{}).get('result',{});core=raw.get('core') or {};profile=raw.get('legacy') or {}
        handle=str(core.get('screen_name') or profile.get('screen_name') or '')
        if not re.fullmatch(r'[A-Za-z0-9_]{1,15}',handle):continue
        if owner and handle.lower()!=owner.lower() and not (owner_id and str(raw.get('rest_id',''))==str(owner_id)):continue
        author=dict(id=raw.get('rest_id',''),name=handle,nick=core.get('name') or profile.get('name',handle),profile_image=(raw.get('avatar') or {}).get('image_url') or profile.get('profile_image_url_https',''),protected=bool((raw.get('privacy') or profile).get('protected')))
        published=''
        try:published=datetime.strptime(legacy.get('created_at',''),'%a %b %d %H:%M:%S %z %Y').isoformat()
        except (ValueError,TypeError):pass
        content=(node.get('note_tweet') or {}).get('note_tweet_results',{}).get('result',{}).get('text') or legacy.get('full_text') or legacy.get('text','')
        for number,media in enumerate(legacy['extended_entities'].get('media',[]),1):
            if not isinstance(media,dict):continue
            key=f'{post}:{number}'
            if key in seen:continue
            kind=media.get('type');url='';ext='jpg'
            if kind=='photo':
                url=str(media.get('media_url_https',''))
                if safe_media_url(url):
                    u=urlparse(url);ext=u.path.rsplit('.',1)[-1].lower();ext=ext if ext in ('jpg','jpeg','png','webp') else 'jpg'
                    params=dict(parse_qsl(u.query));params.update(name='orig');url=urlunparse(u._replace(query=urlencode(params)))
            elif kind in ('video','animated_gif'):
                variants=[v for v in (media.get('video_info') or {}).get('variants',[]) if v.get('content_type')=='video/mp4' and safe_media_url(v.get('url',''))]
                if variants:url=max(variants,key=lambda v:int(v.get('bitrate') or 0))['url'];ext='mp4'
            if not safe_media_url(url):continue
            seen.add(key)
            yield dict(key=key,url=url,metadata=dict(tweet_id=post,num=number,type=kind,extension=ext,date=published,content=str(content),author=author))
