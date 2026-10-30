import PageShell from '@/components/admin/AdminPageShell';
import PlatformAccounts from '@/components/admin/social/connections/PlatformAccounts';
import MetaAccounts from '@/components/admin/social/connections/MetaAccounts';
export default function SocialAccountsPage() {
  return <PageShell title='Connected accounts' subtitle='Verify identity, permissions and account health.' back={{ href: '/admin/social', label: 'Social publishing' }}><MetaAccounts /><PlatformAccounts /></PageShell>;
}
