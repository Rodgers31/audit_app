'use client';

import { County } from '@/types';
import { motion } from 'framer-motion';
import { ComposableMap, Geographies, Geography, Marker } from 'react-simple-maps';

interface CountyMapSelectorProps {
  counties: County[];
  onCountySelect: (county: County) => void;
  selectedCounty: County | null;
}

export default function CountyMapSelector({
  counties,
  onCountySelect,
  selectedCounty,
}: CountyMapSelectorProps) {
  return (
    <div className='w-full'>
      {/* Map Container */}
      <div className='relative bg-slate-50 dark:bg-surface-elevated rounded-2xl p-6 border-2 border-slate-200'>
        <ComposableMap
          projection='geoMercator'
          projectionConfig={{
            center: [37.9062, -0.0236],
            scale: 2800,
          }}
          className='w-full h-96'>
          {/* Kenya Borders */}
          <Geographies geography='/kenya-counties.json'>
            {({ geographies }) =>
              geographies.map((geo) => {
                const countyName = geo.properties?.NAME_1 || geo.properties?.name;
                const isSelected =
                  selectedCounty &&
                  (countyName === selectedCounty.name ||
                    countyName === selectedCounty.name.replace(' County', ''));

                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill={isSelected ? '#3b82f6' : '#e2e8f0'}
                    stroke='#94a3b8'
                    strokeWidth={0.5}
                    style={{
                      default: {
                        outline: 'none',
                      },
                      hover: {
                        fill: isSelected ? '#2563eb' : '#cbd5e1',
                        outline: 'none',
                        cursor: 'pointer',
                      },
                      pressed: {
                        fill: '#1d4ed8',
                        outline: 'none',
                      },
                    }}
                    onClick={() => {
                      const county = counties.find(
                        (c) => c.name === countyName || c.name.replace(' County', '') === countyName
                      );
                      if (county) {
                        onCountySelect(county);
                      }
                    }}
                  />
                );
              })
            }
          </Geographies>

          {/* County Markers */}
          {counties.filter((county) => county.coordinates).map((county) => {
            const isSelected = selectedCounty?.id === county.id;

            return (
              <Marker key={county.id} coordinates={county.coordinates!}>
                <motion.circle
                  r={isSelected ? 8 : 5}
                  fill={isSelected ? '#ef4444' : '#3b82f6'}
                  stroke='#ffffff'
                  strokeWidth={2}
                  className='cursor-pointer drop-shadow-lg'
                  onClick={() => onCountySelect(county)}
                  whileHover={{ r: 7, fill: '#ef4444' }}
                  whileTap={{ r: 6 }}
                  transition={{ duration: 0.2 }}
                />
                <motion.text
                  textAnchor='middle'
                  y={isSelected ? -15 : -12}
                  className='text-xs font-medium fill-slate-700 pointer-events-none'
                  initial={{ opacity: 0 }}
                  animate={{ opacity: isSelected ? 1 : 0.7 }}
                  transition={{ duration: 0.2 }}>
                  {county.name.replace(' County', '')}
                </motion.text>
              </Marker>
            );
          })}
        </ComposableMap>
      </div>

      {/* Quick Select Grid */}
      <div className='mt-6'>
        <h3 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-4'>Quick Select County:</h3>
        <div className='grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2'>
          {counties.slice(0, 12).map((county) => {
            const isSelected = selectedCounty?.id === county.id;

            return (
              <motion.button
                key={county.id}
                onClick={() => onCountySelect(county)}
                className={`
                  px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200
                  ${
                    isSelected
                      ? 'bg-blue-600 text-white shadow-lg scale-105'
                      : 'bg-white dark:bg-surface-base text-gray-700 dark:text-neutral-muted border border-gray-200 dark:border-neutral-border hover:border-blue-300 hover:text-blue-600'
                  }
                `}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}>
                {county.name.replace(' County', '')}
              </motion.button>
            );
          })}
        </div>

        {counties.length > 12 && (
          <p className='text-sm text-gray-500 dark:text-neutral-muted/80 mt-2'>
            Showing {Math.min(12, counties.length)} of {counties.length} counties. Click on the map
            or use search to find others.
          </p>
        )}
      </div>
    </div>
  );
}
