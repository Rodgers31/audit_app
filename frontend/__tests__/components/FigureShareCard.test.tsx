import FigureShareCard from '@/components/sharing/FigureShareCard';
import { preparePublicFigure, type PublicFigureShareInput } from '@/lib/sharing/figureShare';
import { createPublicFigurePng } from '@/lib/sharing/figureShareImage';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

jest.mock('@/lib/i18n/LangProvider', () => ({ useLang: () => ({ lang: 'en' }) }));
jest.mock('@/lib/sharing/figureShareImage', () => ({ createPublicFigurePng: jest.fn() }));

const observation: PublicFigureShareInput = {
  visibility: 'public',
  metric: 'Synthetic county budget spent',
  value: '0.00%',
  source: { publisher: 'Synthetic public office', period: 'FY2025/26', url: 'https://example.org/report.pdf#page=7' },
};
const share = jest.fn();
const canShare = jest.fn();
const createUrl = jest.fn();
const revokeUrl = jest.fn();

beforeEach(() => {
  jest.resetAllMocks();
  jest.mocked(createPublicFigurePng).mockResolvedValue(new Blob(['test image'], { type: 'image/png' }));
  share.mockResolvedValue(undefined);
  canShare.mockReturnValue(true);
  Object.defineProperty(navigator, 'share', { configurable: true, value: share });
  Object.defineProperty(navigator, 'canShare', { configurable: true, value: canShare });
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createUrl });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeUrl });
  createUrl.mockReturnValueOnce('blob:figure-first').mockReturnValueOnce('blob:figure-next');
});

test.each([
  'javascript:alert(1)',
  'https://example.org@127.0.0.1/report.pdf',
  'https://viewer:example@example.org/report.pdf',
  'https://127.0.0.1/report.pdf',
  'https://source.local/report.pdf',
])('rejects a report URL outside the public link contract (%s)', url => {
  expect(preparePublicFigure({ ...observation, source: { ...observation.source!, url } }))
    .toEqual({ status: 'invalidSource' });
});

test('identifies missing source and metric without blocking a published zero figure', () => {
  expect(preparePublicFigure({ ...observation, source: null })).toEqual({ status: 'missingSource' });
  expect(preparePublicFigure({ ...observation, value: null })).toEqual({ status: 'missingFigure' });
  expect(preparePublicFigure(observation)).toMatchObject({
    status: 'ready',
    figure: { metric: 'Synthetic county budget spent', value: '0.00%', period: 'FY2025/26', publisher: 'Synthetic public office' },
  });
});

test('prepares a sourced file without sharing until the Share action', async () => {
  render(<FigureShareCard figure={observation} />);
  expect(screen.getByText('0.00%')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Synthetic public office · FY2025/26' }))
    .toHaveAttribute('href', observation.source!.url);
  expect(screen.getByText(/auditgava\.com/)).toBeVisible();
  expect(createPublicFigurePng).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Prepare image' }));
  const download = await screen.findByRole('link', { name: 'Download image' });
  expect(download).toHaveAttribute('href', 'blob:figure-first');
  expect(download).toHaveAttribute('download', 'auditgava-figure.png');
  expect(share).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Share image' }));
  await waitFor(() => expect(share).toHaveBeenCalledWith({
    files: [expect.objectContaining({ name: 'auditgava-figure.png', type: 'image/png' })],
  }));
});

test('releases every obsolete download URL across preparation, new data and unmount', async () => {
  canShare.mockReturnValue(false);
  createUrl.mockReturnValueOnce('blob:figure-changed');
  const { rerender, unmount } = render(<FigureShareCard figure={observation} />);
  fireEvent.click(screen.getByRole('button', { name: 'Prepare image' }));
  await screen.findByRole('link', { name: 'Download image' });
  expect(screen.queryByRole('button', { name: 'Share image' })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Prepare again' }));
  const replacement = await screen.findByRole('link', { name: 'Download image' });
  expect(replacement).toHaveAttribute('href', 'blob:figure-next');
  expect(revokeUrl).toHaveBeenCalledWith('blob:figure-first');

  rerender(<FigureShareCard figure={{ ...observation, value: '0.01%' }} />);
  expect(revokeUrl).toHaveBeenCalledWith('blob:figure-next');
  expect(screen.queryByRole('link', { name: 'Download image' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Prepare image' }));
  await screen.findByRole('link', { name: 'Download image' });
  unmount();
  expect(revokeUrl.mock.calls).toEqual([
    ['blob:figure-first'], ['blob:figure-next'], ['blob:figure-changed'],
  ]);
});

test('keeps the download accessible if the native share action fails', async () => {
  share.mockRejectedValueOnce(new Error('Share menu unavailable'));
  render(<FigureShareCard figure={observation} />);
  fireEvent.click(screen.getByRole('button', { name: 'Prepare image' }));
  const download = await screen.findByRole('link', { name: 'Download image' });
  fireEvent.click(screen.getByRole('button', { name: 'Share image' }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Could not open file sharing.'));
  expect(download).toHaveAttribute('href', 'blob:figure-first');
});
