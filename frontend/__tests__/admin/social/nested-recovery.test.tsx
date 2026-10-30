import SocialComposer from '@/components/admin/social/SocialComposer';
import GeneratedEvidence from '@/components/admin/social/GeneratedEvidence';
import api from '@/lib/api/axios';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {fireEvent,render,screen,waitFor,cleanup,within} from '@testing-library/react';
import {accounts,post,system,actorId} from '@/tests/socialFixtures';
import {socialKeys} from '@/lib/hooks/useSocial';
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{get:jest.fn(),post:jest.fn(),patch:jest.fn()}}));
jest.mock('@/lib/auth/admin',()=>({useAdmin:()=>({isAdmin:true})}));
jest.mock('@/lib/auth/AuthProvider',()=>({useAuth:()=>({user:{id:'00000000-0000-4000-8000-000000000001'}})}));
const get=api.get as jest.Mock, send=api.post as jest.Mock, patch=api.patch as jest.Mock;
let clients:QueryClient[]=[];
function mount(p?:ReturnType<typeof post>){const qc=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});clients.push(qc);if(p)qc.setQueryData(socialKeys.detail(actorId,p.id),p);return render(<QueryClientProvider client={qc}><SocialComposer initialPost={p} accounts={accounts} system={{...system,publishing_enabled:false}}/></QueryClientProvider>);}
beforeEach(()=>{jest.clearAllMocks();Object.defineProperty(crypto,'randomUUID',{configurable:true,value:()=> '00000000-0000-4000-8000-000000000123'});});
afterEach(()=>{cleanup();clients.forEach(q=>q.clear());clients=[];});
const failure=(field:string,message='Correct this field')=>({isAxiosError:true,response:{status:422,data:{detail:{code:'VALIDATION_FAILED',message:'One field needs attention',field_errors:[{code:'INVALID_FIELD',field,message}],target_errors:[],retryable:false}}}});

test('indexed master hashtag error reveals the settings control',async()=>{
 get.mockResolvedValue({data:post()});send.mockRejectedValue(failure('body.document.master.hashtags.0','This field is invalid or unsupported.'));mount();
 fireEvent.click(screen.getByText('Post settings & hashtags'));fireEvent.change(screen.getByLabelText(/Master hashtags/),{target:{value:'#'+'a'.repeat(100)}});fireEvent.click(screen.getByText('Post settings & hashtags'));
 fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'A clear draft'}});fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
 await screen.findByRole('alert');const field=screen.getByLabelText(/Master hashtags/);if(!field.closest('details')?.open)throw new Error('INDEXED_SETTING_HIDDEN: document.master.hashtags.0 did not reveal the invalid hashtag control');expect(field).toHaveAttribute('aria-invalid','true');expect(field).toBeVisible();
});
test('account override schema error reveals the account field rather than the master URL',async()=>{
 const p=post();get.mockResolvedValue({data:p});patch.mockRejectedValue(failure('body.document.targets.0.overrides.link.value','Use an absolute HTTPS URL without embedded credentials'));mount(p);
 fireEvent.click(screen.getByText('Customize this destination'));fireEvent.click(screen.getByRole('button',{name:'Customize link'}));fireEvent.change(screen.getByLabelText(/Account URL/),{target:{value:'http://example.org/report'}});fireEvent.click(screen.getByText('Customize this destination'));fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
 await screen.findByRole('alert');const field=screen.getByLabelText(/Account URL/);if(!field.closest('details')?.open)throw new Error('ACCOUNT_OVERRIDE_HIDDEN: document.targets.0.overrides.link.value did not reveal the account URL correction control');expect(field).toHaveAttribute('aria-invalid','true');expect(field).toBeVisible();expect(screen.getByLabelText('Website URL')).not.toHaveAttribute('aria-invalid','true');
});
