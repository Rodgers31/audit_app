import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SocialMedia from '@/components/admin/social/SocialMedia';
import MediaUpload from '@/components/admin/social/media/MediaUpload';
import api from '@/lib/api/axios';
import { decodeMediaAsset, decodeMediaCapabilities, MediaCapabilities, MediaMime } from '@/lib/api/socialMedia';

jest.mock('@/lib/api/axios', () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock('@/lib/auth/admin', () => ({ useAdmin: () => ({ isAdmin: true }) }));
jest.mock('@/lib/auth/AuthProvider', () => ({ useAuth: () => ({ user: { id: '00000000-0000-4000-8000-000000000001' } }) }));
const get = api.get as jest.Mock, post = api.post as jest.Mock;
function capabilities(allowed: MediaMime[], reason: string | null = null): MediaCapabilities {
  return { upload_available: allowed.length > 0, library_available: true, allowed_mime_types: allowed, max_image_bytes: 10485760, max_video_bytes: 52428800, unavailable_reason: reason };
}
function mount(tree: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{tree}</QueryClientProvider>);
}
function upload(data: MediaCapabilities) {
  return <MediaUpload capabilities={data} contextKey='Master' onSelect={jest.fn()} onClose={jest.fn()} onBusy={jest.fn()} />;
}
beforeEach(() => jest.clearAllMocks());

test.each([
  { allowed: ['image/jpeg', 'image/png', 'video/mp4'], image: 'JPEG/PNG', video: true },
  { allowed: ['image/jpeg', 'image/png'], image: 'JPEG/PNG', video: false },
  { allowed: ['image/jpeg'], image: 'JPEG', video: false },
  { allowed: ['image/png'], image: 'PNG', video: false },
  { allowed: ['video/mp4'], image: null, video: true },
] as { allowed: MediaMime[]; image: string | null; video: boolean }[])('upload instructions follow advertised formats: $allowed', ({ allowed, image, video }) => {
  mount(upload(capabilities(allowed)));
  const instructions = screen.getByText(/Files are checked before they can be selected/);
  if (image) expect(instructions).toHaveTextContent(`${image} up to 10 MiB.`);
  else expect(instructions).toHaveTextContent('Image inspection is unavailable.');
  if (!allowed.includes('image/jpeg')) expect(instructions).not.toHaveTextContent('JPEG');
  if (!allowed.includes('image/png')) expect(instructions).not.toHaveTextContent('PNG');
  if (video) expect(instructions).toHaveTextContent('H.264 MP4 with optional AAC up to 50 MiB and 120 seconds.');
  else {
    expect(instructions).toHaveTextContent('Video inspection is unavailable.');
    expect(instructions).not.toHaveTextContent('H.264 MP4');
  }
  expect(screen.getByLabelText('Media file')).toHaveAttribute('accept', allowed.join(','));
});

test('an open panel stops advertising and accepting uploads when capability disappears', () => {
  const qc = new QueryClient(), wrap = (data: MediaCapabilities) => <QueryClientProvider client={qc}>{upload(data)}</QueryClientProvider>;
  const view = render(wrap(capabilities(['image/png'])));
  fireEvent.change(screen.getByLabelText('Media file'), { target: { files: [new File(['png'], 'proof.png', { type: 'image/png' })] } });
  expect(screen.getByRole('button', { name: 'Upload and inspect' })).toBeEnabled();
  view.rerender(wrap(capabilities([], 'Required media inspectors are unavailable.')));
  expect(screen.getByText('Required media inspectors are unavailable.')).toBeInTheDocument();
  expect(screen.queryByText(/JPEG|PNG|H\.264 MP4/)).not.toBeInTheDocument();
  expect(screen.getByLabelText('Media file')).toBeDisabled();
  expect(screen.getByLabelText('Default media alt text')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Upload and inspect' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Upload and inspect' }));
  expect(post).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: 'Close upload' })).toBeEnabled();
});

test('unavailable uploads have a fallback explanation', () => {
  mount(upload(capabilities([])));
  expect(screen.getByText('Private media uploads are unavailable.')).toBeInTheDocument();
  expect(screen.getByLabelText('Media file')).toBeDisabled();
});

test.each([...Array.from({ length: 32 }, (_, i) => i), 127])('client rejects filename control U+%i already rejected at the request boundary', codepoint => {
  expect(() => decodeMediaAsset({ id: '00000000-0000-4000-8000-000000000101', version: 1, filename: `bad${String.fromCharCode(codepoint)}.png`, state: 'pending', mime_type: null, byte_size: null, sha256: null, width: null, height: null, duration_ms: null, default_alt_text: null, safe_error: null, created_at: new Date().toISOString() })).toThrow('The media service returned an invalid response.');
});

const contradictory = [
  { ...capabilities([]), upload_available: true },
  { ...capabilities(['image/png']), upload_available: false },
  { ...capabilities(['image/png']), upload_available: 1 },
  { ...capabilities(['image/png']), library_available: 'true' },
  { ...capabilities(['image/png']), allowed_mime_types: ['image/png', 'image/png'] },
  { ...capabilities(['image/png']), allowed_mime_types: ['image/svg+xml'] },
  { ...capabilities(['image/png']), max_image_bytes: 0 },
  { ...capabilities(['image/png']), max_video_bytes: 52428801 },
];
test.each(contradictory)('contradictory capabilities fail closed in decoder and mounted editor: %#', async data => {
  expect(() => decodeMediaCapabilities(data)).toThrow('The media service returned an invalid response.');
  get.mockResolvedValue({ data });
  mount(<SocialMedia label='Master' media={[]} onChange={jest.fn()} />);
  await waitFor(() => expect(screen.getByText('The private media service is unavailable. Existing references are retained.')).toBeInTheDocument());
  const button = screen.getByRole('button', { name: 'Upload media' });
  expect(button).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Choose from library' })).toBeDisabled();
  fireEvent.click(button);
  expect(screen.queryByRole('heading', { name: 'Upload original media' })).not.toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});
