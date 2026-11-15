# AuditGava UI/UX redesign: spec index

Generated from `index.html` in this folder. **`index.html` is the design spec; this file is only a map of it.** Open it in a browser (`open docs/ui-ux-audit-2026-11/index.html`); it has 7 tabs and every spec below is reachable as `index.html#<id>`. Before screenshots are in `img/`; after mockups are HTML inside each spec.

Priority: P0 highest. Effort: S/M/L as estimated in the spec. "BA" = has before/after mockups.


## 1 Foundations

| id | Spec | P | Effort | Where | Issues | BA |
|---|---|---|---|---|---|---|
| `#e1` | E1 · The audit findings page scrolls sideways, and the menu goes off-screen | P0 | S | /audits · Bug |  | yes |
| `#e2` | E2 · On phones the header has no name, and the logo looks like a menu button | P0 | S | Shared · Navigation |  | yes |
| `#e3` | E3 · Put sources one tap down instead of printing them under every figure | P0 | M | Shared · FigureEvidence + 14 importers · Home · Budget · Debt · Counties |  | yes |
| `#e4` | E4 · Interactions and instructions that only work with a mouse | P0 | S–M | Home map · Budget · Debt · Loans |  | yes |
| `#e5` | E5 · Text too small, and contrast below AA | P0 | M (mechanical) | Site-wide · tokens |  | yes |
| `#e6` | E6 · Long lists printed in full | P0 | M | Home · Follow the money · Counties |  | yes |
| `#e7` | E7 · The page header takes the whole first screen | P1 | S | Shared · PageShell (most inner pages) |  | yes |
| `#e8` | E8 · Home: ask what the reader wants to know | P1 | M | Home |  | yes |
| `#e9` | E9 · Give every headline number the same four parts | P1 | M | Shared · new StatCard · All data pages |  | yes |
| `#e10` | E10 · One county report card instead of five different scores | P1 | M | Home county panel · /counties · /counties/[id] |  | yes |
| `#e11` | E11 · Audit findings on phones: cards instead of a 9-column table | P1 | M | /audits |  | yes |
| `#e12` | E12 · Say each caveat once, and say what “freshness” actually knows | P1 | S | Home · /counties · /counties/[id] · Budget · Debt · Audits |  | yes |
| `#e13` | E13 · Charts on phones: one idea per chart, readable numbers | P1 | M | Home · Budget · Debt · Audits charts |  | yes |
| `#e14` | E14 · Navigation: put Audit findings in the menu, and group the drawer | P1 | M | Shared · Navigation drawer + desktop nav |  | yes |
| `#e15` | E15 · Touch targets under 44px | P1 | S | Site-wide |  | yes |
| `#e16` | E16 · Content clipped inside budget cards at 360px | P1 | S | /budget |  | yes |
| `#e17` | E17 · Consolidate the design system the pages already imply | P2 | L | Design system |  | yes |
| `#e18` | E18 · Separate the citizen’s source list from the data-health dashboard | P2 | M | /sources |  | yes |
| `#e19` | E19 · The footer is 1.2 phone screens | P2 | S | Shared · Footer + Newsletter |  | yes |
| `#e20` | E20 · County page tabs: sticky, and real tabs for screen readers | P2 | S | /counties/[id] |  | yes |
| `#e21` | E21 · Make Kiswahili and Plain English easy to find | P2 | S | Shared · LangSwitcher |  | yes |
| `#e22` | E22 · Remove unused UI components before the redesign work starts | P2 | S | Codebase hygiene |  | yes |

## 2 Page blueprints

| id | Spec | P | Effort | Where | Issues | BA |
|---|---|---|---|---|---|---|
| `#b-pattern` | Section navigation that never crops | P0 | S | Shared · replaces the chip row in E7 |  | yes |
| `#b-debt` | National debt: one story in six steps | P1 | M–L | /debt · 16 phone screens today |  | yes |
| `#b-counties` | County Explorer: pick a measure, see the ranking, find your county | P1 | M | /counties · 11 phone screens today |  | yes |
| `#b-county` | A county’s page: header once, sticky tabs, and each tab answering one question | P0 | L | /counties/[id] · all five tabs |  | yes |
| `#b-traced` | County figures that disagree, traced to their cause | P0 |  | Data + code, not design · /counties/[id] · traced on Baringo, 14 Nov 2026 |  | yes |
| `#b-ftm` | Follow the money: the national flow, then the 47 counties on one screen | P1 | M | /transparency · 20.4 phone screens today |  | yes |
| `#b-budget` | Budget: keep the flow, cut the duplicates, make revenue readable | P1 | M | /budget · 12.2 phone screens today |  | yes |
| `#b-audits` | Audit findings: the national picture before the list | P1 | M | /audits · extends E1 and E11 |  | yes |
| `#b-learn` | Learn: from a tidy library to a working companion for the rest of the site | P1 | M–L | /learn · Constitution · quiz · glossary · government |  | yes |

## 3 Charts

| id | Spec | P | Effort | Where | Issues | BA |
|---|---|---|---|---|---|---|
| `#c-rules` | Ten rules for every chart on AuditGava |  |  |  |  |  |
| `#c-phone` | How a chart behaves on a 360px phone |  |  |  |  |  |
| `#c-desk` | …and on desktop |  |  |  |  |  |
| `#c-palette` | Chart colours: four identity colours, validated |  |  |  |  |  |
| `#c-gallery` | The new charts, drawn to scale from the site’s own figures |  |  |  |  |  |
| `#c-audit` | Audit of every chart the site renders |  |  |  |  |  |

## 4 Signal colours

| id | Spec | P | Effort | Where | Issues | BA |
|---|---|---|---|---|---|---|
| `#s-levels` | Four levels, each with a word |  |  |  |  |  |
| `#s-rule` | The rule that keeps red meaningful |  |  |  |  |  |
| `#s-figures` | Every alarming figure, rated |  |  |  |  |  |
| `#s-anatomy` | What a signal looks like |  |  |  |  | yes |

## 5 Look & feel

| id | Spec | P | Effort | Where | Issues | BA |
|---|---|---|---|---|---|---|
| `#i-tells` | Generic tells in the live code |  |  |  |  |  |
| `#i-own` | What makes it look like AuditGava |  |  |  |  | yes |
| `#i-figures` | One face for figures |  |  |  |  |  |
| `#i-motion` | Motion: only when something changes |  |  |  |  |  |
| `#i-desktop` | Desktop layout system |  |  |  |  |  |
| `#i-onestop` | Making it the one place for audit |  |  |  |  |  |

## 6 Final pass

| id | Spec | P | Effort | Where | Issues | BA |
|---|---|---|---|---|---|---|
| `#f-scope` | What this pass checked |  |  |  | #926 #936 #937 #938 #939 #940 #941 #942 #943 |  |
| `#f-direction` | Unslop direction |  |  |  |  |  |
| `#f-signs` | Slop signs still on the site | P1 | M | Sitewide | #934 |  |
| `#f-matrix` | Every page, every screen |  |  |  | #929 |  |
| `#f-about` | About: say what AuditGava does, not what it believes | P2 | S | /about |  | yes |
| `#f-why` | Why this matters: AuditGava’s own figures, not a listicle | P2 | M | /learn/why-it-matters | #935 | yes |
| `#f-compare` | Compare counties: pick first, read a table that fits a phone | P2 | M | /counties/compare |  | yes |
| `#f-unacc` | Unaccounted funds: show the amounts, name the source plainly, fit the list | P1 | M | /accountability/unaccounted-funds · #939 | #939 | yes |
| `#f-evidence` | Figure evidence: a receipt a citizen can read | P2 | S | /sources/figures/[table]/[id] | #942 | yes |
| `#f-system` | System pages: one look, a way back, plain words | P2 | S | 404 · /reset-password · /newsletter/unsubscribe · #941 | #941 | yes |
| `#f-account` | Account: plain settings, and deletion that matches the policy | P3 | S | /account (signed in) · #943 | #943 | yes |
| `#f-legalpages` | Privacy and Terms pages: a summary first, contents, then the text | P1 | S | /privacy · /terms · #936 | #936 | yes |
| `#f-social` | Footer social logos: keep them exactly as they are |  |  |  |  | yes |

## 7 Legal & privacy

| id | Spec | P | Effort | Where | Issues | BA |
|---|---|---|---|---|---|---|
| `#l-read` | Read this first |  |  |  |  |  |
| `#l-map` | What the site actually does with personal data |  |  |  |  |  |
| `#l-gaps` | Where the policies don’t match the app | P0 | S | /privacy · /terms · #936 | #936 |  |
| `#l-laws` | Laws that apply, and what each one asks of AuditGava |  |  |  | #933 |  |
| `#l-risks` | Who could come after us, and what protects the site |  |  |  | #922 #924 #932 |  |
| `#l-ui` | Consent and notices in the interface | P0 | S | Newsletter · sign-up · footer · About · #937 · #940 | #937 #940 | yes |
| `#l-terms` | Draft Terms of Use |  |  |  |  |  |
| `#l-privacy` | Draft Privacy Policy |  |  |  |  |  |
| `#l-decide` | Decisions only you can make |  |  |  | #938 |  |

## GitHub issues referenced by the spec

Spec ↔ issue map (earlier specs predate the issues, so their rows above show no issue):
- `#e1`, `#b-audits` → #926 · `#e16`, `#b-budget` → #927 · `#e6` (loans card) → #928 · `#e4`, `#e13`, `#c-rules` → #929 · `#b-counties` → #930
- `#b-county` → #925 (Audit tab cap), #931 (chip wrap) · `#b-debt` → #932 · `#e5` → #933 · `#e12` → #934 · `#b-traced` → #922 #923 #924 · various small items → #935

- Data and correctness: #922 #923 #924 #925 #934
- Layout and interaction bugs: #926 #927 #928 #929 #930 #931 #932 #933 #935
- Round five: #936 (policies) #937 (consent, double opt-in) #938 (licence) #939 (unaccounted funds) #940 (corrections, right of reply) #941 (404, unsubscribe) #942 (titles, sitemap, breadcrumbs) #943 (data export)
