'use client';

import PageShell from '@/components/layout/PageShell';
import { SocialEditorPage } from '@/components/admin/social/SocialWorkspace';
import { useParams } from 'next/navigation';

export default function EditSocialPostPage() {
  const { postId } = useParams<{ postId: string }>();
  return <PageShell title='Review social post' subtitle='Review the saved revision, destinations, and delivery evidence.' back={{ href: '/admin/social', label: 'Social publishing' }}><SocialEditorPage postId={postId} /></PageShell>;
}
