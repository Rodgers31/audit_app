import {render,screen,within} from '@testing-library/react';
import OverviewTab from '@/app/counties/[id]/tabs/OverviewTab';
import profile from '../fixtures/figure-profile.json';
import type {CountyComprehensive} from '@/types';
it('uses real comprehensive county zero facts and their exact row links',()=>{
 render(<OverviewTab data={profile as unknown as CountyComprehensive}/>);
 expect(screen.getByText('Poverty headcount: 0%')).toBeInTheDocument();
 expect(screen.getByText('Extreme poverty: Not published')).toBeInTheDocument();
 const gcp=screen.getByText(/Gross county product · 2024/).parentElement!;
 expect(within(gcp).getByText('KES 0')).toBeInTheDocument();
 expect(within(gcp).getAllByText(/Verified observation/).length).toBeGreaterThan(0);
 expect(within(gcp).getByRole('link',{name:'Observation evidence details',hidden:true})).toHaveAttribute('href',`/sources/figures/gdp_data/${profile.economic_profile.latest_gcp.record_id}`);
});
it('withholds absent county facts rather than substituting national or metadata GDP',()=>{
 render(<OverviewTab data={{...profile,economic_profile:{...profile.economic_profile,latest_gcp:null,latest_poverty:null}} as unknown as CountyComprehensive}/>);
 expect(screen.queryByText(/Gross county product/)).not.toBeInTheDocument();
 expect(screen.queryByText(/Poverty headcount:/)).not.toBeInTheDocument();
});
