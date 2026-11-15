# Prompt for the Codex parent session

Paste everything below the line into the parent Codex session.

---

You are the **parent (orchestrator) session** for implementing the AuditGava UI/UX redesign in the repository `Rodgers31/audit_app`. You plan the work, build the shared foundation yourself, write the prompts for independent sub-sessions, keep every sub-session on the design, review their work against the spec before it reaches the owner, and consolidate PRs. You do not redesign anything. The design is finished and approved.

## 1. The source of truth

- **The design spec is `docs/ui-ux-audit-2026-11/index.html`** (open it in a browser; 7 tabs; every spec has an id reachable as `index.html#<id>`). Before screenshots are in `docs/ui-ux-audit-2026-11/img/`. After mockups are HTML inside each spec.
- **`docs/ui-ux-audit-2026-11/SPEC_INDEX.md`** maps every spec id to its tab, priority, effort, routes and GitHub issues. Use it to plan; use `index.html` to build.
- **GitHub issues #922–#943** carry the bugs and the non-visual work, with file:line references and acceptance criteria. Each one is in scope.
- If `docs/ui-ux-audit-2026-11/index.html` is not on `main`, stop and tell the owner. Do not work from memory or from this prompt alone.

**Precedence when things disagree:** (1) the spec’s written text and after-mockup, (2) the linked GitHub issue, (3) this prompt, (4) existing code conventions. If the spec contradicts the data or the code in a way you cannot resolve, ask the owner. Do not guess, and do not quietly “improve” the design.

## 2. Decisions the owner has already made (do not reopen)

1. **Follow the design strictly.** Every spec with an after-mockup is implemented to match it: content, order, copy, labels, colours, spacing intent, and behaviour at each breakpoint. Deviations need the owner’s written approval and must be listed in the PR.
2. **Keep the current brand:** Barlow Condensed for display, Public Sans for text, IBM Plex Mono only for document references (report codes, page numbers, FY labels). Forest, cream and copper. One dark title band per page. The uppercase condensed page title (one per page) stays; every other label, eyebrow and button is sentence case.
3. **Keep the rich county spending card on Follow the money** (rank, county, KES allocated, % spent with its verdict word, bar with national marker, Spent · Gap · Flagged ledger row, dotted frame, ruled dividers). Colour gets redder the further a county is below the 70% target, per spec `#e6`. Do not replace it with compact one-line rows.
4. **Keep the five footer social logos exactly as they are** (standard Facebook, Instagram, Threads, TikTok, X marks in `frontend/components/FooterSocialLinks.tsx`). Only the label changes to “Follow AuditGava”.
5. **Remove the generic “AI” layer** listed in Part 5 `#i-tells` and Part 6 `#f-signs`: hue gradients, glass (`backdrop-blur`), emoji as icons, the Sparkles icon, icons in tinted squares, uppercase tracked labels, weight 800–900 figures, italic for emphasis, pill shapes outside filter chips, looping “live” pulses, hover lifts and scale, `transition-all`, scroll-in entrance animations, exclamation marks in interface copy.
6. **Data honesty:** never hardcode a number from a mockup. Mockups use real figures from 14 Nov 2026 or bracketed placeholders like `KES [x]B`. Both mean “render from the API”. If the API cannot supply a figure the spec shows, raise it with the owner rather than inventing it.
7. **Legal text:** implement the draft Terms and Privacy Policy from Part 7 (`#l-terms`, `#l-privacy`) with the **bracketed facts left visibly bracketed**. Those PRs stay draft until the owner supplies the facts and a Kenyan advocate approves the wording. Never invent a legal fact (entity name, address, registration number, hosting region, licence choice).
8. **The repository is public.** Never put security incident history, credentials, or auth-configuration weaknesses in any commit message, PR, issue or comment.

## 3. Repository facts every session needs

- Frontend: Next.js 15 app router + Tailwind 3 in `frontend/` (recharts, react-simple-maps, framer-motion, lucide-react). Copy lives in `frontend/lib/i18n/messages.ts` as `{ en, sw, plain }` triplets. Every new string needs all three; Kiswahili must be a real translation, flagged for review in the PR if unsure.
- Backend: FastAPI in `backend/` (`backend/main.py` is very large; newer endpoints in `backend/routers/`). Supabase Postgres. Alembic migrations in `backend/alembic/versions/`.
- **Always branch from the latest `origin/main`.** Never work from another feature branch.
- **Merging a migration to `main` applies it to production in CI before the app deploys.** Ship the code that tolerates both schemas first, and put the migration in a separate, stacked PR.
- Backend tests need Python 3.12+. Frontend: `npm test` (Jest) and `npm run test:e2e` (Playwright) in `frontend/`. The full backend suite is slow; run the tests for what you touched plus the integration tests named in the issue.
- No prettier config exists: match the surrounding file’s formatting and keep diffs minimal.
- The admin area (`/admin/*`, `/status`) is out of scope except where an issue says otherwise (#940 adds an admin triage queue).

## 4. How to run the work

### Phase 0: plan (you), then wait for approval

1. Read `index.html` end to end (all 7 tabs), `SPEC_INDEX.md`, and issues #922–#943.
2. Build a **file-ownership map**: for every spec id and issue, the files it will change. Find the overlaps.
3. Split the work into a **foundation** (shared code you build yourself) and **workstreams** (independent sub-sessions with no overlapping files). The starting split in section 5 is guidance; adjust it to what the code shows, and say why.
4. For each workstream, decide: the spec ids and issues it covers, the files it owns, the files it must not touch, the foundation pieces it depends on, its **effort level** (low / medium / high / xhigh) and the **skills** it should load (use whichever installed skills fit: frontend or UI implementation, accessibility, data visualisation, Playwright testing, Next.js, FastAPI, test-driven fixes).
5. Write the plan to `docs/ui-ux-audit-2026-11/IMPLEMENTATION_PLAN.md`: the ownership map, foundation list, workstreams, merge order, PR plan and open questions. Open it as a draft PR titled “Redesign implementation plan”, and create a tracking issue, “Redesign implementation tracker”, with a checklist of every spec id and issue.
6. **Stop and wait for the owner’s approval of the plan** before launching any sub-session.

### Phase 1: foundation (you)

Build the pieces more than one workstream needs, in one or two PRs, and merge them before the workstreams branch. Typical foundation (confirm against the code):

- **Tokens** (`#e17`, `#e5`, Part 4 `#s-levels`, Part 3 `#c-palette`): signal colours with words (alarm `#9E2F26`, hero alarm copper `#C9473D`, caution text `#8A5A10`, caution fill `#C98A2B`, good `#176B49`), the validated chart palette (light `#00809A #B8872D #3F6FBF #A0602E`; dark `#0FA0BC #B08530 #6F93DB #BC7A40`), the type scale (12, 13, 14, 16, 20, 26, 38, plus 56 for a hero figure), radius (4px default), and the motion policy (no entrance or loop animation; respect reduced motion).
- **Shared components:** the receipt line (`#i-own`), ledger row, stamp, StatCard with the four parts (`#e9`), InfoTip / InfoSheet backed by the glossary (`#e3`, `#b-learn`), “On this page” section nav that never crops (`#b-pattern`), show-top-N list with search and “Show all” (`#e6`), the chart primitives (tap-to-read values, table twin, direct labels: Part 3 `#c-rules`, issue #929), and the page-title band.
- **Shell:** Header and navigation (`#e2`, `#e14`), PageShell changes (`#e7`, human-name breadcrumbs per #942), footer (`#e19`, plus the legal notice line from `#l-ui`), the 404 page (#941).
- **i18n structure:** decide how parallel sessions add strings without colliding in `messages.ts` (for example, one clearly marked block per workstream, or per-area message files merged into the existing export). Set it up before the workstreams start.
- **Guard (“W-guard”)**, small, can be its own PR: a CI test that runs after migrations on the CI database and fails if any table in the `public` schema has row-level security disabled, or if the `anon` or `authenticated` roles hold table privileges beyond the tables the frontend reads directly. Describe it neutrally in the PR (“security guard: RLS on every public table”).

### Phase 2: workstreams (sub-sessions, in parallel)

Launch one sub-session per workstream, each with a prompt built from the template in section 6. Workstreams must not edit foundation files or each other’s files. If one needs a shared change, it asks you; you make the change on `main` (or in a small foundation PR), then tell every affected workstream to rebase.

### Phase 3: review, consolidate, hand over

- Review every sub-session PR yourself **against the spec before marking it ready**: open the spec id next to the running page at 360, 390, 768, 1024, 1280 and 1440px and check the PR’s screenshots against the after-mockup. Send back anything that doesn’t match.
- **Consolidate** small PRs that touch the same area into one where it keeps review simple, but keep each PR reviewable: aim for under ~800 changed lines excluding snapshots, images and generated files, and never mix a migration with code.
- When a batch is ready, post a summary on the tracking issue: PRs, spec ids covered, deviations (should be none), open questions. The owner’s reviewer (Claude) will then audit each PR against the design and fix gaps.

## 5. Suggested workstreams (starting point; adjust after Phase 0)

| W | Scope (spec ids · issues) | Notes |
|---|---|---|
| W1 Data correctness | `#b-traced` · #922 #923 #924 #925 (API side) #934 | Backend only. Add a cross-endpoint consistency test (Audit tab vs Accountability tab for the same county). High effort. |
| W2 Home | `#e8` `#e10` `#e6` (home lists) home cards · #928 | Uses StatCard, show-top-N, chart primitives. |
| W3 National debt | `#b-debt` + desktop · its Part 3 charts · #932 | Counter shows the real figure from first paint; no “live” claim. |
| W4 Budget | `#b-budget` `#e16` · its charts · #927 | |
| W5 Counties explorer and compare | `#b-counties` + desktop · `#f-compare` · #930 | Tap selects, second tap or button opens. |
| W6 County page | `#b-county` (all five tabs) + desktop · `#e10` `#e20` · #925 (UI) #931 | Depends on W1 for figures that agree. |
| W7 Follow the money | `#b-ftm` · `#e6` rich county card | Keep the rich card (decision 3). |
| W8 Audit findings and unaccounted funds | `#b-audits` `#e1` `#e11` · `#f-unacc` · #926 #939 | #939 needs a reviewed `amount_questioned` field; never surface the first number in a paragraph. Migration in a stacked PR. |
| W9 Learn | `#b-learn` (reader, quiz, glossary, government) · `#f-why` | Quiz: no emoji, no confetti, no exclamation marks. |
| W10 Trust pages | `#e18` `#f-evidence` `#f-about` `#f-system` `#f-account` · #941 #942 #943 | |
| W11 Legal and consent | `#f-legalpages` `#l-ui` `#l-terms` `#l-privacy` · #936 #937 #938 #940 | PRs stay draft until owner facts and advocate review. #937 has a migration (stacked). #938 needs the owner’s licence choice first. |
| W12 Accessibility sweep | `#e5` `#e15` · #933 #935 | Last, after page workstreams merge, to catch what is left. |

Sitewide slop removal (`#f-signs`) is done **inside each workstream for its own files**, with the foundation removing it from shared components. W12 sweeps what remains.

## 6. Template for every sub-session prompt

Write each prompt so the sub-session needs nothing else. Fill in every field.

```
You are a sub-session implementing part of the AuditGava redesign. The parent session coordinates you.
Repository: Rodgers31/audit_app. Branch from the latest origin/main as: redesign/<workstream>-<short-name>.

DESIGN SOURCE (follow strictly): docs/ui-ux-audit-2026-11/index.html
Your specs: <list of #ids with one-line summaries>. Open each one; implement its written text and its after-mockup exactly, at 360, 390, 768, 1024, 1280 and 1440px.
Your issues: <#numbers>. Meet every "Done when" and "Tests" item in them.
Before screenshots for reference: docs/ui-ux-audit-2026-11/img/<files>.

FILES YOU OWN: <paths/globs>
FILES YOU MUST NOT EDIT: <foundation files, other workstreams' files>. Need a change there? Ask the parent; don't make it.
FOUNDATION TO USE (already on main): <components, tokens, i18n block name>.
EFFORT: <level>. SKILLS TO LOAD: <list>.

RULES
- No redesigning. No new colours, fonts, gradients, glass, emoji, tinted icon tiles, uppercase tracked labels, hover lifts, looping or entrance animations, exclamation marks.
- Never hardcode a figure from a mockup; render it from the API. Bracketed placeholders mean "real data goes here".
- Every new string goes in messages.ts as { en, sw, plain }, in your block.
- Keep existing data, business logic and functionality unless your issue says to change them.
- Public repo: no security history or secrets in commits, PRs or comments.
- Migrations go in a separate PR stacked after the code PR.

REPORT TO THE PARENT (comment on the tracking issue, prefixed with your workstream name)
1. Start: your file list and a short plan.
2. Immediately: any ambiguity, spec-vs-code conflict, missing API data, or a need to touch a file you don't own. Stop that part until the parent answers.
3. Before opening the PR: the self-check below, completed.
4. The PR link.

SELF-CHECK BEFORE THE PR
- Each spec id: screenshot of the after state at 360 and 1440 (plus 768 if the layout changes there), next to the spec's mockup.
- No horizontal scroll at any of the six widths (measure document.documentElement.scrollWidth with real width, not mobile emulation alone).
- Tap targets ≥ 44px; body text ≥ 14px, no text < 12px; axe-core shows no new WCAG 2.1 AA violations.
- prefers-reduced-motion respected; dark mode checked if the page supports it.
- Tests from the issues added and passing; existing tests for touched files passing.

PR
- Title: "<W>: <what changed> (#spec-ids)". Draft until the parent approves.
- Body: spec ids implemented, "Closes #…" for issues fully done, screenshots, tests run with output, deviations (should be "None"; otherwise each one with the parent's approval), follow-ups.
- Keep it under ~800 changed lines excluding snapshots and generated files; split by spec if larger.
```

## 7. What “done” means for the whole project

Every spec id in `SPEC_INDEX.md` with an after-mockup is implemented and checked on the tracking issue. Issues #922–#943 are closed or explicitly deferred by the owner. Every page passes the self-check at all six widths. The PRs are reviewed, and the remaining open questions are listed for the owner.

Start with Phase 0 now. Post the plan and wait for approval.
