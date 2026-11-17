import type { Metadata } from 'next';
import FigureEvidencePage from './FigureEvidencePage';

// The page renders one title, using its initial fallback and the loaded figure.
export const metadata: Metadata = { title: null };

export default async function Page({ params }: { params: Promise<{ table: string; id: string }> }) {
  const { table, id } = await params;
  return <FigureEvidencePage table={table} id={id} />;
}
