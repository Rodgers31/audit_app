import { parseIngestionJob, ingestionAge, formatIngestionTime } from '@/lib/admin/ingestion';
const job={id:1,domain:'imf_weo',status:'completed',dry_run:false,
  started_at:'2026-10-27T04:38:48',finished_at:'2026-10-27T04:39:18',created_at:'2026-10-27T04:38:47',
  duration_seconds:30,items_processed:188,items_created:0,items_updated:0,
  errors:[],error_count:0,diagnostics_redacted:true,metadata:{}};

test('legacy known-UTC timestamps become explicit before Date parsing',()=>{
  const parsed=parseIngestionJob(job);
  expect(parsed.started_at).toBe('2026-10-27T04:38:48Z');
  expect(parsed.finished_at).toBe('2026-10-27T04:39:18Z');
  expect(parsed.created_at).toBe('2026-10-27T04:38:47Z');
  expect(Date.parse(parsed.started_at!)).toBe(Date.UTC(2026,9,27,4,38,48));
});

test('pending unknown times stay unknown',()=>{
  const parsed=parseIngestionJob({...job,status:'pending',started_at:null,finished_at:null,created_at:null,duration_seconds:null});
  expect(parsed.started_at).toBeNull();expect(parsed.finished_at).toBeNull();expect(parsed.created_at).toBeNull();
});


test.each(['2026-02-30T01:00:00','2026-10-27T25:00:00Z','2026-10-27T04:38:48+24:00','NaN','',null,undefined])('unknown/invalid displays never invent an age: %s',value=>{
  expect(ingestionAge(value)).toBe('—');expect(formatIngestionTime(value)).toBe('—');
});

test('relative ages use instants across zones, DST and future clocks',()=>{
  const now=Date.UTC(2026,10,1,8,30);
  expect(ingestionAge('2026-11-01T01:30:00-05:00',now)).toBe('2h ago');
  expect(ingestionAge('2026-11-01T01:30:00-06:00',now)).toBe('1h ago');
  expect(ingestionAge('2026-11-01T09:35:00Z',now)).toBe('in 1h');
  expect(ingestionAge('2026-11-01T08:30:00Z',Number.NaN)).toBe('—');
});

test.each([
  ['UTC','Oct 27, 2026, 04:38 AM UTC'],
  ['America/Chicago','Oct 26, 2026, 11:38 PM CDT'],
  ['Europe/Helsinki','Oct 27, 2026, 06:38 AM GMT+2'],
])('absolute rendering names the intended local zone: %s',(zone,expected)=>{
  expect(formatIngestionTime('2026-10-27T04:38:48',zone).replace(/\u202f/g,' ')).toBe(expected);
});

test('fall-back repeated civil hours remain distinguishable',()=>{
  expect(formatIngestionTime('2026-11-01T06:30:00Z','America/Chicago')).toContain('01:30 AM CDT');
  expect(formatIngestionTime('2026-11-01T07:30:00Z','America/Chicago')).toContain('01:30 AM CST');
});
