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
test('failed saves reveal and focus the invalid setting rather than leaving it hidden',async()=>{
 get.mockResolvedValue({data:post()});send.mockRejectedValue(failure('content_type','Use a lowercase content type'));mount();fireEvent.click(screen.getByText('Post settings & hashtags'));fireEvent.change(screen.getByLabelText('Content type'),{target:{value:'Not supported!'}});fireEvent.click(screen.getByText('Post settings & hashtags'));fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'A clear draft'}});fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Use a lowercase content type');const field=screen.getByLabelText('Content type');expect(field).toHaveAttribute('aria-invalid','true');expect(field.closest('details')?.open).toBe(true);expect(field).toBeVisible();expect(screen.getByRole('alert')).toHaveFocus();expect(screen.getByRole('link',{name:/Use a lowercase content type/})).toBeInTheDocument();
});

test('an indexed hashtag error reveals the hashtag field and links to it',async()=>{
 get.mockResolvedValue({data:post()});send.mockRejectedValue(failure('document.master.hashtags.0','Use a valid hashtag'));
 mount();fireEvent.change(screen.getByLabelText('Post text'),{target:{value:'Draft with a source'}});fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
 await screen.findByRole('alert');const field=screen.getByLabelText(/Master hashtags/);expect(field.closest('details')?.open).toBe(true);expect(field).toHaveAttribute('aria-invalid','true');expect(screen.getByRole('link',{name:'Use a valid hashtag'})).toHaveAttribute('href','#'+field.id);
});
