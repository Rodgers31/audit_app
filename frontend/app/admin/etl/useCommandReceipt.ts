'use client';
import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { activeCommand, commandProgress, parseCommand, validCommandId, type EtlCommand } from '@/lib/admin/etlDispatch';
import type { EtlAccess } from './useEtlAccess';

export function useCommandReceipt(access:EtlAccess, commandId:string, accepted?:EtlCommand) {
  const scope=JSON.stringify([access.lifetime,commandId]);
  const previous=useRef<{scope:string;command?:EtlCommand}>({scope,command:accepted});
  if(previous.current.scope!==scope) previous.current={scope,command:accepted};
  return useQuery({
    queryKey:['admin','etl-command',access.actorId,access.lifetime,commandId],
    enabled:access.enabled && validCommandId(commandId),gcTime:0,retry:false,staleTime:0,refetchOnWindowFocus:false,
    initialData:accepted,
    queryFn:({signal})=>access.read('/admin/etl/commands/'+commandId,signal,raw=>{
      const command=commandProgress(parseCommand(raw,commandId),previous.current.command);
      previous.current.command=command;
      return command;
    }),
    refetchInterval:query=>access.enabled && !query.state.error && query.state.data && activeCommand(query.state.data) ? 5000 : false,
  });
}
