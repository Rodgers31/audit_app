import { metadata } from '@/app/counties/[id]/page';

jest.mock('@/app/counties/[id]/CountyDetailClient', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('@/lib/api/counties', () => ({ getCountyComprehensive: jest.fn() }));
jest.mock('@/lib/react-query/getQueryClient', () => ({ getQueryClient: jest.fn() }));

describe('County detail search metadata', () => {
  it('describes the available accountability content without advertising withdrawn projects', () => {
    expect(metadata.description).toMatch(/accountability/i);
    expect(metadata.description).not.toMatch(/stalled projects/i);
  });
});
