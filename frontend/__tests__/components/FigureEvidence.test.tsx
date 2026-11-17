import React from 'react';
import {act,fireEvent,render,screen} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import FigureEvidence from '@/components/evidence/FigureEvidence';
import FigureEvidencePage from '@/app/sources/figures/[table]/[id]/FigureEvidencePage';
import EconomicContextStrip from '@/components/budget/EconomicContextStrip';
import fixture from '../fixtures/figure-qualifications.json';
import type {Qualifications,FigureQualification} from '@/lib/evidence/qualification';
import api from '@/lib/api/axios';
jest.mock('@/lib/api/axios',()=>({__esModule:true,default:{get:jest.fn()}}));
jest.mock('@/components/layout/PageShell',()=>({__esModule:true,default:({children,title}:any)=><main><h1>{title}</h1>{children}</main>}));
jest.mock('framer-motion',()=>({motion:new Proxy({}, {get:()=>({children,initial:_i,whileInView:_w,viewport:_v,transition:_t,...props}:any)=><div {...props}>{children}</div>})}));
const original=fixture.budget_lines.qualifications.allocated_amount as FigureQualification;
it.each(Object.entries(fixture))('renders actual %s handler DTO with separate checks',(_table,response)=>{
 render(<FigureEvidence label='observation' qualifications={response.qualifications as Qualifications}/>);
 expect(screen.getAllByText(/Verified observation/).length).toBeGreaterThan(0);
 expect(screen.getAllByText(/Source bytes: checked · Value: matched/).length).toBeGreaterThan(0);
 expect(screen.queryByText(/Verified total/)).not.toBeInTheDocument();
});
it.each([['qualified','Qualified citation'],['unavailable','Evidence unavailable'],['conflicting','Conflicting evidence'],['modelled','Modelled'],['projected','Projected']] as const)('reports %s independently of bytes check',(status,label)=>{
 render(<FigureEvidence label='budget' qualifications={{allocated_amount:{...original,status}}}/>);
 expect(screen.getByText(`allocated amount · ${label}`)).toBeInTheDocument();
});
it('refuses incomplete verified promotion and excludes hostile URL',()=>{
 render(<FigureEvidence label='budget' qualifications={{allocated_amount:{...original,value_checked:false,source_url:'javascript:alert(1)'}}} table='budget_lines' recordId={1}/>);
 expect(screen.getByText(/allocated amount · Evidence incomplete/)).toBeInTheDocument();
 expect(screen.getByText(/Nairobi · FY2024\/25 · KES · actual/)).toBeInTheDocument();
 expect(screen.queryByRole('link',{name:'Open source document',hidden:true})).not.toBeInTheDocument();
 expect(screen.getByRole('link',{name:'Observation evidence details',hidden:true})).toHaveAttribute('href','/sources/figures/budget_lines/1');
});
it('retains zero GDP and inflation and shows absent context evidence',()=>{
 render(<EconomicContextStrip ctx={{gdp_billion_kes:0,inflation_pct:0,gdp_growth_pct:null}}/>);
 expect(screen.getByText('KES 0B')).toBeInTheDocument();expect(screen.getByText('0.0%')).toBeInTheDocument();
 expect(screen.getAllByText('No source document yet').length).toBeGreaterThan(0);
});
it('replaces cached verified result on downgrade and offers recovery after failure',async()=>{
 const get=api.get as jest.Mock;
 get.mockResolvedValueOnce({data:{...fixture.budget_lines,value:'0'}})
   .mockResolvedValueOnce({data:{value:null,reason:'no_rows',qualifications:{}}})
   .mockRejectedValueOnce(new Error('synthetic offline'))
   .mockResolvedValueOnce({data:{...fixture.budget_lines,value:'0'}});
 const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}});
 render(<QueryClientProvider client={client}><FigureEvidencePage table='budget_lines' id='1'/></QueryClientProvider>);
 await screen.findByRole('heading',{name:'Budget allocation: 0'});expect(screen.getAllByText(/Verified observation/).length).toBeGreaterThan(0);
 expect(screen.queryByRole('button',{name:'Refresh evidence'})).not.toBeInTheDocument();
 await act(() => client.invalidateQueries({queryKey:['figure-evidence','budget_lines','1']}));
 await screen.findByText('Not published');expect(screen.queryByText(/Verified observation/)).not.toBeInTheDocument();
 await act(() => client.invalidateQueries({queryKey:['figure-evidence','budget_lines','1']}));
 await screen.findByRole('alert');expect(screen.queryByRole('heading',{name:/Budget allocation/})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Try again'}));
 await screen.findByRole('heading',{name:'Budget allocation: 0'});
 expect(get).toHaveBeenCalledTimes(4);
 client.clear();
});

it('refuses malformed observation identity even when checks claim success',()=>{
 render(<FigureEvidence label='bad shape' qualifications={{allocated_amount:{...original,identity:{} as FigureQualification['identity']}}}/>);
 expect(screen.queryByText(/Verified observation/)).not.toBeInTheDocument();
 expect(screen.getByText('allocated amount · Evidence unavailable')).toBeInTheDocument();
});

it('keeps an aggregate qualification qualified without promoting it to an observed value',()=>{
 render(<FigureEvidence label='ratio' note={{status:'qualified',reason:'published_imf_ratio_outside_seven_table_contract'}}/>);
 expect(screen.getByRole('button', { name: /Evidence for ratio$/ })).toBeInTheDocument();
 expect(screen.getByText('Source cited, with a caveat')).toBeInTheDocument();
 expect(screen.getByText(/published imf ratio outside seven table contract/)).toBeInTheDocument();
 expect(screen.queryByText(/Verified observation/)).not.toBeInTheDocument();
});
