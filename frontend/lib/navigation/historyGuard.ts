'use client';

import { useCallback, useEffect, useRef } from 'react';

const KEY = '__auditgavaHistory';
type Point = { document: string; position: number };
type Guard = () => boolean;
type Approval = { epoch: number; guards: Set<Guard> };
let tracking: { retain: () => () => void; guards: Set<Guard>; readonly epoch: number; approvedTraversal?: Approval } | undefined;
const approvedClicks = new WeakMap<Event, Set<Guard>>();

function takeApprovedGuards(): Set<Guard> {
  const approval = tracking?.approvedTraversal;
  if (tracking) tracking.approvedTraversal = undefined;
  return approval && approval.epoch === tracking?.epoch ? approval.guards : new Set();
}

export function consumeApprovedTraversal(): boolean {
  const approved = takeApprovedGuards();
  return !!tracking && Array.from(tracking.guards).every(guard => approved.has(guard));
}

export function runHistoryTraversal(event: Event, navigate: () => void): void {
  const approved = approvedClicks.get(event);
  approvedClicks.delete(event);
  if (tracking && approved) tracking.approvedTraversal = { epoch: tracking.epoch, guards: approved };
  try { navigate(); } catch (error) {
    if (tracking) tracking.approvedTraversal = undefined;
    throw error;
  }
}

/** Track same-document entries without replacing Next's history state. */
export function retainHistoryTracking(): () => void {
  if (tracking) return tracking.retain();
  const history = window.history;
  const push = history.pushState, replace = history.replaceState;
  const document = crypto.randomUUID();
  let position = 0, highestPosition = 0, epoch = 0, references = 0, restoring = false;
  let currentUrl = window.location.href, currentState = history.state;
  const guards = new Set<() => boolean>();
  const stamp = (data: unknown, point: number) => ({ ...(data && typeof data === 'object' ? data : {}), [KEY]: { document, position: point } });
  const snapshot = () => { currentUrl = window.location.href; currentState = history.state; epoch++; };
  const point = (state: unknown): Point | undefined => {
    const value = state && typeof state === 'object' ? (state as Record<string, unknown>)[KEY] as Point | undefined : undefined;
    return value?.document === document && Number.isSafeInteger(value.position)
      && value.position >= 0 && value.position <= highestPosition ? value : undefined;
  };
  const trackedPush: History['pushState'] = function (data, unused, url) {
    push.call(history, stamp(data, position + 1), unused, url); position++; highestPosition = position; snapshot();
  };
  const trackedReplace: History['replaceState'] = function (data, unused, url) {
    replace.call(history, stamp(data, position), unused, url); snapshot();
  };
  history.pushState = trackedPush; history.replaceState = trackedReplace;
  trackedReplace(history.state, '', window.location.href);
  const onPop = (event: PopStateEvent) => {
    const destination = point(event.state);
    if (restoring) {
      event.stopImmediatePropagation();
      if (destination?.position === position) { restoring = false; snapshot(); }
      else if (destination) history.go(position - destination.position);
      return;
    }
    const approved = takeApprovedGuards();
    if (!Array.from(guards).every(leave => approved.has(leave) || leave())) {
      // Capture runs before Next's listener, so the dirty editor stays mounted.
      event.stopImmediatePropagation();
      if (destination && destination.position !== position) {
        restoring = true; history.go(position - destination.position);
      } else {
        // An entry created before tracking has no trustworthy traversal delta.
        // Restore the editor URL rather than guessing which history entry to pop.
        push.call(history, currentState, '', currentUrl);
      }
      return;
    }
    if (destination) position = destination.position;
    snapshot();
  };
  window.addEventListener('popstate', onPop, true);
  const owner = { guards, get epoch() { return epoch; }, approvedTraversal: undefined as Approval | undefined, retain: () => {
    references++;
    return () => {
      if (--references) return;
      window.removeEventListener('popstate', onPop, true);
      if (history.pushState === trackedPush) history.pushState = push;
      if (history.replaceState === trackedReplace) history.replaceState = replace;
      if (tracking === owner) tracking = undefined;
    };
  } };
  tracking = owner;
  return owner.retain();
}

export function useUnsavedHistoryGuard(dirty: boolean, draftContext?: unknown): (event: Event) => boolean {
  const currentGuard = useRef<Guard | undefined>(undefined);
  useEffect(() => retainHistoryTracking(), []);
  useEffect(() => {
    if (!dirty || !tracking) return;
    const guards = tracking.guards;
    const leave = () => window.confirm('This draft has unsaved edits. Leave without saving?');
    currentGuard.current = leave;
    guards.add(leave);
    return () => { guards.delete(leave); if (currentGuard.current === leave) currentGuard.current = undefined; };
  }, [dirty, draftContext]);
  return useCallback((event: Event) => {
    const leave = currentGuard.current;
    if (!leave || !leave()) return false;
    const approved = approvedClicks.get(event) ?? new Set<Guard>();
    approved.add(leave); approvedClicks.set(event, approved);
    return true;
  }, []);
}
