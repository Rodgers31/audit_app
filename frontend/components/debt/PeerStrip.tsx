'use client';

import { motion } from 'framer-motion';
import { Globe2 } from 'lucide-react';
import InfoTip from '@/components/InfoTip';

interface PeerEntry {
  country: string;
  debt_to_gdp: number;
  debt_service_to_revenue: number;
  external_debt_share: number;
}

interface PeerStripProps {
  peers: PeerEntry[];
  kenyaCountryName?: string;
}

const COUNTRY_META: Record<string, { flag: string; emoji: string }> = {
  Kenya: { flag: '/flags/ke.svg', emoji: '🇰🇪' },
  Tanzania: { flag: '/flags/tz.svg', emoji: '🇹🇿' },
  Uganda: { flag: '/flags/ug.svg', emoji: '🇺🇬' },
  Rwanda: { flag: '/flags/rw.svg', emoji: '🇷🇼' },
  Ethiopia: { flag: '/flags/et.svg', emoji: '🇪🇹' },
};

const IMF_THRESHOLD = 55;

function bandForDebtToGdp(ratio: number): {
  tone: string;
  label: string;
  bg: string;
  border: string;
} {
  if (ratio >= IMF_THRESHOLD)
    return {
      tone: 'text-gov-copper',
      label: 'Above 55% anchor',
      bg: 'from-gov-copper/12 to-gov-copper/4',
      border: 'border-gov-copper/30',
    };
  if (ratio >= 40)
    return {
      tone: 'text-gov-gold',
      label: 'Caution',
      bg: 'from-gov-gold/12 to-gov-gold/4',
      border: 'border-gov-gold/30',
    };
  return {
    tone: 'text-gov-sage',
    label: 'Within sustainable band',
    bg: 'from-gov-sage/12 to-gov-sage/4',
    border: 'border-gov-sage/30',
  };
}

function RingGauge({
  value,
  max = 100,
  color,
  size = 96,
  strokeWidth = 8,
  centerLabel,
}: {
  value: number;
  max?: number;
  color: string;
  size?: number;
  strokeWidth?: number;
  centerLabel: string;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(value, max));
  const offset = circumference - (clamped / max) * circumference;
  return (
    <div className='relative inline-flex items-center justify-center' style={{ width: size, height: size }}>
      <svg width={size} height={size} className='-rotate-90'>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill='none'
          stroke='rgba(31,58,42,0.08)'
          strokeWidth={strokeWidth}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill='none'
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap='round'
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
      <div className='absolute inset-0 flex items-center justify-center'>
        <span className='text-base font-bold text-gov-dark dark:text-white tabular-nums'>{centerLabel}</span>
      </div>
    </div>
  );
}

export default function PeerStrip({ peers, kenyaCountryName = 'Kenya' }: PeerStripProps) {
  if (!peers || peers.length === 0) {
    return (
      <div className='rounded-xl bg-white/60 dark:bg-surface-elevated border border-white/60 p-6 text-center text-sm text-neutral-muted'>
        Peer comparison data unavailable.
      </div>
    );
  }

  const sorted = [...peers].sort((a, b) => b.debt_to_gdp - a.debt_to_gdp);
  const kenyaEntry = peers.find((p) => p.country === kenyaCountryName);
  const peersOnly = peers.filter((p) => p.country !== kenyaCountryName);
  const eacAvg =
    peersOnly.length > 0
      ? peersOnly.reduce((s, p) => s + p.debt_to_gdp, 0) / peersOnly.length
      : 0;
  const kenyaVsAvg = kenyaEntry ? kenyaEntry.debt_to_gdp - eacAvg : 0;

  return (
    <div className='space-y-4'>
      <div>
        <h3 className='font-display text-xl sm:text-2xl text-gov-dark dark:text-white flex items-center gap-2'>
          <Globe2 className='text-gov-forest dark:text-emerald-100' size={22} />
          Kenya in the East African context
        </h3>
        <p className='text-sm text-neutral-muted mt-1'>
          Debt-to-GDP, service ratio and external share across EAC peers. Sources: IMF WEO, World
          Bank IDS (via WDI).
        </p>
      </div>

      <div className='grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3'>
        {sorted.map((peer, idx) => {
          const isKenya = peer.country === kenyaCountryName;
          const band = bandForDebtToGdp(peer.debt_to_gdp);
          const meta = COUNTRY_META[peer.country] || { emoji: '🏳️' };
          const ringColor = isKenya ? '#C94A4A' : '#4A7C5C';
          return (
            <motion.div
              key={peer.country}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05 + idx * 0.06, duration: 0.4 }}
              className={`relative rounded-xl border p-4 bg-gradient-to-br ${band.bg} ${
                isKenya
                  ? 'border-gov-copper/50 ring-2 ring-gov-copper/30 shadow-elevated'
                  : band.border
              }`}>
              {isKenya && (
                <span className='absolute -top-2 right-3 rounded-full bg-gov-copper text-white text-[10px] font-bold px-2 py-0.5 shadow-sm uppercase tracking-wider'>
                  You
                </span>
              )}
              <div className='flex items-center gap-2 mb-3'>
                <span className='text-2xl'>{meta.emoji}</span>
                <div className='min-w-0'>
                  <div className='text-sm font-semibold text-gov-dark dark:text-white truncate'>
                    {peer.country}
                  </div>
                  <div className={`text-[10px] font-medium ${band.tone}`}>{band.label}</div>
                </div>
              </div>
              <div className='flex items-center gap-3'>
                <RingGauge
                  value={peer.debt_to_gdp}
                  color={ringColor}
                  size={80}
                  strokeWidth={7}
                  centerLabel={`${peer.debt_to_gdp.toFixed(0)}%`}
                />
                <div className='flex-1 min-w-0 space-y-1.5'>
                  <div>
                    <div className='text-[10px] uppercase tracking-wider text-neutral-muted'>
                      Service / Rev
                    </div>
                    <div className='text-sm font-bold text-gov-dark dark:text-white tabular-nums'>
                      {peer.debt_service_to_revenue.toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className='text-[10px] uppercase tracking-wider text-neutral-muted'>
                      External
                    </div>
                    <div className='text-sm font-bold text-gov-dark dark:text-white tabular-nums'>
                      {peer.external_debt_share.toFixed(0)}%
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>

      {kenyaEntry && (
        <div className='flex flex-wrap items-center gap-4 rounded-xl bg-gov-dark/5 border border-gov-dark/10 px-4 py-3'>
          <div className='flex items-center gap-2 text-sm'>
            <span className='text-neutral-muted'>EAC peer average debt-to-GDP:</span>
            <span className='font-bold text-gov-dark dark:text-white tabular-nums'>{eacAvg.toFixed(1)}%</span>
          </div>
          <div className='h-4 w-px bg-gov-dark/15' />
          <div className='flex items-center gap-2 text-sm'>
            <span className='text-neutral-muted'>Kenya vs. average:</span>
            <span
              className={`font-bold tabular-nums ${
                kenyaVsAvg > 0 ? 'text-gov-copper' : 'text-gov-sage'
              }`}>
              {kenyaVsAvg > 0 ? '+' : ''}
              {kenyaVsAvg.toFixed(1)} pp
            </span>
          </div>
          <InfoTip
            term='debt-to-gdp'
            size={14}
          />
        </div>
      )}
    </div>
  );
}
