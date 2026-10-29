'use client';

import PageShell from '@/components/admin/AdminPageShell';
import { SocialEditorPage } from '@/components/admin/social/SocialWorkspace';
import { queueReturnHref } from '@/components/admin/social/socialQueue';
import { useParams, useSearchParams } from 'next/navigation';

export default function EditSocialPostPage() {
  const { postId } = useParams<{ postId: string }>();
  const query = useSearchParams();
  return <PageShell title='Review draft' subtitle='Read the post, check the source and review this exact revision.' back={{ href: queueReturnHref(query.get('queue')), label: 'Social drafts' }}><SocialEditorPage postId={postId} /></PageShell>;
}
