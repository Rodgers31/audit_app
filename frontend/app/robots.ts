import { MetadataRoute } from 'next';

const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || 'https://auditgava.co.ke';

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: ['/api/', '/auth/', '/account/', '/reset-password/'],
      },
    ],
    sitemap: `${BASE_URL}/sitemap.xml`,
  };
}
