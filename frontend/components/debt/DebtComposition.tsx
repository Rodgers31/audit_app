import { useLang } from '@/lib/i18n/LangProvider';
import { formatLenderShare } from '@/lib/debt/lenderBreakdown';
import { fmtKES } from '@/lib/utils';
import { type CSSProperties, useState } from 'react';
import styles from './RankedLenders.module.css';

export type LenderType = 'domestic' | 'external' | 'unclassified';

export interface CompositionGroup {
  category: string;
  name: string;
  color: string;
  type: LenderType;
  share: number;
  outstanding: number;
}

type Portion = { id: string; color: string; share: number; outstanding: number };
type Preview = { kind: 'type' | 'group'; id: string };
const TYPES = [
  { id: 'domestic' as const, color: 'var(--chart-teal)' },
  { id: 'external' as const, color: 'var(--chart-gold)' },
  { id: 'unclassified' as const, color: 'var(--chart-context)' },
];
const CENTER = 140;
const INNER_RADIUS = 94;
const OUTER_RADIUS = 124;

function parts(values: Portion[]) {
  let start = 0;
  return values.map(part => {
    const placed = { ...part, start };
    start += part.share;
    return placed;
  });
}

function Ring({ portions, radius, active, kind, onPreview }: {
  portions: ReturnType<typeof parts>; radius: number; active?: string;
  kind: Preview['kind']; onPreview: (value: Preview | null) => void;
}) {
  return portions.map(({ id, color, share, start }) => {
    // The separator scales down for very small slices so a positive share is
    // still drawn at its position. The stacked bar keeps all exact widths.
    const gap = portions.length > 1 ? Math.min(0.48, share * 0.16) : 0;
    const length = share - gap;
    return (
      <circle key={id} cx={CENTER} cy={CENTER} r={radius} fill='none'
        pathLength={100} stroke={color} strokeWidth={24}
        transform={`rotate(-90 ${CENTER} ${CENTER})`}
        strokeDasharray={`${length} ${100 - length}`} strokeDashoffset={-(start + gap / 2)}
        className={styles.ringPortion} data-key={id} data-muted={active != null && active !== id}
        onPointerEnter={event => { if (event.pointerType === 'mouse') onPreview({ kind, id }); }}
        onPointerLeave={() => onPreview(null)} />
    );
  });
}

export default function DebtComposition({ groups, total, usesPrincipal, active }: {
  groups: CompositionGroup[]; total: number; usesPrincipal: boolean; active: string | null;
}) {
  const { lang, t } = useLang();
  const [preview, setPreview] = useState<Preview | null>(null);
  const locale = lang === 'sw' ? 'sw-KE' : 'en-KE';
  const count = new Intl.NumberFormat(locale).format(groups.length);
  const outerShare = new Intl.NumberFormat(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const formatOuterShare = (share: number) => {
    if (share < 0.1) return `<${outerShare.format(0.1)}`;
    if (share > 99.9 && share < 100) return `>${outerShare.format(99.9)}`;
    return outerShare.format(share);
  };
  const typeParts = parts(TYPES.map(type => ({
    ...type, share: groups.reduce((sum, group) => group.type === type.id ? sum + group.share : sum, 0),
    outstanding: groups.reduce((sum, group) => group.type === type.id ? sum + group.outstanding : sum, 0),
  })).filter(type => type.share > 0));
  const groupParts = parts(groups.map(group => ({ ...group, id: group.category })));
  const previewParts = preview?.kind === 'type' ? typeParts : groupParts;
  const previewed = previewParts.find(part => part.id === preview?.id);
  const previewGroup = preview?.kind === 'group' ? groups.find(group => group.category === preview.id) : undefined;
  const activeGroup = previewGroup ?? groups.find(group => group.category === active);
  const isMuted = (category: string) => activeGroup != null && activeGroup.category !== category;
  const previewLabel = previewed && (preview?.kind === 'type' ? t(`debt.lenders.${previewed.id as LenderType}`)
    : t('debt.lenders.instrument_number').replace('{number}', String(previewParts.indexOf(previewed) + 1)));
  const previewShare = previewed && (preview?.kind === 'type'
    ? formatOuterShare(previewed.share) : formatLenderShare(previewed.share));

  return (
    <figure className={styles.composition} aria-label={t('debt.lenders.composition')}>
      <div className={styles.donut} data-debt-donut>
        <svg viewBox='0 0 280 280' aria-hidden='true' focusable='false'>
          <g data-outer-ring>
            <Ring portions={typeParts} radius={OUTER_RADIUS} kind='type' onPreview={setPreview}
              active={preview?.kind === 'type' ? preview.id : activeGroup?.type} />
          </g>
          <g data-inner-ring>
            <Ring portions={groupParts} radius={INNER_RADIUS} kind='group' onPreview={setPreview} active={activeGroup?.category} />
          </g>
          <g>
            {groupParts.map(({ id, start, share }, index) => {
              if (share < 7) return null;
              const angle = 2 * Math.PI * (start + share / 2) / 100 - Math.PI / 2;
              const x = CENTER + INNER_RADIUS * Math.cos(angle);
              const y = CENTER + INNER_RADIUS * Math.sin(angle);
              return <g key={id} className={styles.ringKey}>
                <circle cx={x} cy={y} r={9} />
                <text x={x} y={y} textAnchor='middle' dominantBaseline='central'>{index + 1}</text>
              </g>;
            })}
          </g>
        </svg>
        <div className={styles.center} data-donut-center>
          <span>{previewLabel || t(usesPrincipal ? 'debt.lenders.total_shown' : 'debt.lenders.total_owed')}</span>
          <strong>{fmtKES(previewed?.outstanding ?? total)}</strong>
          <span>{previewed ? `${previewShare}%`
            : t(groups.length === 1 ? 'debt.lenders.category_count_one' : 'debt.lenders.category_count').replace('{count}', count)}</span>
        </div>
      </div>
      <div className={styles.compositionReadout}>
        <ul className={styles.typeLegend} data-previewing={previewGroup != null}
          role='list' aria-label={t('debt.lenders.ring_type')}>
          {typeParts.map(({ id, color, share, outstanding }) => (
            <li key={id}>
              <span className={styles.swatch} style={{ backgroundColor: color }} aria-hidden='true' />
              {t(`debt.lenders.${id as LenderType}`)} · {formatOuterShare(share)}% · {fmtKES(outstanding)}
            </li>
          ))}
        </ul>
        {previewGroup && <div className={styles.pointerReadout} data-composition-preview aria-hidden='true'>
          <strong>{previewGroup.name}</strong>
          <span>{fmtKES(previewGroup.outstanding)} · {formatLenderShare(previewGroup.share)}%</span>
        </div>}
      </div>
      <div className='space-y-2'>
        <h3 className='text-base font-semibold text-neutral-text'>{t('debt.lenders.instruments')}</h3>
        <div className={styles.stack} data-instrument-share-bar aria-hidden='true'>
          {groups.map(({ category, color, share }, index) => (
            <span key={category} className={styles.segment} data-key={category} data-muted={isMuted(category)}
              onPointerEnter={event => { if (event.pointerType === 'mouse') setPreview({ kind: 'group', id: category }); }}
              onPointerLeave={() => setPreview(null)}
              style={{ flexBasis: `${share}%`, '--segment-fill': color } as CSSProperties}>
              <span className={styles.segmentLabel}>{index + 1}
                <span className={styles.segmentShare}> · {formatLenderShare(share)}%</span>
              </span>
            </span>
          ))}
        </div>
      </div>
    </figure>
  );
}
