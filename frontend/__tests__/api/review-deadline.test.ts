/** @jest-environment node */
import { createHmac } from 'crypto';
import { POST as reset } from '@/app/api/auth/reset-password/route';
import { POST as revalidate } from '@/app/api/revalidate/route';
const mockCookies = jest.fn();
const mockInvalidate = jest.fn();
const mockAuth = { exchangeCodeForSession: jest.fn(), updateUser: jest.fn(), signOut: jest.fn() };
jest.mock('next/headers', () => ({ cookies: () => mockCookies() }));
jest.mock('next/cache', () => ({ revalidatePath: (...a: unknown[]) => mockInvalidate(...a) }));
jest.mock('@supabase/ssr', () => ({ createServerClient: () => ({ auth: mockAuth }) }));
function request() {return new Request('https://app.test/api/auth/reset-password', {method:'POST',headers:{origin:'https://app.test','content-type':'application/json'},body:JSON.stringify({password:'INERT_PASSWORD_123'})});}
const store={get:()=>({value:'INERT_CODE'}),getAll:()=>[]};
beforeEach(()=>{jest.useFakeTimers();jest.clearAllMocks();mockCookies.mockResolvedValue(store);mockAuth.exchangeCodeForSession.mockResolvedValue({data:{session:{}},error:null});mockAuth.updateUser.mockResolvedValue({error:null});process.env.REVALIDATE_SECRET='INERT_SECRET';});
afterEach(()=>jest.useRealTimers());
test('actual reset must respond to its deadline while cookie lookup is pending', async()=>{
 let open!:(x:any)=>void;mockCookies.mockReturnValue(new Promise(resolve=>open=resolve));
 let status:number|undefined;const task=reset(request()).then(r=>{status=r.status;return r;});
 for(let i=0;i<50 && !mockCookies.mock.calls.length;i++)await Promise.resolve();
 expect(mockCookies).toHaveBeenCalledTimes(1);
 await jest.advanceTimersByTimeAsync(16000);
 const observed=status;open(store);await task;
 expect(observed).toBe(504);
});
test('last synchronous revalidation cannot report success beyond total deadline',async()=>{
 mockInvalidate.mockImplementation(()=>jest.advanceTimersByTime(6000));
 const body=JSON.stringify({paths:['/']});
 const r=new Request('https://app.test/api/revalidate',{method:'POST',headers:{'x-revalidate-signature':createHmac('sha256','INERT_SECRET').update(body).digest('hex')},body});
 const response=await revalidate(r as any);
 expect(response.status).toBe(504);
});
