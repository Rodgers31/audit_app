import { validateHttpBaseUrl } from '../config/public-config.cjs';

/** Browser requests use the baked public URL; server requests may use container DNS. */
export function getApiBase(): string {
  if (typeof window === 'undefined' && process.env.INTERNAL_API_URL !== undefined) {
    return validateHttpBaseUrl(process.env.INTERNAL_API_URL, 'INTERNAL_API_URL');
  }
  return validateHttpBaseUrl(
    process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
    'NEXT_PUBLIC_API_URL'
  );
}
