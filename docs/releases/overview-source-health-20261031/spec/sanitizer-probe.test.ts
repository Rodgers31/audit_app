import {AxiosError,AxiosHeaders} from 'axios';
import {writeFileSync} from 'node:fs';
import api from '@/lib/api/axios';
jest.mock('@/lib/supabase/client',()=>({createClient:()=>({auth:{getSession:async()=>({data:{session:null}})}})}));
const records:any[]=[];const original=api.defaults.adapter;
beforeEach(()=>jest.useFakeTimers());
afterEach(()=>{api.defaults.adapter=original;jest.useRealTimers()});
afterAll(()=>writeFileSync('/evidence/sanitizer-probe-values.json',JSON.stringify(records,null,2)));
test.each(['1\n','1\r\n'])('plain raw object is sanitized before interceptor: %p',async raw=>{
 const headers={'Retry-After':raw};const normalized=AxiosHeaders.from(headers).get('Retry-After');expect(normalized).toBe('1');let calls=0;let seen:any;
 api.defaults.adapter=async config=>{calls++;const r={config,status:calls===1?503:200,statusText:'',data:{ok:true},headers};if(calls===1){const error=new AxiosError('capacity',AxiosError.ERR_BAD_RESPONSE,config,undefined,r);seen=error;throw error;}return r};
 const result=api.get('/sanitized').catch(e=>e);await jest.runAllTimersAsync();const r=await result;expect(r.status).toBe(200);expect(calls).toBe(2);records.push({kind:'plain-object',raw,normalized,boundaryHeader:seen.response.headers.get('Retry-After'),calls,status:r.status});
});
test.each(['1\n','1\r\n'])('raw mutated AxiosHeaders instance reaches strict interceptor: %p',async raw=>{
 const headers=new AxiosHeaders();(headers as any)['Retry-After']=raw;const normalized=AxiosHeaders.from(headers).get('Retry-After');expect(normalized).toBe(raw);let calls=0;
 api.defaults.adapter=async config=>{calls++;const r={config,status:calls===1?503:200,statusText:'',data:{ok:true},headers};if(calls===1)throw new AxiosError('capacity',AxiosError.ERR_BAD_RESPONSE,config,undefined,r);return r};
 const result=api.get('/raw-instance').catch(e=>e);await jest.runAllTimersAsync();const r=await result;records.push({kind:'mutated-AxiosHeaders-instance',raw,normalized,calls,status:r.response?.status??r.status});expect(r.response?.status).toBe(503);expect(calls).toBe(1);
});
