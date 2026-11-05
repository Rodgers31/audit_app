"""Trusted test-only entry: actual product main, only HTTPTransport intercepted."""
import os,sys,json,time
from pathlib import Path
bootstrap=json.loads(Path(__file__).with_name('bootstrap.json').read_text())
sys.path[:0]=[bootstrap['backend'],bootstrap['social_tests'],bootstrap['pytest_tool_root']]
import httpx
from social.connections.verification_process import main
ROOT=Path(bootstrap['fixture_root'])
class FixtureTransport(httpx.BaseTransport):
    def __init__(self,*args,**kwargs):self.graph=None
    def handle_request(self,request):
        mode=json.loads((ROOT/'mode.json').read_text()).get('mode','normal')
        path=request.url.path.removeprefix('/v26.0/')
        if request.method!='GET' or path not in {'debug_token','me','me/permissions','me/accounts','801'}:raise RuntimeError('fixture denied non-read')
        with (ROOT/'graph.jsonl').open('a')as out:out.write(json.dumps({'pid':os.getpid(),'method':request.method,'endpoint':path,'optimize':sys.flags.optimize})+'\n')
        if mode=='headers_delay':time.sleep(5)
        if mode=='body_delay':
            class SlowBody(httpx.SyncByteStream):
                def __iter__(self):
                    (ROOT/'body-started').write_text('body')
                    yield b'{'
                    time.sleep(5)
                    yield b'}'
            return httpx.Response(200,stream=SlowBody())
        if mode=='gate' and not (ROOT/'gate-seen').exists():
            (ROOT/'gate-seen').write_text('ready')
            deadline=time.monotonic()+6
            while not (ROOT/'gate-release').exists():
                if time.monotonic()>deadline:raise RuntimeError('fixture gate expired')
                time.sleep(.01)
        if self.graph is None:
            from test_connections_support import FakeGraph
            self.graph=FakeGraph()
        return self.graph(request)
httpx.HTTPTransport=FixtureTransport
if __name__=='__main__':raise SystemExit(main())
