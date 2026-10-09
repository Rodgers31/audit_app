'use client';
import type { DispatchSource } from '@/lib/admin/etlDispatch';

export interface SubmittedIntent {source:DispatchSource;dry_run:boolean;key:string;generation:string}
// Browser memory only; written by event handlers, never during SSR. Keep one
// unresolved intent across AdminGuard's profile-revalidation unmount. Receipts
// and credentials are never stored here; only the originating actor can recover.
let pending: {actorId:string;intent:SubmittedIntent}|null=null;
export function rememberSubmittedIntent(actorId:string, intent:SubmittedIntent) {
  pending={actorId,intent:{source:intent.source,dry_run:intent.dry_run,key:intent.key,generation:intent.generation}};
}
export function submittedIntent(actorId:string|null) {
  return actorId && pending?.actorId===actorId ? pending.intent : null;
}
export function clearSubmittedIntent(actorId:string|null, key:string) {
  if(pending?.actorId===actorId && pending?.intent.key===key) pending=null;
}
