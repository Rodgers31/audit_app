/**
 * Every suppression of `local/no-zero-fallback-on-published-figure` must carry
 * a reason.
 *
 * ESLint accepts a bare `// eslint-disable-next-line <rule>`; the ` -- reason`
 * suffix is optional and no rule validates it. So the sibling rule's stated
 * contract — "it becomes a decision someone wrote down" — was unenforced: a
 * developer could silence a published-figure zero with no explanation at all.
 *
 * This rule reads the directive comments themselves and requires a non-empty
 * reason after `--`.
 */
'use strict';

const TARGET = 'local/no-zero-fallback-on-published-figure';
// Rule names contain hyphens, so the reason can only be split on the ` -- `
// separator ESLint itself uses — not by treating `-` as a delimiter.
const DIRECTIVE = /^\s*eslint-disable(?:-next-line|-line)?\s+([\s\S]*)$/;

module.exports = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Require a written reason on every eslint-disable of the zero-fallback rule.',
    },
    schema: [],
    messages: {
      missingReason:
        'Suppressing {{rule}} requires a reason: write ' +
        '`// eslint-disable-next-line {{rule}} -- why a zero is correct here`. ' +
        'A silent suppression re-publishes the zero this rule exists to catch.',
    },
  },
  create(context) {
    const sourceCode = context.sourceCode || context.getSourceCode();
    return {
      Program() {
        for (const comment of sourceCode.getAllComments()) {
          const match = DIRECTIVE.exec(comment.value);
          if (!match) continue;
          if (!comment.value.includes(TARGET)) continue;
          const rest = match[1];
          const sep = rest.indexOf('--');
          const reason = sep >= 0 ? rest.slice(sep + 2).trim() : '';
          if (reason) continue;
          context.report({
            loc: comment.loc,
            messageId: 'missingReason',
            data: { rule: TARGET },
          });
        }
      },
    };
  },
};
