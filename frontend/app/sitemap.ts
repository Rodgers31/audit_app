import type { MetadataRoute } from 'next';
import { COUNTY_LINKS } from '@/lib/counties/lookup';

const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || 'https://www.auditgava.com';

export default function sitemap(): MetadataRoute.Sitemap {
  // A sitemap generation date does not establish the freshness of these pages.
  return [
    {
      url: BASE_URL,
      changeFrequency: 'daily',
      priority: 1,
    },
    {
      url: `${BASE_URL}/debt`,
      changeFrequency: 'weekly',
      priority: 0.9,
    },
    {
      url: `${BASE_URL}/budget`,
      changeFrequency: 'weekly',
      priority: 0.9,
    },
    {
      url: `${BASE_URL}/counties`,
      changeFrequency: 'weekly',
      priority: 0.9,
    },
    {
      url: `${BASE_URL}/transparency`,
      changeFrequency: 'weekly',
      priority: 0.8,
    },
    {
      url: `${BASE_URL}/learn`,
      changeFrequency: 'monthly',
      priority: 0.7,
    },
    {
      url: `${BASE_URL}/learn/glossary`,
      changeFrequency: 'monthly',
      priority: 0.5,
    },
    {
      url: `${BASE_URL}/learn/government`,
      changeFrequency: 'monthly',
      priority: 0.5,
    },
    {
      url: `${BASE_URL}/learn/quiz`,
      changeFrequency: 'monthly',
      priority: 0.4,
    },
    {
      url: `${BASE_URL}/about`,
      changeFrequency: 'monthly',
      priority: 0.4,
    },
    {
      url: `${BASE_URL}/privacy`,
      changeFrequency: 'yearly',
      priority: 0.2,
    },
    {
      url: `${BASE_URL}/terms`,
      changeFrequency: 'yearly',
      priority: 0.2,
    },
    { url: `${BASE_URL}/audits` },
    { url: `${BASE_URL}/sources` },
    { url: `${BASE_URL}/counties/compare` },
    { url: `${BASE_URL}/accountability/unaccounted-funds` },
    { url: `${BASE_URL}/learn/why-it-matters` },
    ...COUNTY_LINKS.map(({ slug }) => ({ url: `${BASE_URL}/counties/${slug}` })),
  ];
}
