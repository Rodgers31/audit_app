'use client';

import PageShell from '@/components/admin/AdminPageShell';
import { SocialEditorPage } from '@/components/admin/social/SocialWorkspace';

export default function CreateSocialPostPage() {
  return <PageShell title='Write a post' subtitle='Start with the message. Preview it before sending it for review.' back={{ href: '/admin/social', label: 'Social publishing' }}><SocialEditorPage /></PageShell>;
}
