import { screen, within } from '@testing-library/react';

export function revenueDetails(technical = true) {
  const trigger = screen.getByTestId('revenue-section-source');
  const id = trigger.getAttribute('aria-controls');
  const dialog = id ? document.getElementById(id) : null;
  if (!(dialog instanceof HTMLDialogElement)) throw new Error('Expected the tax revenue source dialog');
  // jsdom does not implement native modal interactions. Playwright exercises opening and focus return.
  dialog.open = true;
  if (technical) {
    const details = dialog.querySelector('details');
    if (details) details.open = true;
  }
  return dialog;
}

export function publishedObservation(name: string, period = 'FY 2025/26') {
  const release = within(revenueDetails()).getByRole('region', { name: period });
  const row = Array.from(release.querySelectorAll<HTMLElement>('[data-revenue-observation]'))
    .find(item => item.dataset.revenueObservation === name);
  if (!row) throw new Error(`Expected a source observation for ${name}`);
  return within(row);
}
