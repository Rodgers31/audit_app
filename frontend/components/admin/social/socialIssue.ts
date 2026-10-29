import type { SocialIssue } from '@/lib/api/social';

/** A target field is identified by both its account and request path. */
export function socialIssueKey(issue: SocialIssue): string {
  return JSON.stringify([issue.account_id ?? null, issue.field]);
}
