'use client';

import { useEffect, useRef } from 'react';

/** Reconcile a native query change made before Next installs its history handlers. */
export function useReconcileInitialQuery(query: string) {
  const initialQuery = useRef(query);
  useEffect(() => {
    let mounted = true;
    // Run after the other mount effects, including Next's History API integration.
    queueMicrotask(() => {
      if (mounted && new URLSearchParams(window.location.search).toString() !== initialQuery.current) {
        // Supported History API integration updates the router without a Flight
        // request or another entry, preserving the browser's current URL/hash.
        const state = { ...window.history.state };
        // Next bypasses its router update when either marker is supplied. Its
        // handler restores the current internal state while keeping custom data.
        delete state.__NA;
        delete state._N;
        window.history.replaceState(state, '', window.location.href);
      }
    });
    return () => { mounted = false; };
  }, []);
}
