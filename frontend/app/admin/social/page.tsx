'use client';

import PageShell from '@/components/admin/AdminPageShell';
import SocialWorkspace from '@/components/admin/social/SocialWorkspace';

export default function SocialPage() {
  return <PageShell title='Social drafts' subtitle='Open a draft, shape the message and review the evidence.' back={{ href: '/admin', label: 'Admin overview' }}><SocialWorkspace /></PageShell>;
}
