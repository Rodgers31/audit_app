'use client';

import { County } from '@/types';
import { motion } from 'framer-motion';
import { useEffect, useRef, useState } from 'react';
import { ComposableMap, Geographies, Geography } from 'react-simple-maps';

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
  const [currentPage, setCurrentPage] = useState(0);
  const [isUserInteracting, setIsUserInteracting] = useState(false);
  const [timerKey, setTimerKey] = useState(0); // Key to reset timer
  const lastNavigatedCountyRef = useRef<string | null>(null); // Track last navigated county
  const countiesPerPage = 12;
  const totalPages = Math.ceil(counties.length / countiesPerPage);

  // Auto-cycle through counties every 6 seconds
  useEffect(() => {
    if (isUserInteracting || totalPages <= 1) return;

    const interval = setInterval(() => {
      setCurrentPage((prev) => (prev + 1) % totalPages);
    }, 6000);

    return () => clearInterval(interval);
  }, [totalPages, isUserInteracting, timerKey]); // Added timerKey dependency to restart timer

  // Pause auto-cycling when user interacts and reset timer
  useEffect(() => {
    if (isUserInteracting) {
      const timeout = setTimeout(() => {
        setIsUserInteracting(false);
        setTimerKey((prev) => prev + 1); // Reset timer when resuming auto-cycling
      }, 5000); // Resume after 5 seconds of no interaction

      return () => clearTimeout(timeout);
    }
  }, [isUserInteracting]);

  const handleCountyClick = (county: County) => {
    setIsUserInteracting(true);
    setTimerKey((prev) => prev + 1); // Reset timer immediately when user clicks
    onCountySelect(county);
  };

  // Auto-navigate to page containing selected county when county is selected from map
  useEffect(() => {
    if (selectedCounty && lastNavigatedCountyRef.current !== selectedCounty.id) {
      const countyIndex = counties.findIndex((county) => county.id === selectedCounty.id);
      if (countyIndex !== -1) {
        const pageContainingCounty = Math.floor(countyIndex / countiesPerPage);
        if (pageContainingCounty !== currentPage) {
          setCurrentPage(pageContainingCounty);
        }
        lastNavigatedCountyRef.current = selectedCounty.id; // Mark this county as navigated
      }
    }
  }, [selectedCounty, counties, countiesPerPage, currentPage]);

  const currentCounties = counties.slice(
    currentPage * countiesPerPage,
    (currentPage + 1) * countiesPerPage
  );
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
          className='w-full h-[500px]'>
          {/* Kenya Borders */}
          <Geographies geography='/kenya-counties.json'>
            {({ geographies }) =>
              geographies.map((geo) => {
                const countyName =
                  geo.properties?.COUNTY_NAM || geo.properties?.NAME_1 || geo.properties?.name;
                const isSelected =
                  selectedCounty &&
                  (countyName?.toLowerCase() === selectedCounty.name.toLowerCase() ||
                    countyName?.toLowerCase() ===
                      selectedCounty.name.replace(' County', '').toLowerCase());

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
                      const geoName =
                        geo.properties?.COUNTY_NAM ||
                        geo.properties?.NAME_1 ||
                        geo.properties?.name;
                      console.log('Geography clicked:', geoName);
                      console.log('All geography properties:', geo.properties);
                      console.log(
                        'Available counties:',
                        counties.map((c) => c.name)
                      );

                      const county = counties.find((c) => {
                        // Normalize both names to lowercase for comparison
                        const normalizedCountyName = c.name.toLowerCase().replace(' county', '');
                        const normalizedGeoName = geoName?.toLowerCase().replace(' county', '');

                        const matches = [
                          // Direct lowercase comparison
                          normalizedCountyName === normalizedGeoName,
                          c.name.toLowerCase() === geoName?.toLowerCase(),
                          // Check if county name contains geography name
                          normalizedCountyName.includes(normalizedGeoName || ''),
                          // Check if geography name contains county name
                          normalizedGeoName?.includes(normalizedCountyName),
                          // Exact matches (case-sensitive)
                          c.name === geoName,
                          // With "county" suffix variations
                          c.name.toLowerCase() === `${normalizedGeoName} county`,
                          normalizedGeoName === `${normalizedCountyName} county`,
                        ];

                        const isMatch = matches.some(Boolean);
                        if (isMatch) {
                          console.log(`✓ Match found: ${geoName} -> ${c.name}`);
                        }
                        return isMatch;
                      });

                      console.log('Found county:', county);
                      if (county) {
                        setIsUserInteracting(true);
                        setTimerKey((prev) => prev + 1); // Reset timer when clicking on map
                        onCountySelect(county);
                      } else {
                        console.warn(`❌ No county found for geography: ${geoName}`);
                        console.log(
                          'Tried matching against counties:',
                          counties.map((c) => c.name).join(', ')
                        );
                      }
                    }}
                  />
                );
              })
            }
          </Geographies>
        </ComposableMap>
      </div>

      {/* Quick Select Grid */}
      <div className='mt-6'>
        <div className='flex items-center justify-between mb-4'>
          <h3 className='text-lg font-semibold text-gray-900 dark:text-neutral-text'>Quick Select County:</h3>
          <div className='flex items-center gap-2'>
            <div className='text-xs text-gray-500 dark:text-neutral-muted/80'>
              {totalPages > 1 && `Page ${currentPage + 1} of ${totalPages}`}
            </div>
            {totalPages > 1 && (
              <div className='flex gap-1'>
                {Array.from({ length: totalPages }).map((_, index) => (
                  <motion.div
                    key={index}
                    className={`w-2 h-2 rounded-full cursor-pointer ${
                      currentPage === index ? 'bg-blue-600' : 'bg-gray-300'
                    }`}
                    onClick={() => {
                      setCurrentPage(index);
                      setIsUserInteracting(true);
                      setTimerKey((prev) => prev + 1); // Reset timer
                    }}
                    whileHover={{ scale: 1.2 }}
                    whileTap={{ scale: 0.9 }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        <motion.div
          className='grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2 min-h-[120px]'
          key={currentPage}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.5 }}>
          {currentCounties.map((county, index) => {
            const isSelected = selectedCounty?.id === county.id;

            return (
              <motion.button
                key={county.id}
                onClick={() => handleCountyClick(county)}
                className={`
                  px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200
                  ${
                    isSelected
                      ? 'bg-blue-600 text-white shadow-lg scale-105'
                      : 'bg-white dark:bg-surface-base text-gray-700 dark:text-neutral-muted border border-gray-200 dark:border-neutral-border hover:border-blue-300 hover:text-blue-600'
                  }
                `}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1, duration: 0.3 }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onMouseEnter={() => setIsUserInteracting(true)}>
                {county.name.replace(' County', '')}
              </motion.button>
            );
          })}
        </motion.div>

        <div className='flex items-center justify-between mt-3'>
          <p className='text-sm text-gray-500 dark:text-neutral-muted/80'>
            Showing {currentCounties.length} of {counties.length} counties
            {!isUserInteracting && totalPages > 1 && (
              <span className='ml-2 text-blue-600'>• Auto-cycling</span>
            )}
          </p>

          {totalPages > 1 && (
            <div className='flex gap-2'>
              <button
                onClick={() => {
                  setCurrentPage((prev) => (prev - 1 + totalPages) % totalPages);
                  setIsUserInteracting(true);
                  setTimerKey((prev) => prev + 1); // Reset timer
                }}
                className='px-2 py-1 text-xs bg-gray-100 dark:bg-surface-elevated hover:bg-gray-200 dark:bg-surface-sunken rounded transition-colors'>
                ←
              </button>
              <button
                onClick={() => {
                  setCurrentPage((prev) => (prev + 1) % totalPages);
                  setIsUserInteracting(true);
                  setTimerKey((prev) => prev + 1); // Reset timer
                }}
                className='px-2 py-1 text-xs bg-gray-100 dark:bg-surface-elevated hover:bg-gray-200 dark:bg-surface-sunken rounded transition-colors'>
                →
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
