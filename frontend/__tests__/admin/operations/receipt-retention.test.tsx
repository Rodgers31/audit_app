import { render, screen } from '@testing-library/react';
import ReceiptRetention from '@/components/admin/ReceiptRetention';
import { parseReceiptRetention, parseIngestionJob } from '@/lib/admin/ingestion';

const missing = {state:'missing_bytes', observed:2, retained:1, missing:1, recovered:1, retry_requests:2};

test('a completed job cannot hide missing source bytes', () => {
  render(<ReceiptRetention metadata={{receipt_retention:missing}} />);
  expect(screen.getByRole('status')).toHaveTextContent('Source evidence needs attention');
  expect(screen.getByText(/Observed 2/)).toHaveTextContent('Verified 1 · Unconfirmed 1');
  expect(screen.getByText(/Recovered after retry/)).toHaveTextContent('Additional requests 2');
});

test.each([undefined, null, {}, {...missing, observed:true}, {...missing, state:'confirmed'},
  {...missing, missing:-1}, {...missing, retained:3}, {...missing, recovered:2},
  {...missing, retry_requests:NaN}, {...missing, retry_requests:1000001}, {...missing, private:'SECRET'}])('unknown or invalid evidence never becomes a healthy zero: %j', raw => {
  expect(parseReceiptRetention(raw)).toEqual({state:'unverified'});
  render(<ReceiptRetention metadata={{receipt_retention:raw}} />);
  expect(screen.getByRole('status')).toHaveTextContent('outcome is unknown');
  expect(screen.queryByText(/SECRET|Verified 0|passed storage readback/)).not.toBeInTheDocument();
});

test('retrying an all-retained set must have recovered a capture', () => {
  expect(parseReceiptRetention({state:'confirmed',observed:1,retained:1,missing:0,recovered:0,retry_requests:1})).toEqual({state:'unverified'});
});

test('the real job parser passes only the safe retention summary to the panel', () => {
  const job = parseIngestionJob({id:1,domain:'pending_bills',status:'completed',dry_run:false,
    started_at:null,finished_at:null,created_at:null,duration_seconds:null,
    items_processed:48,items_created:0,items_updated:48,errors:[],error_count:0,diagnostics_redacted:true,
    metadata:{receipt_retention:missing,provider_payload:'PRIVATE'}});
  expect(job.metadata).toEqual({receipt_retention:missing});
  render(<ReceiptRetention metadata={job.metadata}/>);
  expect(screen.getByRole('status')).toHaveTextContent('Source evidence needs attention');
  expect(screen.queryByText(/PRIVATE/)).not.toBeInTheDocument();
});

test('an empty scope is not a retention qualification', () => {
  render(<ReceiptRetention metadata={{receipt_retention:{state:'not_observed',observed:0,retained:0,missing:0,recovered:0,retry_requests:0}}} />);
  expect(screen.getByRole('status')).toHaveTextContent('Storage retention was not qualified');
});

test('confirmed means all observed captures passed byte verification', () => {
  render(<ReceiptRetention metadata={{receipt_retention:{state:'confirmed',observed:2,retained:2,missing:0,recovered:1,retry_requests:1}}} />);
  expect(screen.getByRole('status')).toHaveTextContent('All observed source captures passed storage readback');
});
