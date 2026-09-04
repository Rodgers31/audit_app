/**
 * Forbid `?? 0` / `|| 0` on a field that carries a published figure.
 *
 * The single most repeated defect in the pre-launch credibility audit. The ETL
 * correctly withholds a figure it cannot source; a component then writes
 * `data.tax_revenue ?? 0` and the page states that Kenya collected no tax.
 * Nine separate findings came from this one line shape:
 *
 *   BudgetFlowHero      tax/non-tax/borrowing/debt-service -> "KES 0B · 0.0%"
 *   DebtPageClient      debt_service_to_revenue -> "0.0%", below every peer
 *   AuditsPageClient    irregular expenditure -> "KES 0"
 *   TransparencyPage    Flagged -> "KES 0 - No flagged findings"
 *   DebtPageClient      gdpRatio -> risk band "Low"
 *
 * A zero and an absence are different claims. This rule cannot tell them apart
 * by itself, so it keys on the FIELD NAME: the money and ratio fields the API
 * declares nullable. Sorting comparators, reducers and array indices are not
 * matched, because those are not published figures.
 *
 * Escape hatch: if a zero really is correct for a field, say so at the call
 * site with `// eslint-disable-next-line local/no-zero-fallback-on-published-figure`
 * and a reason. The point is that it becomes a decision someone wrote down.
 */
'use strict';

const PUBLISHED_FIELD = /(^|_)(amount|amounts|budget|revenue|spending|spend|spent|allocated|allocation|borrowing|debt|debt_service|cost|ratio|rate|pct|percentage|share|total|count|findings|flagged|questioned|outstanding|principal|population|gdp)($|_)/i;

// Names that are plainly aggregations or comparisons rather than a figure.
const ALLOWED_CONTEXT = /^(sum|acc|accumulator|prev|idx|index|len|length|i|n)$/i;

// Private internals (`__retryCount`, `_cache`) are machinery, not something a
// reader ever sees. Widening the matcher to camelCase pulled these in.
const PRIVATE_INTERNAL = /^_/;

/**
 * camelCase -> snake_case, so one pattern covers both naming conventions.
 *
 * The matcher keys on `_`-delimited word boundaries, which meant it saw the
 * API's snake_case fields but not the frontend model's camelCase ones:
 * `county.budgetUtilization ?? 0` and `totalDebt ?? 0` are the same defect and
 * were passing the gate.
 */
function normaliseFieldName(name) {
  return name
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1_$2')
    .toLowerCase();
}

function fieldNameOf(node) {
  // a?.b?.c  ->  "c";  a.b  ->  "b";  bare identifier -> its name
  let n = node;
  while (n && (n.type === 'TSNonNullExpression' || n.type === 'ChainExpression')) {
    n = n.expression;
  }
  if (!n) return null;
  if (n.type === 'MemberExpression' && n.property) {
    if (n.property.type === 'Identifier') return n.property.name;
    if (n.property.type === 'Literal' && typeof n.property.value === 'string') {
      return n.property.value;
    }
    return null;
  }
  if (n.type === 'Identifier') return n.name;
  return null;
}

module.exports = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow defaulting a nullable published figure to 0; render an em dash instead.',
    },
    schema: [],
    messages: {
      zeroFallback:
        "`{{name}} {{op}} 0` publishes a zero where the API withheld a figure. " +
        'A zero is a claim: "the Auditor-General questioned nothing", "Kenya ' +
        'collected no tax". Render "—" and say why it is absent, or add an ' +
        'eslint-disable with the reason a zero is correct here.',
    },
  },
  create(context) {
    return {
      LogicalExpression(node) {
        if (node.operator !== '??' && node.operator !== '||') return;
        if (node.right.type !== 'Literal' || node.right.value !== 0) return;
        const name = fieldNameOf(node.left);
        if (!name) return;
        if (ALLOWED_CONTEXT.test(name)) return;
        if (PRIVATE_INTERNAL.test(name)) return;
        if (!PUBLISHED_FIELD.test(normaliseFieldName(name))) return;
        context.report({
          node,
          messageId: 'zeroFallback',
          data: { name, op: node.operator },
        });
      },
    };
  },
};
