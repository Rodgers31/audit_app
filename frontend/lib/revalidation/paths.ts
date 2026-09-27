/**
 * The pages the nightly revalidates, from the one manifest both the workflow
 * and the route read (issue #231). Edit `paths.json`, not this file.
 */
import manifest from './paths.json';

export const REVALIDATE_PATHS: ReadonlySet<string> = new Set(manifest.paths);

/**
 * `revalidatePath` needs to be told when a path is a route pattern rather
 * than a URL. `/counties/[id]` with type 'page' revalidates every county
 * page; without the type it would match no page at all.
 */
export function revalidateType(p: string): 'page' | undefined {
  return p.includes('[') ? 'page' : undefined;
}
