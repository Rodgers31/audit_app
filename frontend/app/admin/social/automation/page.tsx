'use client';
import { Suspense } from 'react';
import PageShell from '@/components/admin/AdminPageShell';
import SocialAutomation from '@/components/admin/social/SocialAutomation';
export default function AutomationPage() { return <PageShell title='Source checks & draft controls' subtitle='Find out why a source did or did not produce a draft.' back={{ href: '/admin/social', label: 'Social publishing' }}><Suspense fallback={<p role='status'>Loading source selection…</p>}><SocialAutomation /></Suspense></PageShell>; }
