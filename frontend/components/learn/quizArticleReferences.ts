// Only explanations checked against the published text get an article link.
export const quizArticleReferences = new Map<string, { article: number; clause?: string }>([
  ['const-5', { article: 2, clause: '(1)' }],
  ['const-6', { article: 1, clause: '(1)' }],
  ['gov-2', { article: 97, clause: '(1)' }],
  ['gov-3', { article: 98, clause: '(1)' }],
  ['gov-5', { article: 152, clause: '(1)(d)' }],
  ['dev-1', { article: 6, clause: '(1)' }],
  ['dev-3', { article: 216, clause: '(1)(a)' }],
  ['dev-6', { article: 179, clause: '(2)' }],
  ['fin-2', { article: 228, clause: '(4)–(5)' }],
  ['fin-5', { article: 229, clause: '(4), (7)' }],
  ['fin-6', { article: 206, clause: '(1)' }],
  ['rights-1', { article: 35, clause: '(1)' }],
  ['rights-4', { article: 33, clause: '(1)' }],
  ['rights-5', { article: 25 }],
  ['rights-6', { article: 43, clause: '(1)' }],
]);
