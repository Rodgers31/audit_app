'use client';
import PageShell from '@/components/admin/AdminPageShell';
import SocialAutomation from '@/components/admin/social/SocialAutomation';
export default function AutomationPage() { return <PageShell title='Draft generation & shadow rules' subtitle='Factual templates and advisory decisions. Human review remains required.' back={{ href: '/admin/social', label: 'Social publishing' }}><SocialAutomation /></PageShell>; }
