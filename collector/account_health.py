# SPDX-License-Identifier: GPL-2.0-only
"""Explicit X account-state results. Transport/auth failures are never bans."""
import contextlib,json,re,sys

def user_state(user):
    if not isinstance(user,dict):return dict(state='unknown',reason='平台未返回账号资料')
    kind=user.get('__typename','');reason=str(user.get('reason') or '');message=str(user.get('message') or '')
    if kind=='UserUnavailable':
        banned=reason.lower()=='suspended' or bool(re.fullmatch(r'(?:user (?:is|has been)|this account is) suspended[.!]?',message.strip(),re.I))
        return dict(state='suspended' if banned else 'restricted' if reason.lower() in {'protected','blocked'} else 'not_found',reason=message or reason or '账号当前不可访问')
    if kind=='User' and user.get('rest_id'):return dict(state='active',reason='平台返回正常账号资料')
    return dict(state='unknown',reason='暂时无法确认账号状态')

def probe():
    payload=json.load(sys.stdin);result=dict(state='unknown',reason='检测未完成')
    try:
        with contextlib.redirect_stdout(sys.stderr):
            from gallery_dl import config,extractor
            config.clear();config.set(('extractor','twitter'),'cookies',payload.get('cookies',{}));config.set(('extractor',),'retries',0);config.set(('extractor',),'timeout',15)
            if payload.get('proxy'):config.set(('extractor',),'proxy',payload['proxy'])
            extr=extractor.find('https://x.com/'+payload['handle']+'/media');extr.initialize();extr.login()
            raw=extr.api.user_by_rest_id(payload['external_id']) if payload.get('external_id') else extr.api.user_by_screen_name(payload['handle'])
            result=user_state(raw)
            if result['state']=='active':result['profile']=extr._transform_user(raw)
    except Exception as exc:
        text=str(exc)
        for value in payload.get('cookies',{}).values():
            if value:text=text.replace(value,'[redacted]')
        result=dict(state='unknown',reason='网络、登录或平台响应需要检查：'+text[:180])
    print(json.dumps(result,ensure_ascii=True,default=str),flush=True)
