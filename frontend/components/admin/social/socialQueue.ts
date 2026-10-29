/** Public URL state for the private review queue; never accepts a return origin. */
export type QueueView = 'drafts' | 'pending' | 'scheduled' | 'history' | 'needs_attention' | 'archived';
export interface QueueSelection { view: QueueView; page: number; origin: string; category: string }
export const queueDefaults: QueueSelection = {view:'pending',page:1,origin:'',category:''};
const views = new Set<QueueView>(['drafts','pending','scheduled','history','needs_attention','archived']);
const topics = new Set(['dataset_availability','new_report','debt_update','budget_update','audit_finding','correction']);
export function readQueueSelection(query: string): QueueSelection {
  const params=new URLSearchParams(query),view=params.get('view'),page=params.get('page')??'1',origin=params.get('origin')??'',category=params.get('topic')??'';
  return {view:views.has(view as QueueView)?view as QueueView:'pending',page:/^[1-9]\d{0,5}$/.test(page)?Number(page):1,origin:['manual','generated'].includes(origin)?origin:'',category:topics.has(category)?category:''};
}
export function queueQuery(selection: QueueSelection): string {
  const safe=readQueueSelection(new URLSearchParams({view:selection.view,page:String(selection.page),origin:selection.origin,topic:selection.category}).toString());
  const params=new URLSearchParams();
  if(safe.view!=='pending')params.set('view',safe.view);
  if(safe.page!==1)params.set('page',String(safe.page));
  if(safe.origin)params.set('origin',safe.origin);
  if(safe.category)params.set('topic',safe.category);
  return params.toString();
}
export function queueReturnHref(raw: string | null): string { const query=queueQuery(readQueueSelection(raw??''));return '/admin/social'+(query?'?'+query:''); }
