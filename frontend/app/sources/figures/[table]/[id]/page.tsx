import FigureEvidencePage from './FigureEvidencePage';

export default async function Page({ params }: { params: Promise<{ table: string; id: string }> }) {
  const { table, id } = await params;
  return <FigureEvidencePage table={table} id={id} />;
}
