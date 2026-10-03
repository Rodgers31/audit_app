import { isRoundNumberEstimate } from '@/components/dashboard/NationalDebtCard';
import fixture from '../fixtures/figure-qualifications.json';
import type { Qualifications } from '@/lib/evidence/qualification';
const real = fixture.debt_timeline.qualifications as Qualifications;
it('does not infer model origin from round quantities, including zero', () => {
 expect(isRoundNumberEstimate({external:1500,domestic:1600,total:3100})).toBe(false);
 expect(isRoundNumberEstimate({external:0,domestic:0,total:0,qualifications:real})).toBe(false);
});
it('uses explicit origin even for non-round values', () => {
 expect(isRoundNumberEstimate({external:1501.25,domestic:1602.4,total:3103.65,qualifications:{...real,total:{...real.total,status:'modelled'}}})).toBe(true);
});
