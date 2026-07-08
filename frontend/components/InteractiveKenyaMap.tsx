/**
 * InteractiveKenyaMap – redesigned with header / legend bar,
 * refined SVG styling (subtle inner-shadow, softer strokes),
 * and polished hover / active interactions.
 */
'use client';

import { KENYA_COUNTIES_GEOJSON } from '@/data/kenya-counties.geojson';
import { useLang } from '@/lib/i18n/LangProvider';
import { County } from '@/types';
import { AnimatePresence, motion } from 'framer-motion';
import { Eye, Layers, MapPin } from 'lucide-react';
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';
import CountyMarker from './map/CountyMarker';
import MapTooltip from './map/MapTooltip';
import {
  getCountyByName,
  getCountyFill,
  getCountyHoverFill,
  LEGEND_ITEMS,
} from './map/MapUtilities';

interface CountyShapeProps {
  geo: any;
  geoName: string;
  county: County | undefined;
  fill: string;
  hoverFill: string;
  isActive: boolean;
  onEnter: (geoName: string, county: County | undefined, e?: React.MouseEvent) => void;
  onLeave: () => void;
  onSelect: (county: County) => void;
}

/**
 * One county path, memoised so a hover / auto-rotate state change only
 * re-renders the counties whose props actually changed (typically 2 of
 * 47) instead of reconciling every path. The previous implementation
 * wrapped each county in a framer-motion spring (`motion.g`), which ran
 * 47 JS-driven animations per state change — a multi-second main-thread
 * block on low-end phones. The scale-up is now a plain CSS transition,
 * which the browser composites off the main thread.
 */
const CountyShape = memo(function CountyShape({
  geo,
  geoName,
  county,
  fill,
  hoverFill,
  isActive,
  onEnter,
  onLeave,
  onSelect,
}: CountyShapeProps) {
  return (
    <g
      style={{
        transformBox: 'fill-box',
        transformOrigin: 'center',
        transform: isActive ? 'scale(1.02)' : 'scale(1)',
        transition: 'transform 300ms cubic-bezier(0.34, 1.3, 0.64, 1)',
      }}>
      <Geography
        geography={geo}
        onMouseEnter={(e) => onEnter(geoName, county, e as any)}
        // Anchor is pinned at the cursor's ENTRY point to
        // the county and does not follow mousemove. If we
        // track mousemove, the tooltip chases the cursor
        // upward as the user tries to move toward it, and
        // the user can never reach it. Pinning on enter
        // lets the user slide straight into the card.
        onMouseLeave={onLeave}
        onClick={() => county && onSelect(county)}
        style={{
          default: {
            fill,
            stroke: isActive ? '#0F1A12' : '#3d5a45',
            strokeWidth: isActive ? 2.5 : 1.2,
            outline: 'none',
            filter: isActive ? 'url(#countyGlow)' : 'url(#innerShadow)',
            transition: 'fill 300ms ease, stroke-width 200ms ease',
          },
          hover: {
            fill: hoverFill,
            stroke: '#0F1A12',
            strokeWidth: 2,
            outline: 'none',
            filter: 'url(#countyGlow)',
            cursor: county ? 'pointer' : 'default',
            transition: 'fill 200ms ease, stroke-width 150ms ease',
          },
          pressed: {
            fill: '#1B3A2A',
            stroke: '#0F1A12',
            strokeWidth: 2.5,
            outline: 'none',
          },
        }}
      />
    </g>
  );
});

interface InteractiveKenyaMapProps {
  counties: County[];
  onCountySelect: (county: County) => void;
  onCountyHover?: (county: County | null) => void;
  selectedCounty: County | null;
  currentCountyIndex: number;
  onCountyIndexChange: (index: number) => void;
  isInteractingWithDetails?: boolean;
  className?: string;
}

export default function InteractiveKenyaMap({
  counties,
  onCountySelect,
  onCountyHover,
  selectedCounty,
  currentCountyIndex,
  onCountyIndexChange,
  isInteractingWithDetails = false,
  className = '',
}: InteractiveKenyaMapProps) {
  const { t } = useLang();
  /* ── state ── */
  const [hoveredCounty, setHoveredCounty] = useState<string | null>(null);
  // Cursor/centroid anchor in map-container local coordinates. Passed
  // to MapTooltip so it can place itself next to the hovered county
  // instead of floating at the center-top of the map, which leaves the
  // user no way to move the cursor onto the card without crossing
  // another county's hit area.
  const [hoveredAnchor, setHoveredAnchor] = useState<
    { x: number; y: number; containerWidth: number; containerHeight: number } | null
  >(null);
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const [showTooltip, setShowTooltip] = useState(false);
  const [visualMode, setVisualMode] = useState<'focus' | 'overview'>('overview');
  const [isMapHovered, setIsMapHovered] = useState(false);
  // Track coarse-pointer / touch state as React state so tooltip re-renders
  // pick up the close button when the user resizes across the breakpoint.
  const [isTouch, setIsTouch] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(pointer: coarse)');
    setIsTouch(mq.matches);
    const listener = (e: MediaQueryListEvent) => setIsTouch(e.matches);
    mq.addEventListener?.('change', listener);
    return () => mq.removeEventListener?.('change', listener);
  }, []);
  const isOverlayHoveredRef = useRef(false);
  const isProcessingLeaveRef = useRef(false);
  // Must be a ref, not useState. State reads close over the render that
  // created the handler — if a mouseenter runs BEFORE React commits the
  // render after a mouseleave's `setHideTimeoutId(tid)`, the closure
  // sees the stale null ID, can't cancel the pending timer, and the
  // timer fires 800ms later clearing `hoveredCounty` even though the
  // cursor is still on a county. Visually that flips the map back to
  // showing the auto-rotate county as "active" while the user's mouse
  // is hovering something else.
  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Mirror selectedCounty + counties in refs so the 800ms hide-timer's
  // closure always sees the latest values (the closure was captured at
  // mouseleave time; selectedCounty may have been set by a trailing
  // click in the interim).
  const selectedCountyRef = useRef(selectedCounty);
  useEffect(() => {
    selectedCountyRef.current = selectedCounty;
  }, [selectedCounty]);
  const countiesRef = useRef(counties);
  useEffect(() => {
    countiesRef.current = counties;
  }, [counties]);
  // Mirror hoveredCounty too, so the leave handler can stay referentially
  // stable (useCallback with no state deps) — otherwise every hover change
  // would mint new handlers and defeat CountyShape's memoisation.
  const hoveredCountyRef = useRef(hoveredCounty);
  useEffect(() => {
    hoveredCountyRef.current = hoveredCounty;
  }, [hoveredCounty]);

  /* ── geo data loading – single local file, inline fallback ──
   * .topo.json is the mapshaper-simplified TopoJSON (~48KB vs the
   * original 347KB GeoJSON) — same 47 counties, same NAME_1 property,
   * ~7x less main-thread JSON parsing on load. */
  const geoUrl = '/kenya-counties.topo.json';

  const [geoData, setGeoData] = useState<any | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(geoUrl, { cache: 'force-cache' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) setGeoData(data);
      } catch {
        // local file missing – fall back to compiled-in GeoJSON
        if (!cancelled) setGeoData(KENYA_COUNTIES_GEOJSON as any);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Promote the current `hoveredCounty` to a selection on touch
   * devices. Called from BOTH hover-linger timers (county leave + tooltip
   * overlay leave) since on iOS a tap can fire mouseenter but not click,
   * and whichever leave-timer fires last would otherwise clear the hover
   * state and snap the map back to the auto-rotate county.
   *
   * Reads the latest selectedCounty and counties via refs so a trailing
   * click that DID land doesn't get clobbered by a stale-closure promote.
   */
  const promoteHoverIfTouch = useCallback(
    (hoveredName: string | null) => {
      const isTouch =
        typeof window !== 'undefined' &&
        window.matchMedia?.('(pointer: coarse)').matches;
      if (!isTouch || !hoveredName || selectedCountyRef.current) return;
      const c = getCountyByName(hoveredName, countiesRef.current ?? []);
      if (!c) return;
      onCountySelect(c);
      const idx = (countiesRef.current ?? []).findIndex((cc) => cc.id === c.id);
      if (idx >= 0) onCountyIndexChange(idx);
    },
    [onCountySelect, onCountyIndexChange]
  );

  /** Convert a DOM MouseEvent to map-container-local coordinates for
   * the tooltip anchor. Using clientX/Y from the live event (rather
   * than the path centroid) means the tooltip appears right where the
   * cursor is — wherever inside the county the user happened to hover.
   * useCallback([]) — reads only a ref, so it is referentially stable
   * and can sit in dependency lists without breaking memoisation. */
  const anchorFromEvent = useCallback((e?: React.MouseEvent): typeof hoveredAnchor => {
    if (!e || !mapContainerRef.current) return null;
    const box = mapContainerRef.current.getBoundingClientRect();
    return {
      x: e.clientX - box.left,
      y: e.clientY - box.top,
      containerWidth: box.width,
      containerHeight: box.height,
    };
  }, []);

  /* ── hover handlers ──
   * All three geography handlers are useCallback-stable (state is read
   * through refs) so they can be passed to the memoised CountyShape
   * without invalidating it on every hover change. Dependency lists are
   * complete — every referenced callback is itself useCallback-stable,
   * so exhaustive deps cost nothing and stale-closure hazards are out. */
  const handleCountyMouseEnter = useCallback(
    (countyName: string, county: County | undefined, e?: React.MouseEvent) => {
      if (hideTimeoutRef.current) {
        clearTimeout(hideTimeoutRef.current);
        hideTimeoutRef.current = null;
      }
      isProcessingLeaveRef.current = false;
      setHoveredCounty(countyName);
      setHoveredAnchor(anchorFromEvent(e));
      setShowTooltip(!!county);
      if (county && onCountyHover) onCountyHover(county);
    },
    [anchorFromEvent, onCountyHover]
  );

  /** True when the component is running on a coarse-pointer device
   * (phone / tablet). Read lazily because SSR doesn't have `window`. */
  const isTouchNow = () =>
    typeof window !== 'undefined' &&
    !!window.matchMedia?.('(pointer: coarse)').matches;

  const handleCountyMouseLeave = useCallback(() => {
    // On touch the tooltip is user-dismissed (via the close button or
    // by tapping another county). Skipping the auto-hide linger gives
    // the user time to read the content — previously the tooltip would
    // vanish ~1s after tap, which isn't enough.
    if (isTouchNow()) {
      // Still promote the hovered county to a selection in case the
      // tap didn't cleanly fire `click` on iOS (same reason as before),
      // so the panel and pill reflect what they just tapped.
      promoteHoverIfTouch(hoveredCountyRef.current);
      return;
    }
    if (isProcessingLeaveRef.current) return;
    isProcessingLeaveRef.current = true;
    if (hideTimeoutRef.current) clearTimeout(hideTimeoutRef.current);
    hideTimeoutRef.current = setTimeout(() => {
      if (!isOverlayHoveredRef.current) {
        setHoveredCounty(null);
        setHoveredAnchor(null);
        setShowTooltip(false);
        if (onCountyHover) onCountyHover(null);
      }
      isProcessingLeaveRef.current = false;
      hideTimeoutRef.current = null;
    }, 800);
  }, [onCountyHover, promoteHoverIfTouch]);

  const handleOverlayMouseEnter = () => {
    isOverlayHoveredRef.current = true;
    if (hideTimeoutRef.current) {
      clearTimeout(hideTimeoutRef.current);
      hideTimeoutRef.current = null;
    }
  };
  const handleOverlayMouseLeave = () => {
    // See handleCountyMouseLeave — on touch the tooltip stays open until
    // the user taps the close button or another county.
    if (isTouchNow()) return;
    isOverlayHoveredRef.current = false;
    if (hideTimeoutRef.current) clearTimeout(hideTimeoutRef.current);
    hideTimeoutRef.current = setTimeout(() => {
      setHoveredCounty(null);
      setHoveredAnchor(null);
      setShowTooltip(false);
      if (onCountyHover) onCountyHover(null);
      hideTimeoutRef.current = null;
    }, 1200);
  };

  /** Explicit tooltip dismiss, triggered by the close button on touch
   * devices. Clears hover-state + tooltip visibility but leaves
   * selectedCounty alone so the panel and pill still reflect what was
   * tapped. */
  const handleTooltipClose = () => {
    if (hideTimeoutRef.current) {
      clearTimeout(hideTimeoutRef.current);
      hideTimeoutRef.current = null;
    }
    isOverlayHoveredRef.current = false;
    setHoveredCounty(null);
    setHoveredAnchor(null);
    setShowTooltip(false);
    if (onCountyHover) onCountyHover(null);
  };

  /* ── auto-rotate ──
   * Desktop-only. On coarse-pointer devices the 8s tick re-rendered the
   * map + details panel forever; a tap landing mid-render on a low-end
   * phone was a major INP contributor. Touch users drive the panel by
   * tapping counties instead. Also disabled under prefers-reduced-motion. */
  useEffect(() => {
    if (selectedCounty || isInteractingWithDetails || isMapHovered || !counties?.length) return;
    if (isTouch) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    const id = setInterval(() => {
      onCountyIndexChange(currentCountyIndex === 0 ? counties.length - 1 : currentCountyIndex - 1);
    }, 8000);
    return () => clearInterval(id);
  }, [
    selectedCounty,
    isInteractingWithDetails,
    isMapHovered,
    currentCountyIndex,
    onCountyIndexChange,
    counties,
    isTouch,
  ]);

  useEffect(
    () => () => {
      if (hideTimeoutRef.current) clearTimeout(hideTimeoutRef.current);
    },
    []
  );

  /* ── derived ── */
  const handleCountyClick = useCallback(
    (county: County) => {
      onCountySelect(county);
      const idx = (countiesRef.current ?? []).findIndex((c) => c.id === county.id);
      if (idx >= 0) onCountyIndexChange(idx);
    },
    [onCountySelect, onCountyIndexChange]
  );

  /* Resolve geo name → County once per county-data change and cache it.
   * getCountyByName normalises with regexes and linear-scans the county
   * list; calling it for every geography on every render (as the colour
   * helpers used to) burned tens of thousands of regex executions per
   * hover/tick on the main thread. */
  const resolveCounty = useMemo(() => {
    const cache = new Map<string, County | undefined>();
    return (geoName: string): County | undefined => {
      if (cache.has(geoName)) return cache.get(geoName);
      const county = getCountyByName(geoName, counties ?? []);
      cache.set(geoName, county);
      return county;
    };
  }, [counties]);

  const currentAutoCounty =
    !selectedCounty && counties?.length ? counties[currentCountyIndex] : null;

  // Label pill priority: hover > click > auto-rotate. Without this the
  // pill kept showing the auto-rotate target even while the user was
  // hovering a different county, so the map felt like it was "fighting"
  // the cursor.
  const activeLabel = hoveredCounty
    ? resolveCounty(hoveredCounty)?.name ?? null
    : selectedCounty?.name ?? currentAutoCounty?.name ?? null;

  /* ── matched county count for header ── */
  const matchedCount = useMemo(() => counties?.length ?? 0, [counties]);

  /* ── render ── */
  return (
    <div
      className={`relative w-full h-full flex flex-col ${className}`}
      style={{ minHeight: '620px' }}
      onMouseEnter={() => setIsMapHovered(true)}
      onMouseLeave={() => setIsMapHovered(false)}>
      {/* ═══════════ Header Bar ═══════════ */}
      <div className='flex flex-wrap items-center justify-between gap-3 mb-3'>
        {/* Title */}
        <div className='flex items-center gap-2'>
          <div className='w-8 h-8 rounded-lg bg-gov-forest/10 flex items-center justify-center'>
            <MapPin className='w-4 h-4 text-gov-forest dark:text-emerald-100' />
          </div>
          <div>
            <h3 className='text-sm font-semibold text-gov-dark dark:text-white leading-tight'>{t('home.map.title')}</h3>
            <p className='text-[11px] text-gray-500 dark:text-neutral-muted/80 leading-tight'>
              {matchedCount} {t('home.map.subtitle_prefix')} &middot; {t('home.map.subtitle_suffix')}
            </p>
          </div>
        </div>

        {/* Legend pills */}
        <div className='flex flex-wrap items-center gap-1.5'>
          {LEGEND_ITEMS.map((item) => (
            <span
              key={item.labelKey}
              className='inline-flex items-center gap-1 text-[10px] font-medium text-gray-600 dark:text-neutral-muted bg-white/70 dark:bg-surface-elevated rounded-full px-2 py-0.5 border border-gray-200/60 dark:border-neutral-border/60'>
              <span
                className='w-2 h-2 rounded-full ring-1 ring-black/10'
                style={{ backgroundColor: item.color }}
              />
              {t(item.labelKey)}
            </span>
          ))}
        </div>

        {/* View mode toggle */}
        <div className='flex items-center bg-white/60 dark:bg-surface-elevated rounded-lg border border-gray-200/60 dark:border-neutral-border/60 p-0.5'>
          <button
            onClick={() => setVisualMode('overview')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
              visualMode === 'overview'
                ? 'bg-gov-forest text-white shadow-sm'
                : 'text-gray-500 dark:text-neutral-muted/80 hover:text-gray-700 dark:text-neutral-muted'
            }`}>
            <Layers className='w-3 h-3' />
            {t('home.map.view_all')}
          </button>
          <button
            onClick={() => setVisualMode('focus')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
              visualMode === 'focus'
                ? 'bg-gov-forest text-white shadow-sm'
                : 'text-gray-500 dark:text-neutral-muted/80 hover:text-gray-700 dark:text-neutral-muted'
            }`}>
            <Eye className='w-3 h-3' />
            {t('home.map.view_focus')}
          </button>
        </div>
      </div>

      {/* ═══════════ Map Container ═══════════ */}
      <div
        ref={mapContainerRef}
        className='relative w-full flex-1 rounded-xl overflow-hidden border border-white/30'
        role="application"
        aria-label={t('home.map.aria_label')}
        style={{ minHeight: 560 }}>
        {/* Subtle radial vignette overlay */}
        <div
          className='absolute inset-0 pointer-events-none z-10 rounded-xl'
          style={{
            background:
              'radial-gradient(ellipse at center, transparent 55%, rgba(15,26,18,0.06) 100%)',
          }}
        />

        {/* Active county label pill */}
        <AnimatePresence mode='wait'>
          {activeLabel && (
            <motion.div
              key={activeLabel}
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.3 }}
              className='absolute top-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1.5 bg-gov-dark/80 backdrop-blur-md text-white text-xs font-semibold px-3 py-1.5 rounded-full shadow-lg border border-white/10'>
              <span className='w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse' />
              {activeLabel}
            </motion.div>
          )}
        </AnimatePresence>

        {/* SVG Map */}
        <ComposableMap
          projection='geoMercator'
          projectionConfig={{ scale: 5500, center: [37.8, -0.2] }}
          width={1100}
          height={1100}
          className='w-full h-full'
          style={{ background: 'transparent' }}>
          <defs>
            {/* Soft outer glow for active/hover */}
            <filter id='countyGlow' x='-30%' y='-30%' width='160%' height='160%'>
              <feGaussianBlur stdDeviation='2.5' result='blur' />
              <feMerge>
                <feMergeNode in='blur' />
                <feMergeNode in='SourceGraphic' />
              </feMerge>
            </filter>
            {/* Subtle inner shadow on each county for depth */}
            <filter id='innerShadow' x='-10%' y='-10%' width='120%' height='120%'>
              <feComponentTransfer in='SourceAlpha'>
                <feFuncA type='table' tableValues='1 0' />
              </feComponentTransfer>
              <feGaussianBlur stdDeviation='1.5' />
              <feOffset dx='0' dy='1' result='offsetblur' />
              <feFlood floodColor='rgba(0,0,0,0.12)' result='color' />
              <feComposite in2='offsetblur' operator='in' />
              <feComposite in2='SourceAlpha' operator='in' />
              <feMerge>
                <feMergeNode in='SourceGraphic' />
                <feMergeNode />
              </feMerge>
            </filter>
          </defs>

          <Geographies geography={geoData ?? geoUrl}>
            {({ geographies }) =>
              geographies.map((geo) => {
                const geoCountyName =
                  geo.properties?.COUNTY_NAM ||
                  geo.properties?.COUNTY ||
                  geo.properties?.NAME_1 ||
                  geo.properties?.NAME ||
                  geo.properties?.name ||
                  '';
                const county = resolveCounty(geoCountyName);
                // The auto-rotate county only counts as "active" (scale-up +
                // glow + thick stroke) when nothing else is taking focus.
                // Hovering any county suppresses it so we never have two
                // counties reading as active at once. The `!!county` guards
                // matter: before county data loads every geography resolves
                // to undefined, and `undefined === undefined` used to mark
                // ALL 47 counties active — 47 Gaussian-blur glow filters
                // during the hydration window.
                const isSelected = !!county && selectedCounty?.id === county.id;
                const isAutoActive =
                  !!county &&
                  !selectedCounty &&
                  !hoveredCounty &&
                  currentAutoCounty?.id === county.id;
                const isActive = isSelected || isAutoActive;

                return (
                  <CountyShape
                    key={geo.rsmKey}
                    geo={geo}
                    geoName={geoCountyName}
                    county={county}
                    fill={getCountyFill(county, {
                      isSelected,
                      isAutoActive,
                      isHovered: hoveredCounty === geoCountyName,
                      visualMode,
                    })}
                    hoverFill={getCountyHoverFill(county)}
                    isActive={isActive}
                    onEnter={handleCountyMouseEnter}
                    onLeave={handleCountyMouseLeave}
                    onSelect={handleCountyClick}
                  />
                );
              })
            }
          </Geographies>

          {/* Active County Marker — hidden while hovering so it doesn't
              compete with the cursor's target for attention. */}
          {currentAutoCounty && !hoveredCounty && <CountyMarker county={currentAutoCounty} />}
        </ComposableMap>

        {/* Hover Tooltip */}
        <AnimatePresence>
          {showTooltip &&
            hoveredCounty &&
            (() => {
              const county = resolveCounty(hoveredCounty);
              return county ? (
                <MapTooltip
                  county={county}
                  onMouseEnter={handleOverlayMouseEnter}
                  onMouseLeave={handleOverlayMouseLeave}
                  onCountyClick={handleCountyClick}
                  // Desktop hover only: position the card at the cursor
                  // so the user can slide straight up into it. Omitting
                  // the prop on touch falls back to the center-top
                  // placement where the fixed close button is reachable.
                  anchor={!isTouch && hoveredAnchor ? hoveredAnchor : undefined}
                  // Only show the close button on coarse-pointer devices.
                  // Desktop users already have hover-dismiss, and a close
                  // button there would just be noise. `isTouch` is tracked
                  // as state so window-resize across breakpoints updates
                  // the UI.
                  onClose={isTouch ? handleTooltipClose : undefined}
                />
              ) : null;
            })()}
        </AnimatePresence>

        {/* Bottom-right hint */}
        <div className='absolute bottom-3 right-3 z-20 text-[10px] text-gray-400 dark:text-neutral-muted/80 bg-white/60 dark:bg-surface-elevated backdrop-blur-sm rounded-md px-2 py-1 border border-gray-200/40 dark:border-neutral-border/40'>
          Hover to explore &middot; Click to select
        </div>
      </div>
    </div>
  );
}
