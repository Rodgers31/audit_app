import PageShell from '@/components/admin/AdminPageShell';
import PrivacyReview from '@/components/admin/social/PrivacyReview';
export default function PrivacyPage(){return <PageShell title='Privacy review' subtitle='Review authority, approved scope and verified outcomes.' back={{href:'/admin/social',label:'Social publishing'}}><PrivacyReview/></PageShell>;}
