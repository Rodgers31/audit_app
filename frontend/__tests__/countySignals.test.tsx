import { render, screen } from '@testing-library/react';
import React from 'react';
import { AuditStatusSignal, gradeSignal } from '@/app/counties/CountySignals';

describe('County signal meaning', () => {
  it('keeps the health and audit B bands distinct', () => {
    expect(gradeSignal('B', 'health')).toEqual({
      tone: 'watch',
      labelKey: 'county.acct.grade_fair',
    });
    expect(gradeSignal('B', 'audit')).toEqual({
      tone: 'positive',
      labelKey: 'county.acct.grade_good',
    });
    expect(gradeSignal('D', 'audit')).toEqual({
      tone: 'concern',
      labelKey: 'county.acct.grade_needs_improvement',
    });
    expect(gradeSignal('C', 'health')).toEqual({
      tone: 'critical',
      labelKey: 'county.acct.grade_poor',
    });
  });

  it.each([null, undefined, '', 'unknown', 'D', '__proto__', 'constructor'])(
    'treats unavailable or unsupported health grade %s as unassessed',
    (grade) => {
      expect(gradeSignal(grade, 'health')).toEqual({
        tone: 'unavailable',
        labelKey: 'county.acct.grade_ungraded',
      });
    }
  );

  it.each([
    ['clean', 'positive'],
    ['Unqualified', 'positive'],
    ['Qualified', 'watch'],
    ['Adverse', 'critical'],
    ['Disclaimer', 'critical'],
    ['pending', 'unavailable'],
    ['unknown', 'unavailable'],
    [null, 'unavailable'],
    [undefined, 'unavailable'],
    ['__proto__', 'unavailable'],
    ['constructor', 'unavailable'],
  ])('preserves the displayed opinion and distinguishes %s', (status, tone) => {
    render(<AuditStatusSignal status={status} label='Published opinion label' />);
    expect(screen.getByText('Published opinion label')).toHaveAttribute('data-tone', tone);
  });
});
