'use client';
import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAdmin } from '@/lib/auth/admin';
import { useAuth } from '@/lib/auth/AuthProvider';

/** Queries are actor-scoped, cancelled hidden and removed when this observer leaves. */
export function useOperationsAccess(families: string[]) {
  const {isAdmin,isLoading}=useAdmin();
  const {user}=useAuth();
  const actorId=user?.id ?? null;
  const qc=useQueryClient();
  const [visible,setVisible]=useState(false);
  const familyKey=families.join(',');
  useEffect(() => {
    const keys=familyKey.split(',');
    const update=() => {
      const shown=document.visibilityState === 'visible';
      setVisible(shown);
      if(!shown) for(const family of keys) void qc.cancelQueries({queryKey:['admin',family,actorId]});
    };
    update();
    document.addEventListener('visibilitychange',update);
    return () => {
      document.removeEventListener('visibilitychange',update);
      for(const family of keys) {
        void qc.cancelQueries({queryKey:['admin',family,actorId]});
        qc.removeQueries({queryKey:['admin',family,actorId]});
      }
    };
  },[actorId,familyKey,isAdmin,qc]);
  return {actorId,visible,isAdmin,isLoading,enabled:isAdmin && !!actorId && visible};
}
