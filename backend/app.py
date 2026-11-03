"""Desktop JSON-RPC host. The library location is stored outside the library."""
import argparse,json,sys,threading,os,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from store import json_text

def main():
    from service import Library
    from workspace_host import WorkspaceHost
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);args=parser.parse_args()
    host=WorkspaceHost(args.root,lambda root:Library(root,defer_recovery=True))
    stdout_lock=threading.Lock();pool=ThreadPoolExecutor(max_workers=4)
    def call(method,a):return host.call(method,a)
    def respond(request):
        try:response={'id':request['id'],'result':call(request['method'],request.get('args',{}))}
        except Exception as exc:response={'id':request.get('id'),'error':str(exc)}
        with stdout_lock:print(json.dumps(response,ensure_ascii=True),flush=True)
    try:
        for line in sys.stdin:
            try:request=json.loads(line)
            except ValueError:continue
            if request.get('method') in ('switchStatus','cancelSwitch'):respond(request)
            else:pool.submit(respond,request)
    finally:
        host.cancel.set()
        with host.condition:
            host.condition.wait_for(lambda:not host.switching,timeout=10)
        library=host.library
        if library:
            library.call('shutdown',{});deadline=time.monotonic()+25
            while library.active and time.monotonic()<deadline:time.sleep(.1)
            library.analyzer.thread.join(timeout=5)
        pool.shutdown(wait=True)
if __name__=='__main__':
    for stream in [sys.stdin,sys.stdout,sys.stderr]:
        if stream:stream.reconfigure(encoding='utf-8')
    if '--inspect-profiles' in sys.argv:
        from profile_info import inspect_profile
        print(json.dumps([inspect_profile(p) for p in json.loads(sys.argv[sys.argv.index('--inspect-profiles')+1])],ensure_ascii=True));sys.exit(0)
    if '--snapshot-profile-library' in sys.argv:
        from profile_info import snapshot_library
        index=sys.argv.index('--snapshot-profile-library');print(json.dumps(snapshot_library(sys.argv[index+1],sys.argv[index+2])));sys.exit(0)
    if '--power' in sys.argv:
        from win_power import execute
        execute(sys.argv[sys.argv.index('--power')+1]);sys.exit(0)
    for flag in ('--probe-account','--following','--download'):
        if flag in sys.argv:
            import subprocess
            from collector_client import collector_command
            sys.exit(subprocess.call(collector_command(flag)))
    main()
