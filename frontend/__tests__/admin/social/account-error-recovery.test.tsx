import SocialComposer from '@/components/admin/social/SocialComposer';
import api from '@/lib/api/axios';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {fireEvent,render,screen,waitFor,cleanup} from '@testing-library/react';
import {accounts,post,system,actorId,facebookId,instagramId,assetId,validation} from '@/tests/socialFixtures';
import {socialKeys} from '@/lib/hooks/useSocial';
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{get:jest.fn(),post:jest.fn(),patch:jest.fn()}}));
jest.mock('@/lib/auth/admin',()=>({useAdmin:()=>({isAdmin:true})}));
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({user:{id:'00000000-0000-4000-8000-000000000001'}})}));
const get=api.get as jest.Mock,send=api.post as jest.Mock,patch=api.patch as jest.Mock;
let clients:QueryClient[]=[];
function mount(p:ReturnType<typeof post>){const qc=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(qc);qc.setQueryData(socialKeys.detail(actorId,p.id),p);return render(<QueryClientProvider client={qc}><SocialComposer initialPost={p} accounts={accounts} system={{...system,publishing_enabled:false}}/></QueryClientProvider>);}
function two(){const p=post();return post({...p,document:{...p.document,targets:[{account_id:facebookId,format:'text',overrides:{link:{mode:'replace',value:'https://example.org/fb'}}},{account_id:instagramId,format:'image',overrides:{link:{mode:'replace',value:'https://example.org/ig'}}}]}});}
const error=(field:string,message:string)=>({isAxiosError:true,response:{status:422,data:{detail:{code:'INVALID_REQUEST',message:'Correct the saved draft inputs.',field_errors:[{code:'INVALID_FIELD',field,message}],target_errors:[],retryable:false}}}});
beforeEach(()=>{jest.clearAllMocks();Object.defineProperty(crypto,'randomUUID',{configurable:true,value:()=> '00000000-0000-4000-8000-000000000123'});});
afterEach(()=>{cleanup();clients.forEach(q=>q.clear());clients=[];});
test('inactive destination schema error selects the account, opens preview and error link keeps input focus',async()=>{
 const p=two();get.mockResolvedValue({data:p});patch.mockRejectedValue(error('body.document.targets.1.overrides.link.value','Correct the Instagram URL'));mount(p);
 fireEvent.click(screen.getByText('Customize this destination'));fireEvent.click(screen.getByRole('button',{name:'Instagram · AuditGava test Instagram'}));fireEvent.change(screen.getByLabelText(/Account URL/),{target:{value:'http://example.org/ig'}});fireEvent.click(screen.getByRole('button',{name:'Facebook · AuditGava test Page'}));fireEvent.click(screen.getByText('Customize this destination'));fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
 await screen.findByRole('alert');await waitFor(()=>expect(screen.getByRole('button',{name:'Instagram · AuditGava test Instagram'})).toHaveAttribute('aria-pressed','true'));
 await waitFor(()=>{if(screen.getByRole('button',{name:'Preview'}).getAttribute('aria-pressed')!=='true')throw new Error('PREVIEW_RECOVERY_MISSING: inactive account error did not expose its preview panel');});const field=screen.getByLabelText(/Account URL/);expect(field).toHaveValue('http://example.org/ig');expect(field).toHaveAttribute('aria-invalid','true');expect(field.closest('details')?.open).toBe(true);expect(screen.getByRole('alert')).toHaveFocus();
 fireEvent.click(screen.getByText('Customize this destination'));fireEvent.click(screen.getByRole('link',{name:'Correct the Instagram URL'}));await waitFor(()=>expect(screen.getByLabelText(/Account URL/)).toHaveFocus());await new Promise(resolve=>setTimeout(resolve,0));expect(screen.getByLabelText(/Account URL/)).toHaveFocus();expect(screen.getByLabelText('Website URL')).not.toHaveAttribute('aria-invalid','true');
});
test('master error returns from preview to editor and field link opens the source reference',async()=>{
 const p=post({references:[{url:'https://example.org/report',label:'Source'}]});get.mockResolvedValue({data:p});patch.mockRejectedValue(error('body.references[0].url','Correct the first source URL'));mount(p);
 fireEvent.click(screen.getByText('Source references'));fireEvent.change(screen.getByLabelText('Source URL 1'),{target:{value:'http://example.org/report'}});fireEvent.click(screen.getByText('Source references'));fireEvent.click(screen.getByRole('button',{name:'Preview'}));fireEvent.click(screen.getByRole('button',{name:'Save draft'}));await screen.findByRole('alert');
 await waitFor(()=>expect(screen.getByRole('button',{name:'Editor'})).toHaveAttribute('aria-pressed','true'));expect(screen.getByLabelText('Source URL 1').closest('details')?.open).toBe(true);fireEvent.click(screen.getByRole('link',{name:'Correct the first source URL'}));await waitFor(()=>expect(screen.getByLabelText('Source URL 1')).toHaveFocus());
});
test('two destination errors with the same raw field keep their account identity in summary links',async()=>{
 const p=two();p.editorial_state='pending_review';p.document.master.media=[{asset_id:assetId,caption_asset_id:null,alt_text:'An inert fixture graphic'}];p.document.targets.forEach(t=>t.format='image');get.mockResolvedValue({data:p});
 send.mockImplementation(async(path:string)=>{if(path.endsWith('/validate'))return {data:validation(p)};throw {isAxiosError:true,response:{status:422,data:{detail:{code:'TARGET_VALIDATION_FAILED',message:'Destination capabilities changed after validation.',field_errors:[],target_errors:[{code:'UNSUPPORTED_FORMAT',field:'format',account_id:facebookId,message:'Correct the Facebook format'},{code:'UNSUPPORTED_FORMAT',field:'format',account_id:instagramId,message:'Correct the Instagram format'}],retryable:false}}}};});
 mount(p);fireEvent.click(screen.getByRole('button',{name:'Save & validate'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Approve revision'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'Approve revision'}));await screen.findByRole('alert');fireEvent.click(screen.getByRole('link',{name:'Correct the Instagram format'}));
 await waitFor(()=>{if(screen.getByRole('button',{name:'Instagram · AuditGava test Instagram'}).getAttribute('aria-pressed')!=='true')throw new Error('TARGET_ERROR_IDENTITY_COLLISION: Instagram format summary selected the Facebook error because both raw fields are format');});expect(screen.getByLabelText('Account format')).toHaveFocus();
});
