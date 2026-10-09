'use client';
import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useOperationsAccess } from '@/lib/admin/ingestionPolling';
import { createClient } from '@/lib/supabase/client';
import { dispatchHttpStatus } from '@/lib/admin/etlDispatch';
import api from '@/lib/api/axios';

const FAMILIES = ['etl-dispatch','etl-commands','etl-command'];
/** Every async continuation checks the originating authorized, visible lifetime. */
export function useEtlAccess() {
  const access = useOperationsAccess(FAMILIES);
  const { authUser } = useAuth();
  const qc = useQueryClient();
  const [, renderRevision] = useState(0);
  const mounted = useRef(false);
  const epoch = useRef(0);
  const denied = useRef(false);
  const controllers = useRef(new Set<AbortController>());
  const identity = useRef({actorId:access.actorId,isAdmin:access.isAdmin,authUser});
  if (identity.current.actorId !== access.actorId || identity.current.isAdmin !== access.isAdmin ||
      identity.current.authUser !== authUser) {
    ++epoch.current;
    denied.current = false;
    identity.current = {actorId:access.actorId,isAdmin:access.isAdmin,authUser};
  }
  const enabled = access.enabled && !denied.current;
  const live = useRef(enabled);
  live.current = enabled;
  const lifetime = epoch.current;
  useEffect(() => {
    mounted.current = true;
    const invalidate = (deny = false) => {
      ++epoch.current;
      if (deny) denied.current = true;
      live.current = false;
      controllers.current.forEach(controller=>controller.abort());
      controllers.current.clear();
      for (const family of FAMILIES) {
        void qc.cancelQueries({queryKey:['admin',family,access.actorId]});
        qc.removeQueries({queryKey:['admin',family,access.actorId]});
      }
      renderRevision(value=>value+1);
    };
    const visibility = () => invalidate();
    document.addEventListener('visibilitychange',visibility);
    // Same-actor renewal must invalidate deferred callbacks even if the SDK
    // reuses its User object. This subscriber never calls an auth request.
    const subscription = authUser ? createClient().auth.onAuthStateChange(() => invalidate()).data.subscription : undefined;
    return () => {
      mounted.current = false;
      controllers.current.forEach(controller=>controller.abort());
      controllers.current.clear();
      document.removeEventListener('visibilitychange',visibility);
      subscription?.unsubscribe();
      for (const family of FAMILIES) {
        void qc.cancelQueries({queryKey:['admin',family,access.actorId,lifetime]});
        qc.removeQueries({queryKey:['admin',family,access.actorId,lifetime]});
      }
    };
  },[access.actorId,access.isAdmin,authUser,qc]);
  const current = (ticket = lifetime) => mounted.current && live.current && ticket === epoch.current && document.visibilityState === 'visible';
  const rejectAccess = (error: unknown) => {
    if (!current()) return;
    if ([401,403].includes(dispatchHttpStatus(error) ?? 0)) {
      denied.current = true;
      live.current = false;
      ++epoch.current;
      controllers.current.forEach(controller=>controller.abort());
      for (const family of FAMILIES) {
        void qc.cancelQueries({queryKey:['admin',family,access.actorId]});
        qc.removeQueries({queryKey:['admin',family,access.actorId]});
      }
      renderRevision(value=>value+1);
    }
  };
  const read = async <T,>(path:string, signal:AbortSignal, parse:(raw:unknown)=>T, params?:Record<string,string|number>) => {
    if (!current()) throw new Error('Authorization lifetime ended.');
    try {
      const response = await api.get(path,{signal,params,headers:{'Cache-Control':'no-store'}});
      if (!current() || signal.aborted) throw new Error('Authorization lifetime ended.');
      return parse(response.data);
    } catch (error) { rejectAccess(error); throw error; }
  };
  const controller = () => { const value = new AbortController(); controllers.current.add(value); return value; };
  const release = (value:AbortController) => controllers.current.delete(value);
  return {...access,enabled,denied:denied.current,lifetime,current,read,rejectAccess,controller,release};
}
export type EtlAccess = ReturnType<typeof useEtlAccess>;
