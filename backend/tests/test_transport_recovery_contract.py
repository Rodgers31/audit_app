"""Real SeedingHttpClient paths over inert HTTP streams; no publisher claims."""
import ssl
import httpx
import pytest
from seeding.config import SeedingSettings
from seeding.http_client import SeedingHttpClient, PdfDownloadIncomplete

URL='https://cog.go.ke/current-governors/'


def settings(tmp_path):
    return SeedingSettings(_env_file=None, storage_path=tmp_path, http_cache_enabled=False,
                           rate_limit='1000/sec', max_retries=3, retry_backoff=0.001)


def test_pdf_certificate_failure_is_not_progress(tmp_path):
    calls=[]
    def handler(request):
        calls.append(request)
        try: raise ssl.SSLCertVerificationError(1, 'certificate verify failed: hostname mismatch')
        except ssl.SSLCertVerificationError as cause:
            raise httpx.ConnectError('TLS refused', request=request) from cause
    with SeedingHttpClient(settings(tmp_path), client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(httpx.ConnectError):
            client.download_to_file(URL, tmp_path/'out.pdf', max_seconds=1, resume_part=tmp_path/'out.part')
    assert len(calls)==1
    assert not (tmp_path/'out.pdf').exists()
    assert not (tmp_path/'out.part').exists()


class BrokenBody(httpx.SyncByteStream):
    def __iter__(self):
        yield b'partial'
        raise httpx.ReadError('body interrupted')


def test_bounded_get_recovers_dns_connect_and_body(tmp_path):
    calls=[]
    def handler(request):
        calls.append(request)
        if len(calls)==1: raise httpx.ConnectError('[Errno -3] Temporary failure in name resolution')
        if len(calls)==2: return httpx.Response(200, stream=BrokenBody())
        return httpx.Response(200, text='complete')
    with SeedingHttpClient(settings(tmp_path), client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        response=client.get(URL, max_seconds=2, max_bytes=1024, allowed_hosts={'cog.go.ke'}, cache=False)
    assert response.text=='complete'
    assert len(calls)==3
    assert response.extensions['response_receipt']['request_url']==URL


def test_bounded_get_cumulative_bytes(tmp_path):
    def handler(request): return httpx.Response(200, stream=BrokenBody())
    with SeedingHttpClient(settings(tmp_path), client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(Exception, match='byte'):
            client.get(URL, max_seconds=1, max_bytes=10, allowed_hosts={'cog.go.ke'}, cache=False)

@pytest.mark.parametrize('value', [None,0,-1,True,float('nan'),float('inf'),'1'])
def test_direct_bounds_refuse_invalid_deadlines(tmp_path,value):
    with SeedingHttpClient(settings(tmp_path), client=httpx.Client(transport=httpx.MockTransport(lambda r:pytest.fail('no network')))) as client:
        with pytest.raises((ValueError,TypeError)):
            client.get(URL,max_seconds=value,max_bytes=1024,allowed_hosts={'cog.go.ke'},cache=False)


def test_official_redirect_refused_before_external_connection(tmp_path):
    calls=[]
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302,headers={'location':'https://names.invalid/roster'})
    with SeedingHttpClient(settings(tmp_path),client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(ValueError,match='origin'):
            client.get(URL,max_seconds=1,max_bytes=1000,allowed_hosts={'cog.go.ke'},cache=False)
    assert calls==[URL]


def test_slow_body_deadline_closes_response(tmp_path):
    import time
    closed=[]
    class Slow(httpx.SyncByteStream):
        def __iter__(self):
            time.sleep(.03)
            yield b'late'
        def close(self):closed.append(True)
    with SeedingHttpClient(settings(tmp_path),client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,stream=Slow())))) as client:
        with pytest.raises(httpx.TimeoutException):
            client.get(URL,max_seconds=.01,max_bytes=1000,allowed_hosts={'cog.go.ke'},cache=False)
    assert closed


def test_cached_whole_pdf_cannot_bypass_caller_byte_cap(tmp_path):
    from seeding.pdf_download import get_or_download_pdf
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,content=b'%PDF-1.7\n'+b'x'*100+b'\n%%EOF\n')
    with SeedingHttpClient(settings(tmp_path),client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        result=get_or_download_pdf(client,URL,cache_dir=tmp_path/'pdfs',ttl_seconds=3600,max_seconds=1,max_bytes=1000)
        from seeding.http_client import PdfDownloadError
        with pytest.raises(PdfDownloadError,match='cached PDF exceeded'):
            get_or_download_pdf(client,URL,cache_dir=tmp_path/'pdfs',ttl_seconds=3600,max_seconds=1,max_bytes=16)
        assert result.exists()
    assert len(calls)==1


def test_bounded_acquisition_restores_earlier_cli_timer(tmp_path):
    import signal,time
    from seeding.http_client import _wall_clock_budget
    old=signal.getsignal(signal.SIGALRM)
    def earlier(signum,frame): raise RuntimeError('CLI domain deadline')
    try:
        signal.signal(signal.SIGALRM,earlier);signal.setitimer(signal.ITIMER_REAL,.02)
        with pytest.raises(RuntimeError,match='CLI domain deadline'):
            with _wall_clock_budget(.5):time.sleep(.1)
        assert signal.getsignal(signal.SIGALRM) is earlier
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)


@pytest.mark.parametrize('status',[204,206,304])
@pytest.mark.parametrize('with_location',[False,True])
def test_incomplete_status_cannot_recover_via_location(tmp_path,status,with_location):
    from services.receipt_store import LocalReceiptStore
    calls=[]
    def handler(request):
        calls.append(str(request.url))
        if request.url.path=='/current-governors/':
            return httpx.Response(status,headers={'location':'/alternate/'} if with_location else {},content=b'partial')
        return httpx.Response(200,text='a fresh body at another path')
    store=LocalReceiptStore(tmp_path/'retained')
    with SeedingHttpClient(settings(tmp_path),client=httpx.Client(transport=httpx.MockTransport(handler)),receipt_store=store) as client:
        with pytest.raises((ValueError,httpx.HTTPStatusError)):
            client.get(URL,max_seconds=1,max_bytes=1024,allowed_hosts={'cog.go.ke'},cache=False)
        assert client.download_receipt(URL) is None
    assert calls==[URL]
    assert not list((tmp_path/'retained').rglob('*'))


@pytest.mark.parametrize("slow_phase", ["rate_limit", "connect", "body"])
def test_pdf_wall_clock_interrupts_blocking_phases(tmp_path, slow_phase):
    import time
    from contextlib import contextmanager
    from seeding.http_client import PdfDownloadIncomplete
    calls=[]
    class Limiter:
        @contextmanager
        def context(self):
            if slow_phase == "rate_limit": time.sleep(.4)
            yield
    class SlowBody(httpx.SyncByteStream):
        def __iter__(self):
            time.sleep(.4)
            yield b"%PDF-1.7\nbody\n%%EOF"
    def handler(request):
        calls.append(True)
        if slow_phase == "connect": time.sleep(.4)
        return httpx.Response(200, stream=SlowBody() if slow_phase == "body" else httpx.ByteStream(b"%PDF-1.7\n%%EOF"))
    started=time.monotonic()
    with SeedingHttpClient(settings(tmp_path), rate_limiter=Limiter(), client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        with pytest.raises(PdfDownloadIncomplete):
            client.download_to_file(URL, tmp_path/"deadline.pdf", max_seconds=.03)
        assert client.download_receipt(URL) is None
    assert time.monotonic()-started < .25
    assert not (tmp_path/"deadline.pdf").exists()
    assert not list(tmp_path.glob("deadline.pdf.*.part"))
    if slow_phase == "rate_limit": assert not calls
