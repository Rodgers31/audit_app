/** Reject messages from other origins, windows and OAuth attempts. */
export function receiveMetaCallback(event: Pick<MessageEvent, 'origin' | 'source' | 'data'>, origin: string, popup: Window | null, state: string | null): { code: string | null; denied: boolean } | null {
  if (!popup || !state || event.origin !== origin || event.source !== popup) return null;
  const v = event.data;
  if (!v || typeof v !== 'object' || Array.isArray(v) || v.type !== 'auditgava-meta-callback' || v.state !== state || typeof v.denied !== 'boolean' || Object.keys(v).some(k => !['type','code','state','denied'].includes(k))) return null;
  if (!v.denied && (typeof v.code !== 'string' || !v.code.length || v.code.length > 4096)) return null;
  return { code: v.denied ? null : v.code, denied: v.denied };
}

/** Direct callbacks carry a non-authorizing reference, never code/state. */
export function receiveDirectMetaCallback(event: Pick<MessageEvent, 'origin' | 'source' | 'data'>, origin: string, popup: Window | null, flowId: string): boolean {
  const v = event.data;
  return !!popup && event.origin === origin && event.source === popup && !!v && typeof v === 'object' && !Array.isArray(v)
    && Object.keys(v).length === 2 && v.type === 'auditgava-meta-ready' && v.flow_id === flowId;
}

export function launchDirectMeta(popupName: string, flow: { launch_url: string; launch_token: string; flow_id: string }) {
  const form = document.createElement('form');
  form.method = 'POST'; form.action = flow.launch_url; form.target = popupName;
  for (const [name, value] of Object.entries({ flow_id: flow.flow_id, launch_token: flow.launch_token })) {
    const input = document.createElement('input'); input.type = 'hidden'; input.name = name; input.value = value; form.appendChild(input);
  }
  document.body.appendChild(form);
  try { form.submit(); } finally { form.remove(); }
}
