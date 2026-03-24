/**
 * InteractiveKenyaMap – redesigned with header / legend bar,
 * refined SVG styling (subtle inner-shadow, softer strokes),
 * and polished hover / active interactions.
 */
'use client';

import { KENYA_COUNTIES_GEOJSON } from '@/data/kenya-counties.geojson';
import { County } from '@/types';
import { AnimatePresence, motion } from 'framer-motion';
import { Eye, Layers, MapPin } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';
import CountyMarker from './map/CountyMarker';
import MapTooltip from './map/MapTooltip';
import {
  getCountyByName,
  getCountyColor,
  getCountyHoverColor,
  getNextAnimationMode,
  LEGEND_ITEMS,
} from './map/MapUtilities';

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
  /* ── state ── */
  const [hoveredCounty, setHoveredCounty] = useState<string | null>(null);
  const [showTooltip, setShowTooltip] = useState(false);
  const [animationMode, setAnimationMode] = useState<'slideshow' | 'pulse' | 'wave'>('slideshow');
  const [visualMode, setVisualMode] = useState<'focus' | 'overview'>('overview');
  const [hideTimeoutId, setHideTimeoutId] = useState<NodeJS.Timeout | null>(null);

  const [isMapHovered, setIsMapHovered] = useState(false);
  const isOverlayHoveredRef = useRef(false);
  const isProcessingLeaveRef = useRef(false);

  /* ── geo data loading – single local file, inline fallback ── */
  const geoUrl = '/kenya-counties.json';

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

  /* ── hover handlers ── */
  const handleCountyMouseEnter = (countyName: string, county: any) => {
    if (hideTimeoutId) {
      clearTimeout(hideTimeoutId);
      setHideTimeoutId(null);
    }
    isProcessingLeaveRef.current = false;
    setHoveredCounty(countyName);
    setShowTooltip(!!county);
    if (county && onCountyHover) onCountyHover(county);
  };

  const handleCountyMouseLeave = () => {
    if (isProcessingLeaveRef.current) return;
    isProcessingLeaveRef.current = true;
    if (hideTimeoutId) {
      clearTimeout(hideTimeoutId);
      setHideTimeoutId(null);
    }
    const tid = setTimeout(() => {
      if (!isOverlayHoveredRef.current) {
        setHoveredCounty(null);
        setShowTooltip(false);
        if (onCountyHover) onCountyHover(null);
      }
      isProcessingLeaveRef.current = false;
    }, 800);
    setHideTimeoutId(tid);
  };

  const handleOverlayMouseEnter = () => {
    isOverlayHoveredRef.current = true;
    if (hideTimeoutId) {
      clearTimeout(hideTimeoutId);
      setHideTimeoutId(null);
    }
  };
  const handleOverlayMouseLeave = () => {
    isOverlayHoveredRef.current = false;
    const tid = setTimeout(() => {
      setHoveredCounty(null);
      setShowTooltip(false);
      if (onCountyHover) onCountyHover(null);
    }, 1200);
    setHideTimeoutId(tid);
  };

  /* ── auto-rotate + animation mode cycle ── */
  useEffect(() => {
    if (selectedCounty || isInteractingWithDetails || isMapHovered || !counties?.length) return;
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
  ]);

  useEffect(() => {
    const id = setInterval(() => setAnimationMode(getNextAnimationMode), 15000);
    return () => clearInterval(id);
  }, []);

  useEffect(
    () => () => {
      if (hideTimeoutId) clearTimeout(hideTimeoutId);
    },
    [hideTimeoutId]
  );

  /* ── derived ── */
  const handleCountyClick = (county: County) => {
    onCountySelect(county);
    if (counties) onCountyIndexChange(counties.findIndex((c) => c.id === county.id));
  };

  const currentAutoCounty =
    !selectedCounty && counties?.length ? counties[currentCountyIndex] : null;

  const activeLabel = selectedCounty?.name ?? currentAutoCounty?.name ?? null;

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
            <MapPin className='w-4 h-4 text-gov-forest' />
          </div>
          <div>
            <h3 className='text-sm font-semibold text-gov-dark leading-tight'>County Explorer</h3>
            <p className='text-[11px] text-gray-500 leading-tight'>
              {matchedCount} counties &middot; audit-status colour coded
            </p>
          </div>
        </div>

        {/* Legend pills */}
        <div className='flex flex-wrap items-center gap-1.5'>
          {LEGEND_ITEMS.map((item) => (
            <span
              key={item.label}
              className='inline-flex items-center gap-1 text-[10px] font-medium text-gray-600 bg-white/70 rounded-full px-2 py-0.5 border border-gray-200/60'>
              <span
                className='w-2 h-2 rounded-full ring-1 ring-black/10'
                style={{ backgroundColor: item.color }}
              />
              {item.label}
            </span>
          ))}
        </div>

        {/* View mode toggle */}
        <div className='flex items-center bg-white/60 rounded-lg border border-gray-200/60 p-0.5'>
          <button
            onClick={() => setVisualMode('overview')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
              visualMode === 'overview'
                ? 'bg-gov-forest text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}>
            <Layers className='w-3 h-3' />
            All
          </button>
          <button
            onClick={() => setVisualMode('focus')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all ${
              visualMode === 'focus'
                ? 'bg-gov-forest text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}>
            <Eye className='w-3 h-3' />
            Focus
          </button>
        </div>
      </div>

      {/* ═══════════ Map Container ═══════════ */}
      <div
        className='relative w-full flex-1 rounded-xl overflow-hidden border border-white/30'
        role="application"
        aria-label="Interactive map of Kenya's 47 counties. Hover to see county details, click to select a county. Counties are color-coded by audit status."
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
              geographies.map((geo, index) => {
                const geoCountyName =
                  geo.properties?.COUNTY_NAM ||
                  geo.properties?.COUNTY ||
                  geo.properties?.NAME_1 ||
                  geo.properties?.NAME ||
                  geo.properties?.name ||
                  '';
                const county = getCountyByName(geoCountyName, counties || []);
                const isActive =
                  selectedCounty?.id === county?.id ||
                  (!selectedCounty && currentAutoCounty?.id === county?.id);
                const isHovered = hoveredCounty === geoCountyName;

                const fillColor = getCountyColor(
                  geoCountyName,
                  counties || [],
                  index,
                  selectedCounty,
                  currentCountyIndex,
                  hoveredCounty,
                  animationMode,
                  visualMode
                );

                const hoverFill = county
                  ? getCountyHoverColor(geoCountyName, counties || [])
                  : '#c8cec9';

                return (
                  <motion.g
                    key={geo.rsmKey}
                    initial={{ scale: 1 }}
                    animate={{
                      scale: isActive ? 1.02 : 1,
                    }}
                    transition={{ type: 'spring', stiffness: 300, damping: 25 }}>
                    <Geography
                      geography={geo}
                      onMouseEnter={() => handleCountyMouseEnter(geoCountyName, county)}
                      onMouseLeave={handleCountyMouseLeave}
                      onClick={() => county && handleCountyClick(county)}
                      style={{
                        default: {
                          fill: fillColor,
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
                  </motion.g>
                );
              })
            }
          </Geographies>

          {/* Active County Marker */}
          {currentAutoCounty && <CountyMarker county={currentAutoCounty} />}
        </ComposableMap>

        {/* Hover Tooltip */}
        <AnimatePresence>
          {showTooltip &&
            hoveredCounty &&
            (() => {
              const county = getCountyByName(hoveredCounty, counties || []);
              return county ? (
                <MapTooltip
                  county={county}
                  onMouseEnter={handleOverlayMouseEnter}
                  onMouseLeave={handleOverlayMouseLeave}
                  onCountyClick={handleCountyClick}
                />
              ) : null;
            })()}
        </AnimatePresence>

        {/* Bottom-right hint */}
        <div className='absolute bottom-3 right-3 z-20 text-[10px] text-gray-400 bg-white/60 backdrop-blur-sm rounded-md px-2 py-1 border border-gray-200/40'>
          Hover to explore &middot; Click to select
        </div>
      </div>
    </div>
  );
}
