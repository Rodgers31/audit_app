'use client';

import PageShell from '@/components/layout/PageShell';
import { SocialEditorPage } from '@/components/admin/social/SocialWorkspace';

export default function CreateSocialPostPage() {
  return <PageShell title='Create a manual post' subtitle='One master draft. Independent account versions. Human approval.' back={{ href: '/admin/social', label: 'Social publishing' }}><SocialEditorPage /></PageShell>;
}
