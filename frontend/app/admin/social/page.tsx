'use client';

import PageShell from '@/components/layout/PageShell';
import SocialWorkspace from '@/components/admin/social/SocialWorkspace';

export default function SocialPage() {
  return <PageShell title='Social publishing' subtitle='Review the evidence. Shape the message. Choose where it goes.' back={{ href: '/admin', label: 'Admin overview' }}><SocialWorkspace /></PageShell>;
}
