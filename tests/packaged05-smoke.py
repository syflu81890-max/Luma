"""Launch the packaged app with an explicit temporary profile; never touches live data."""
import json,os,subprocess,tempfile,time,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];portable=os.environ.get('LUMA_TEST_PORTABLE')=='1';exe=root/'release-v05'/'Luma 0.5.0.exe' if portable else root/'release-v05'/'win-unpacked'/'Luma.exe'
with tempfile.TemporaryDirectory(prefix='luma-packaged05-') as temporary:
    profile=Path(temporary);(profile/'assistant-settings.json').write_text(json.dumps(dict(enabled=True,port=0)),encoding='utf-8')
    env={**os.environ,'LUMA_TEST_ROOT':str(profile),'LUMA_RECOVERY_VERIFY':'1','LUMA_POWER_DRY_RUN':'1'}
    process=subprocess.Popen([str(exe),'--background'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));report={};main_pid=process.pid
    try:
        connection=profile/'assistant-connection.json';deadline=time.monotonic()+35
        while not connection.is_file() and time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Packaged desktop exited before startup')
            time.sleep(.1)
        info=json.loads(connection.read_text(encoding='utf-8'));candidate=int(info['pid'])
        if candidate!=process.pid:
            assert portable,'Unexpected process identity'
            ancestor=candidate
            for _ in range(6):
                if ancestor==process.pid:break
                output=subprocess.check_output(['powershell.exe','-NoProfile','-Command',f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {ancestor}').ParentProcessId"],text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));ancestor=int(output.strip())
            assert ancestor==process.pid,'Portable child does not belong to test process'
        main_pid=candidate
        def call(method,args=None):
            request=urllib.request.Request(info['url']+'/v1/rpc',data=json.dumps(dict(method=method,args=args or {})).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+info['token']})
            with urllib.request.urlopen(request,timeout=30) as response:result=json.load(response)
            if result.get('error'):raise RuntimeError(result['error'])
            return result['result']
        stats=call('stats');assert Path(stats['root']).resolve()==(profile/'library').resolve();assert stats['total']==0
        assert call('accountHealthStatus')['status']=='idle';assert call('collections')==[]
        request=urllib.request.Request(info['url']+'/v1/status',headers={'Authorization':'Bearer '+info['token']})
        with urllib.request.urlopen(request,timeout=10) as response:status=json.load(response)
        assert status['version']=='0.5.0'
        report=dict(ok=True,version=status['version'],connectionFormat=info['version'],isolatedProfile=True,httpBackend=True,portable=portable,media=stats['total'])
        (root/('output/portable05-smoke.json' if portable else 'output/packaged05-smoke.json')).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
    finally:
        # Only this explicitly isolated test process and its child tree are terminated.
        if process.poll() is None:
            subprocess.run(['taskkill','/PID',str(main_pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            try:process.wait(timeout=25)
            except subprocess.TimeoutExpired:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15);process.wait(timeout=10)
        time.sleep(.5)
