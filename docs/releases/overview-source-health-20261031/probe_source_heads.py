import asyncio,json,time,ssl,datetime
import httpx
URLS=["https://www.knbs.or.ke","https://www.treasury.go.ke","https://www.cob.go.ke","https://treasury.go.ke","https://cob.go.ke"]
async def one(url):
 start=time.monotonic()
 async with httpx.AsyncClient(timeout=2.0,follow_redirects=True,max_redirects=2,limits=httpx.Limits(max_connections=1,max_keepalive_connections=0)) as c:
  try:
   r=await c.head(url)
   return {"url":url,"status":r.status_code,"final_url":str(r.url),"redirects":[{"url":str(x.url),"status":x.status_code,"location":x.headers.get("location")} for x in r.history],"seconds":round(time.monotonic()-start,3),"tls_verification":True}
  except Exception as e:
   chain=[];value=e
   for _ in range(8):
    if value is None:break
    chain.append({"type":type(value).__name__,"message":str(value)[:300],"verify_code":getattr(value,"verify_code",None),"verify_message":getattr(value,"verify_message",None)});value=value.__cause__ or value.__context__
   return {"url":url,"seconds":round(time.monotonic()-start,3),"error_chain":chain,"tls_verification":True}
async def main():
 rows=await asyncio.gather(*(one(x) for x in URLS));print(json.dumps({"at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"httpx":httpx.__version__,"results":rows},indent=2))
asyncio.run(main())
