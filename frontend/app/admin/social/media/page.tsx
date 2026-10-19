'use client';
import PageShell from '@/components/layout/PageShell';
import MediaPicker from '@/components/admin/social/media/MediaPicker';

export default function MediaLibraryPage() {
  return <PageShell title='Media library' subtitle='Inspect usage and safely archive unused assets. Stored bytes and quota remain retained.' back={{ href: '/admin/social', label: 'Social publishing' }}><MediaPicker /></PageShell>;
}
