import { SocialAccount, SocialDocument, SocialFormat } from '@/lib/api/social';
import { supportedFormats, resolveContent } from './socialDocument';

/** Use inspected media metadata and known account capabilities; never drop a target. */
export function automaticMediaFormats(document: SocialDocument, accounts: SocialAccount[], mimeTypes: ReadonlyMap<string, string>): SocialDocument {
  return { ...document, targets: document.targets.map(target => {
    const account = accounts.find(item => item.id === target.account_id);
    if (!account) return target;
    const verifiedFormats = supportedFormats(account);
    const formats = verifiedFormats.length ? verifiedFormats : (account.draft_formats ?? []), media = resolveContent(document.master, target).media;
    if (!formats.length) return target;
    let desired: SocialFormat | undefined;
    if (!media.length) desired = 'text';
    else {
      const kinds = media.map(item => mimeTypes.get(item.asset_id));
      if (kinds.some(kind => !kind)) return target;
      if (kinds.every(kind => kind!.startsWith('image/'))) desired = media.length === 1 ? 'image' : 'carousel';
      else if (media.length === 1 && kinds[0] === 'video/mp4') {
        desired = (target.format === 'reel' || account.platform === 'instagram' || !formats.includes('video')) && formats.includes('reel') ? 'reel' : 'video';
      }
    }
    return desired && formats.includes(desired) ? { ...target, format: desired } : target;
  }) };
}
