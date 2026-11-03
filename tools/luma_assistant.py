"""Small dependency-free client. Does not log the connection token."""
import argparse,json,os,sys
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError

def main():
    parser=argparse.ArgumentParser(description='Manage a running local Luma')
    parser.add_argument('--connection',default=str(Path.home()/'.luma-desktop'/'UserData'/'assistant-connection.json'))
    parser.add_argument('method',help='status, capabilities, or an RPC method')
    group=parser.add_mutually_exclusive_group();group.add_argument('--json',default=None);group.add_argument('--file',type=Path)
    args=parser.parse_args();connection=json.loads(Path(args.connection).read_text(encoding='utf-8-sig'))
    if not connection.get('running') or not connection.get('token'):raise ValueError('Luma 未运行或本机助手端口已关闭')
    url=connection['url']
    from urllib.parse import urlsplit
    parsed=urlsplit(url)
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.username or parsed.password:raise ValueError('连接地址必须是本机 HTTP 端口')
    values=json.loads(args.file.read_text(encoding='utf-8-sig') if args.file else args.json or '{}')
    endpoint='/v1/'+args.method if args.method in {'status','capabilities'} else '/v1/rpc'
    payload=None if args.method in {'status','capabilities'} else json.dumps(dict(method=args.method,args=values),ensure_ascii=False).encode('utf-8')
    request=Request(url+endpoint,data=payload,headers={'Authorization':'Bearer '+connection['token'],'Content-Type':'application/json'})
    try:
        with build_opener(ProxyHandler({})).open(request,timeout=310) as response:result=json.load(response)
    except HTTPError as error:
        try:message=json.load(error).get('error',str(error))
        except ValueError:message=str(error)
        raise ValueError(message) from None
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    if sys.stdout:sys.stdout.reconfigure(encoding='utf-8')
    try:main()
    except (OSError,ValueError) as exc:print(str(exc),file=sys.stderr);sys.exit(1)
