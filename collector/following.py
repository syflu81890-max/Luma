# SPDX-License-Identifier: GPL-2.0-only
"""Read authorized following lists in an isolated gallery-dl process."""
import contextlib,json,logging,re,sys
from common import json_text

def read_following():
    payload=json.load(sys.stdin);stream=sys.stdout
    def emit(kind,**data):stream.write(json_text(dict(type=kind,**data))+'\n');stream.flush()
    logging.basicConfig(level=logging.CRITICAL,force=True)
    try:
        if not payload.get('cookies',{}).get('auth_token'):raise ValueError('缺少本地 X 登录会话，请先登录后读取关注')
        import gallery_dl.config as config
        from gallery_dl import extractor
        config.clear()
        for key,value in dict(cookies=payload['cookies'],retries=1,timeout=25,ratelimit='abort',cursor=payload.get('cursor') or None).items():config.set(('extractor','twitter'),key,value)
        if payload.get('proxy'):config.set(('extractor',),'proxy',payload['proxy'])
        with contextlib.redirect_stdout(sys.stderr):
            extr=extractor.find('https://x.com/'+payload['owner']+'/following');extr.initialize();extr.login()
            update=extr._update_cursor
            def cursor(value):
                result=update(value);emit('cursor',cursor=value);return result
            extr._update_cursor=cursor
            count=0
            for raw in extr.api.user_following(payload['owner']):
                if raw.get('rest_id'):emit('user',user=extr._transform_user(raw));count+=1
            expected=(getattr(extr,'_user',None) or {}).get('friends_count') or 0
            if not count and int(expected)>0:raise RuntimeError('账号显示已有关注，但平台没有返回名单；请检查登录身份、网络或稍后重试')
        emit('finished',ok=True,message='关注列表已读取完成；可勾选账号加入采集任务')
    except Exception as exc:
        message=str(exc)
        for secret in payload.get('cookies',{}).values():
            if secret:message=message.replace(secret,'[redacted]')
        message=re.sub(r'(auth_token|ct0|authorization|cookie)[\s:=]+\S+',r'\1=[redacted]',message,flags=re.I)
        emit('finished',ok=False,message='读取未完成：'+message[:350]+'；已读取的结果保留')
