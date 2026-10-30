'use client';
import PageShell from '@/components/admin/AdminPageShell';
import SocialStudio from '@/components/admin/social/SocialStudio';

export default function StudioPage() {
  return <PageShell title='Social studio' subtitle='Review local derivatives, provider observations and publication schedules.' back={{ href: '/admin/social', label: 'Social review queue' }}><SocialStudio /></PageShell>;
}
