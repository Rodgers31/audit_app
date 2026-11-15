import { MESSAGES } from '@/lib/i18n/messages';
import { FOUNDATION_MESSAGES } from '@/lib/i18n/messages/foundation';
import { SHELL_MESSAGES } from '@/lib/i18n/messages/shell';

it('registers every redesign message with all three modes and preserves its interpolation fields', () => {
  for (const bundle of [FOUNDATION_MESSAGES, SHELL_MESSAGES]) {
    for (const [key, entry] of Object.entries(bundle)) {
      expect(MESSAGES[key as keyof typeof MESSAGES]).toEqual(entry);
      const fields = (copy: string) => Array.from(copy.matchAll(/\{(\w+)\}/g), match => match[1]).sort();
      for (const mode of ['en', 'sw', 'plain'] as const) {
        expect(entry[mode].trim()).not.toBe('');
        expect(fields(entry[mode])).toEqual(fields(entry.en));
      }
    }
  }
});
