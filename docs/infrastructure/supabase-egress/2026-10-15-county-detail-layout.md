# County detail loading stability

The streamed `/counties/[id]` fallback omitted the back-link and eyebrow rows.
Its title appeared at y=100 rather than the loaded title's y=196.5 in the
observed Chrome viewport. Query loading used a third, spinner-only layout.
Late accountability also changed the width and height of the grade group.

Both loading paths now use one data-free county skeleton with the same header
rows and responsive metric/tab structure. The grade group reserves its width
and minimum height. Empty demographic and fiscal-year rows retain their space;
an unsourced fiscal year remains empty and hidden. Narrow screens reserve two
title lines for long county names. No financial values or grades are inferred.

Verification:

- Three regression cases failed on accepted source `ba89a7f` (both loading
  paths and an absent fiscal-year row); the final four-case fixture passes.
- All 175 county Jest cases and the production Next.js build pass.
- Independent React review executed 13 and 10 additional cases, including
  English/Swahili/plain labels, zero/missing facts, delayed accountability,
  errors and navigation. Its missing-year finding was reproduced and fixed.
- Logged-in Chrome exercised the real local Next.js app and real backend
  readers against disposable SQLite, with four-second comprehensive and
  seven-second accountability delays. A 355 CSS-pixel long-name navigation
  retained the title's position and reduced the following metric-row movement
  from roughly 37 pixels to less than one pixel, without horizontal overflow.

The Chrome geometry receipt is a bounded local observation, not a field p75
CLS result. Production deployment and repeated field/long-session observations
remain release acceptance. The historical county list and budget metrics remain
separate; social publishing, worker, storage and billing settings are untouched.
