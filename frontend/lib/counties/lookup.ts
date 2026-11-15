import { REGION_COUNTIES } from './regions';

export const COUNTY_LINKS = Object.values(REGION_COUNTIES).flat().map(name => ({
  name,
  // The county API accepts the official name with its apostrophe preserved.
  slug: name === "Murang'a" ? 'Murang%27a' : name.toLowerCase().replace(/'/g, '').replace(/\s+/g, '-'),
}));
