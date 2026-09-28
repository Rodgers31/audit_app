/** Kenya's eight former provinces for the County Explorer regional filter. */
export const REGION_COUNTIES = {
  central: ['Kiambu', 'Kirinyaga', "Murang'a", 'Nyandarua', 'Nyeri'],
  coast: ['Kilifi', 'Kwale', 'Lamu', 'Mombasa', 'Taita Taveta', 'Tana River'],
  eastern: ['Embu', 'Isiolo', 'Kitui', 'Machakos', 'Makueni', 'Marsabit', 'Meru', 'Tharaka Nithi'],
  nairobi: ['Nairobi'],
  'north-eastern': ['Garissa', 'Mandera', 'Wajir'],
  nyanza: ['Homa Bay', 'Kisii', 'Kisumu', 'Migori', 'Nyamira', 'Siaya'],
  'rift-valley': [
    'Baringo', 'Bomet', 'Elgeyo Marakwet', 'Kajiado', 'Kericho', 'Laikipia',
    'Nakuru', 'Nandi', 'Narok', 'Samburu', 'Trans Nzoia', 'Turkana',
    'Uasin Gishu', 'West Pokot',
  ],
  western: ['Bungoma', 'Busia', 'Kakamega', 'Vihiga'],
} as const;

export type CountyRegion = keyof typeof REGION_COUNTIES;

/** Use one key for API names, GADM paths, hyphen variants, and "County" suffixes. */
export function normalizeCountyName(name: string): string {
  return name
    .trim()
    .replace(/\s+County$/i, '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]/gi, '')
    .toLowerCase();
}

const REGION_BY_NAME = new Map<string, CountyRegion>(
  Object.entries(REGION_COUNTIES).flatMap(([region, names]) =>
    names.map((name) => [normalizeCountyName(name), region as CountyRegion] as const)
  )
);
REGION_BY_NAME.set(normalizeCountyName('Nairobi City'), 'nairobi');

export function getCountyRegion(name: string): CountyRegion | null {
  return REGION_BY_NAME.get(normalizeCountyName(name)) ?? null;
}
