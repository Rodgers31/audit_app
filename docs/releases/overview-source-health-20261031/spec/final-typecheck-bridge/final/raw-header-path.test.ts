import {AxiosError,AxiosHeaders,type InternalAxiosRequestConfig} from 'axios';
import {writeFileSync} from 'node:fs';
import api from '@/lib/api/axios';
jest.mock('@/lib/supabase/client',()=>({createClient:()=>({auth:{getSession:async()=>({data:{session:null}})}})}));
const original=api.defaults.adapter;const records:any[]=[];
beforeEach(()=>jest.useFakeTimers());afterEach(()=>{api.defaults.adapter=original;jest.useRealTimers()});afterAll(()=>writeFileSync('/evidence/raw-path-values.json',JSON.stringify(records,null,2)));
const fail=(api.interceptors.response as any).handlers.find((h:any)=>h?.rejected).rejected;
function config(){return {headers:new AxiosHeaders(),method:'get',url:'/owned-direct-header-path'} as InternalAxiosRequestConfig;}
test('direct actual interceptor accepts one mixed-case plain-object instruction',async()=>{let calls=0;api.defaults.adapter=async config=>{calls++;return {config,status:200,statusText:'',headers:{},data:{exact:true}}};const c=config(),headers={'rEtRy-AfTeR':'1'};const error=new AxiosError('capacity',AxiosError.ERR_BAD_RESPONSE,c,undefined,{config:c,status:503,statusText:'',data:{},headers});const r=fail(error);await jest.runAllTimersAsync();expect((await r).data).toEqual({exact:true});expect(calls).toBe(1);});
test.each([
 ['linebreak',{'Retry-After':'1\n'}],['array',{'Retry-After':['1']}],['numeric',{'Retry-After':1}],['overbudget',{'Retry-After':'4'}],['absent',{}],['ambiguous-valid-first',{'Retry-After':'1','retry-after':'4'}],['ambiguous-invalid-first',{'Retry-After':'4','retry-after':'1'}],
] as const)('direct actual interceptor refuses raw-object %s',async(name,headers)=>{let calls=0;api.defaults.adapter=async config=>{calls++;return {config,status:200,statusText:'',headers:{},data:{unexpected:true}}};const c=config();const error=new AxiosError('capacity',AxiosError.ERR_BAD_RESPONSE,c,undefined,{config:c,status:503,statusText:'',data:{},headers:headers as any});const result=fail(error).catch((e:any)=>e);await jest.runAllTimersAsync();const r=await result;records.push({name,headers,calls,resultStatus:r.response?.status??r.status});expect(r).toBe(error);expect(calls).toBe(0);});
