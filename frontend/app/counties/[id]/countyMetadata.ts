import { COUNTY_LINKS } from '@/lib/counties/lookup';

// Keep the First Schedule order used by backend/services/county_identity.py.
// Only the legacy route IDs for Nairobi and Mombasa reverse this order.
const officialCountyNames = [
  'Mombasa', 'Kwale', 'Kilifi', 'Tana River', 'Lamu', 'Taita Taveta',
  'Garissa', 'Wajir', 'Mandera', 'Marsabit', 'Isiolo', 'Meru',
  'Tharaka Nithi', 'Embu', 'Kitui', 'Machakos', 'Makueni', 'Nyandarua',
  'Nyeri', 'Kirinyaga', "Murang'a", 'Kiambu', 'Turkana', 'West Pokot',
  'Samburu', 'Trans Nzoia', 'Uasin Gishu', 'Elgeyo Marakwet', 'Nandi', 'Baringo',
  'Laikipia', 'Nakuru', 'Narok', 'Kajiado', 'Kericho', 'Bomet',
  'Kakamega', 'Vihiga', 'Bungoma', 'Busia', 'Siaya', 'Kisumu',
  'Homa Bay', 'Migori', 'Kisii', 'Nyamira', 'Nairobi',
] as const;

function countyNameKey(value: string): string {
  return value.trim()
    .replace(/\s+county$/i, '')
    .toLowerCase()
    .replace(/’/g, "'")
    .replace(/-/g, ' ')
    .replace(/\s+/g, ' ');
}

const countyByName = new Map(COUNTY_LINKS.map(county => [countyNameKey(county.name), county] as const));

export function resolveCountyMetadataRoute(id: string) {
  // Next's App Router encodes dynamic params before passing them to the page.
  let route: string;
  try {
    route = decodeURIComponent(id).trim();
  } catch {
    return undefined;
  }
  // Unpadded IDs are database primary keys with no static county mapping.
  const numeric = /^(code:)?(\d{3})$/.exec(route);
  if (numeric) {
    const [, official, value] = numeric;
    const code = !official && value === '001' ? '047' : !official && value === '047' ? '001' : value;
    const name = officialCountyNames[Number(code) - 1];
    return name ? countyByName.get(countyNameKey(name)) : undefined;
  }
  const key = countyNameKey(route);
  return countyByName.get(key === 'nairobi city' ? 'nairobi' : key);
}
