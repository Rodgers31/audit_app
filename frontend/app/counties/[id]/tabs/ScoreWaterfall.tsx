'use client';

import { useEffect, useRef, useState, type CSSProperties } from 'react';
import ChartReadout, { useChartReadout } from '@/components/charts/ChartReadout';
import { useLang } from '@/lib/i18n/LangProvider';
import type { Lang } from '@/lib/i18n/messages';
import type { AccountabilityScorecard } from '@/types';
import { SCORE_MESSAGES } from './scoreMessages';
import styles from './ScoreWaterfall.module.css';

// The published method and the point-delta contract both define this base.
const START_POINTS = 100;
const AXIS_WIDTH = 25;
const MIN_TARGET = 44;
const ENDPOINT_WIDTH = 31;
const COLUMN_GAP = 5;

type ScoreStep = {
  label: string;
  detail: string;
  before: number;
  after: number;
  points: number;
  impact: 'minor' | 'moderate' | 'major';
};

export function getScoreSteps(data: AccountabilityScorecard): ScoreStep[] | null {
  const { accountability_grade: grade, accountability_score: score, grade_factors: factors } = data;
  if (
    !('unresolved_findings_count_reason' in data) ||
    data.unresolved_findings_count_reason !== 'resolution_status_not_published' ||
    data.unresolved_findings_count !== null ||
    data.evidence_basis !== 'publishable_findings' ||
    typeof grade !== 'string' || !/^[ABCDF]$/.test(grade) ||
    !Number.isSafeInteger(score) || !Array.isArray(factors) || !factors.length
  ) {
    return null;
  }

  let remaining = START_POINTS;
  const steps: ScoreStep[] = [];
  for (const factor of factors) {
    if (!factor) return null;
    const { label, detail, impact, points } = factor;
    // The API emits this zero-point row when no penalty applies.
    if (factors.length === 1 && impact === 'positive' && points === 0) continue;
    if (
      (impact !== 'minor' && impact !== 'moderate' && impact !== 'major') ||
      typeof points !== 'number' || !Number.isSafeInteger(points) ||
      points >= 0 || typeof label !== 'string' || !label.trim() ||
      typeof detail !== 'string' || !detail.trim()
    ) {
      return null;
    }

    const after = remaining + points;
    // The backend floors its score at zero. A deduction through the floor
    // cannot be shown at its full size within the approved 0–100 plot.
    if (after < 0) return null;
    steps.push({ label, detail, before: remaining, after, points, impact });
    remaining = after;
  }
  return remaining === score ? steps : null;
}

// The response publishes display labels but has no factor IDs or short labels.
// Match the currently documented full labels for the chart caption only.
// The rule readout and table always keep the API’s full label.
const STEP_LABELS = [
  ['found', /^(\d+) audit findings(?: \(>\d+\))?$/],
  ['serious', /^(\d+) critical findings?$/],
  ['repeat', /^(\d+) recurring query types$/],
  ['flagged', /^(\d+(?:\.\d+)?%) of budget flagged$/],
  ['spent', /^(\d+%) budget absorption$/],
  ['opinion', /^Adverse \/ disclaimer opinion \((\d{4})\)$/],
  ['opinion', /^Qualified opinion \(latest FY\)$/],
] as const;

function chartLabel(label: string, lang: Lang) {
  for (const [key, pattern] of STEP_LABELS) {
    const match = pattern.exec(label);
    if (match) return { name: SCORE_MESSAGES[key][lang], measurement: match[1] };
  }
  return { name: label };
}

export default function ScoreWaterfall({
  county, score, grade, steps,
}: {
  county: string;
  score: number;
  grade: string;
  steps: readonly ScoreStep[];
}) {
  const { lang, t } = useLang();
  const readout = useChartReadout();
  const plot = useRef<HTMLDivElement>(null);
  const [compact, setCompact] = useState(false);
  const deductionCount = steps.length;

  useEffect(() => {
    const element = plot.current;
    if (!element) return;
    const minimumWidth =
      AXIS_WIDTH + 2 * ENDPOINT_WIDTH + MIN_TARGET * deductionCount + COLUMN_GAP * (deductionCount + 1);
    const measure = () => setCompact(element.clientWidth < minimumWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [deductionCount]);

  const copy = SCORE_MESSAGES;
  const startLabel = copy.start[lang];
  const scoreLabel = t('county.acct.score_label');
  const points = t('county.acct.pt_suffix');
  const final = `${score} · ${grade}`;
  const caption = copy.takeaway[lang]
    .replace('{start}', String(START_POINTS))
    .replace('{deductions}', String(START_POINTS - score))
    .replace('{score}', String(score))
    .replace('{grade}', grade)
    .replace('{county}', county);
  const factors = steps.map((step, index) => ({
    id: String(index),
    label: step.label,
    value: `−${-step.points} ${points} · ${step.detail} · ${copy.remaining[lang]
      .replace('{points}', String(step.after)).replace('{start}', String(START_POINTS))}`,
  }));
  const data = [
    { id: 'start', label: startLabel, value: `${START_POINTS} ${points}` },
    ...factors,
    { id: 'score', label: scoreLabel, value: final },
  ];
  const position = (before: number, after: number): CSSProperties => ({
    '--bar-from': `${after}%`,
    '--bar-size': `${before - after}%`,
  } as CSSProperties);

  return (
    <div className={styles.chart}>
      <ChartReadout
        takeaway={caption}
        columns={[copy.deduction[lang], copy.rule[lang]]}
        data={data}
        activeId={readout.activeId}>
        <div
          ref={plot}
          className={styles.plot}
          data-layout={compact ? 'rows' : 'columns'}
          data-no-deductions={deductionCount === 0}
          style={{
            '--axis-width': `${AXIS_WIDTH}px`,
            '--endpoint-width': `${ENDPOINT_WIDTH}px`,
            '--min-target': `${MIN_TARGET}px`,
            '--column-gap': `${COLUMN_GAP}px`,
            '--deduction-count': deductionCount,
          } as CSSProperties}>
          <div className={styles.axis} aria-hidden='true'>
            {[0, 50, START_POINTS].map(tick => <span key={tick} style={{ '--tick': `${tick}%` } as CSSProperties}>{tick}</span>)}
          </div>
          <div className={styles.steps}>
            <div className={styles.step} aria-hidden='true'>
              <span className={styles.mark} style={position(START_POINTS, 0)} data-impact='start'>
                <span className={styles.number}>{START_POINTS}</span>
                <span className={styles.bar} />
              </span>
              <span className={styles.label} data-short>{compact ? startLabel : copy.start_chart[lang]}</span>
            </div>
            {steps.map((step, index) => {
              const datum = factors[index];
              const signedPoints = `−${-step.points}`;
              const captionLabel = compact ? { name: step.label } : chartLabel(step.label, lang);
              return (
                <button
                  key={datum.id}
                  className={styles.step}
                  {...readout.trigger(datum, t('foundation.no_chart_value'))}
                  aria-label={undefined}>
                  <span className={styles.mark} style={position(step.before, step.after)} data-impact={step.impact}>
                    <span className={styles.number}>{signedPoints}</span>
                    <span className={styles.bar} />
                  </span>
                  {' '}
                  <span className={styles.label} data-short={captionLabel.name !== step.label || undefined}>
                    {captionLabel.name}
                    {captionLabel.measurement && <span className={styles.measurement}> {captionLabel.measurement}</span>}
                  </span>
                </button>
              );
            })}
            <div className={styles.step} aria-hidden='true'>
              <span className={styles.mark} style={position(score, 0)} data-impact='score'>
                <span className={styles.number}>{final}</span>
                <span className={styles.bar} />
              </span>
              <span className={styles.label} data-short>{scoreLabel}</span>
            </div>
          </div>
        </div>
        {deductionCount > 0 && <p className='text-sm text-neutral-muted'>{copy.hint[lang]}</p>}
      </ChartReadout>
    </div>
  );
}
