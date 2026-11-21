import { useSyncExternalStore } from 'react';

const desktopQuery = '(min-width: 960px)';

function subscribeToDesktopLayout(notify: () => void) {
  const query = window.matchMedia(desktopQuery);
  query.addEventListener('change', notify);
  return () => query.removeEventListener('change', notify);
}

export function useCountyExplorerDesktop(): boolean {
  return useSyncExternalStore(
    subscribeToDesktopLayout,
    () => window.matchMedia(desktopQuery).matches,
    () => false
  );
}

export type CountyExplorerSelection = {
  selectedId?: string;
  onSelect: (countyId: string) => void;
};
