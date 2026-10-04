import PageShell from '@/components/layout/PageShell';
import MetaAccounts from '@/components/admin/social/connections/MetaAccounts';
export default function SocialAccountsPage() {
  return <PageShell title='Connected accounts' subtitle='Verify identity, permissions and account health.' back={{ href: '/admin/social', label: 'Social publishing' }}><MetaAccounts /></PageShell>;
}
