# SPDX-License-Identifier: GPL-2.0-only
"""Independent collector: one JSON stdin request, JSON-line stdout events.

May be invoked without Luma. It never opens the library database or loads AI.
"""
import io,json,re,sys

def main():
    for stream in (sys.stdin,sys.stdout,sys.stderr):
        if stream:stream.reconfigure(encoding='utf-8')
    if '--download' in sys.argv:
        prepare('--download')
        from worker import download
        return download()
    if '--following' in sys.argv:
        prepare('--following')
        from following import read_following
        read_following();return 0
    if '--probe-account' in sys.argv:
        prepare('--probe-account')
        from account_health import probe
        probe();return 0
    if '--version' in sys.argv:
        print('Luma collector 0.5.1-beta.1 (GPL-2.0-only); gallery-dl 1.32.19');return 0
    print('Use --download, --following or --probe-account with a JSON stdin request.',file=sys.stderr)
    return 2

def prepare(flag):
    from bootstrap import ensure_engine
    payload=json.load(sys.stdin)
    def progress(message):
        if flag!='--probe-account':print(json.dumps(dict(type='log',level='INFO',message=message),ensure_ascii=False),flush=True)
    try:ensure_engine(payload.get('proxy',''),progress)
    except Exception as exc:
        detail=str(exc)
        for secret in payload.get('cookies',{}).values():
            if secret:detail=detail.replace(secret,'[redacted]')
        detail=re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@',r'\1[redacted]@',detail)
        message='采集组件未准备完成：'+type(exc).__name__+': '+detail[:240]+'；请检查网络或代理后重试，已有媒体和任务保留'
        if flag=='--probe-account':print(json.dumps(dict(state='unknown',reason=message),ensure_ascii=False),flush=True)
        else:
            progress(message)
            result=dict(type='finished',code=1,ok=False,message=message)
            print(json.dumps(result,ensure_ascii=False),flush=True)
        sys.exit(1)
    sys.stdin=io.StringIO(json.dumps(payload))

if __name__=='__main__':sys.exit(main())
