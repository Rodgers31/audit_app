"""Fail-closed interpretation of a nonempty, measured shared-worker workload."""
import math
from datetime import datetime


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, *, positive=False):
    require(type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0), 'Invalid measured number')
    return value


def integer(value, *, positive=False):
    require(type(value) is int and (value > 0 if positive else value >= 0), 'Invalid measured integer')
    return value


def counter(value):
    require(type(value) is str and value.isascii() and value.isdecimal(), 'Invalid cgroup counter')
    return int(value)


def pairs(starts, completed, window_start, window_end):
    require(starts and completed, 'Operation observations absent')
    require(all(type(row.get('request_id')) is str and row['request_id'] for row in starts),
            'Operation request identity absent')
    by_id = {row['request_id']: row for row in starts}
    require(len(by_id) == len(starts), 'Duplicate operation start identity')
    completed_ids = [row.get('request_id') for row in completed]
    require(all(type(value) is str and value in by_id for value in completed_ids)
            and len(set(completed_ids)) == len(completed_ids), 'Unmatched/duplicate operation completion')
    require(set(completed_ids) == set(by_id), 'Incomplete operation observations')
    require(all(window_start <= number(row['started'], positive=True) <= window_end for row in starts),
            'Operation start outside measured API window')
    for row in completed:
        start = by_id[row['request_id']]
        require(type(start.get('path')) is str and start['path'] == row.get('path')
                and number(start['started'], positive=True)
                <= number(row.get('completed'), positive=True) <= window_end,
                'Operation path/order outside measured API window')
    return [(by_id[row['request_id']], row) for row in completed]


def statement_counts(rows):
    require(type(rows) is list, 'Missing SQL snapshot')
    counts = {}
    for row in rows:
        require(type(row) is dict and type(row.get('query')) is str and row['query']
                and row['query'] not in counts, 'Invalid/duplicate SQL fingerprint')
        counts[row['query']] = integer(row['calls'])
    return counts


def wire_failure_free(before, after):
    require(type(before) is dict and type(after) is dict, 'Missing wire observation')
    for wire in (before, after):
        integer(wire.get('upstream_failures'))
    require(after['upstream_failures'] == before['upstream_failures'],
            'Upstream connection failure during measurement')


def assess(samples, latencies, census, wire_before, wire_after, requests, duration, thresholds):
    require(type(samples) is list and len(samples) >= 20, 'Insufficient cgroup samples')
    require(type(latencies) is list and len(latencies) >= thresholds['minimum_api_requests'], 'Insufficient API requests')
    require(number(duration, positive=True) >= thresholds['duration_seconds'], 'Insufficient sustained duration')
    previous_time, previous_cpu = -1, -1
    roles = None
    for sample in samples:
        require(type(sample) is dict, 'Invalid cgroup sample')
        current = integer(sample['memory'], positive=True)
        peak = integer(sample['peak'], positive=True)
        require(current <= peak <= thresholds['memory_peak_bytes'], 'Memory reserve failed')
        elapsed = number(sample['elapsed'], positive=True)
        usage = counter(sample['cpu']['usage_usec'])
        require(elapsed > previous_time and usage >= previous_cpu, 'Nonmonotonic observation')
        require(counter(sample['oom']['oom_kill']) == 0, 'OOM observed')
        processes = sample['processes']
        require(type(processes) is list and processes, 'Missing actual process census')
        workers, web, supervisor = [], [], []
        for process in processes:
            integer(process['pid'], positive=True)
            integer(process['rss'], positive=True)
            integer(process['threads'], positive=True)
            argv = process['argv']
            require(type(argv) is list and argv and all(type(v) is str for v in argv), 'Invalid process argv')
            if 'social.worker' in argv:
                require(process['threads'] <= 3, 'Native worker exceeded main plus two executor threads')
                workers.append(process['pid'])
            if 'main:app' in argv and any('gunicorn' in arg for arg in argv):
                web.append(process['pid'])
            if 'social_worker_supervisor' in argv:
                supervisor.append(process['pid'])
        require(len(workers) == 1 and web and supervisor == [1]
                and workers[0] != 1 and workers[0] not in web and 1 not in web,
                'Distinct real shared processes absent')
        current_roles = (workers[0], tuple(sorted(web)), supervisor[0])
        if roles is None:
            roles = current_roles
        require(current_roles[0] == roles[0] and current_roles[2] == roles[2], 'Native/supervisor identity changed')
        previous_time, previous_cpu = elapsed, usage
    require(samples[0]['elapsed'] <= 15 and duration - samples[-1]['elapsed'] <= 15
            and samples[-1]['elapsed'] <= duration
            and samples[-1]['elapsed'] - samples[0]['elapsed'] >= duration - 30,
            'Cgroup samples do not cover the sustained workload')
    cpu = (counter(samples[-1]['cpu']['usage_usec']) - counter(samples[0]['cpu']['usage_usec'])) / 1e6 / (
        samples[-1]['elapsed'] - samples[0]['elapsed'])
    require(0 < cpu <= thresholds['steady_mean_cpu'], 'Steady CPU threshold failed')
    p95 = sorted(number(v, positive=True) for v in latencies)[math.ceil(len(latencies) * .95) - 1]
    require(p95 <= thresholds['api_p95_seconds'] and max(latencies) <= thresholds['api_max_seconds'], 'API latency threshold failed')
    require(type(census) is dict and 1 <= integer(census['connections']) <= thresholds['worker_connections'], 'Native connections absent/over budget')
    targets = census['social_post_targets']
    require(type(targets) is list and len(targets) >= 6, 'Insufficient real native workload')
    before_counts = statement_counts(census.get('statements_before'))
    after_counts = statement_counts(census['statements'])
    require(before_counts and after_counts, 'Empty SQL measurement baseline/final snapshot')
    require(all(after_counts.get(query, -1) >= calls for query, calls in before_counts.items()),
            'SQL counters reset/disappeared during measurement')
    sql_calls = sum(calls - before_counts.get(query, 0) for query, calls in after_counts.items())
    require(sql_calls > 0, 'No server statements within measurement')
    for wire in (wire_before, wire_after):
        require(type(wire) is dict, 'Missing wire observation')
        for key in ('server_bytes', 'client_bytes', 'connections', 'active', 'peak_active', 'upstream_failures'):
            integer(wire[key])
        require(0 <= wire['active'] <= wire['peak_active'] <= wire['connections']
                and 1 <= wire['peak_active'] <= thresholds['worker_connections'],
                'Observed connection counters inconsistent/over ceiling')
    wire_failure_free(wire_before, wire_after)
    received = wire_after['server_bytes'] - wire_before['server_bytes']
    sent = wire_after['client_bytes'] - wire_before['client_bytes']
    require(wire_after['connections'] >= wire_before['connections']
            and wire_after['peak_active'] >= wire_before['peak_active'], 'Nonmonotonic wire counters')
    require(0 < received <= thresholds['busy_server_bytes']
            and 0 < sent <= thresholds['busy_client_bytes'], 'Worker wire transfer absent/unbounded')
    require(type(requests) is list and requests, 'Missing real provider/storage operations')
    window_start = number(wire_before.get('measurement_started'), positive=True)
    window_end = number(wire_after.get('measurement_completed'), positive=True)
    require(window_start < window_end and duration - 5 <= window_end - window_start <= duration + 15,
            'Actual measured API window absent/inconsistent')
    wall_start = number(wire_before.get('wall_started'), positive=True)
    wall_end = number(wire_after.get('wall_completed'), positive=True)
    require(wall_start < wall_end and abs((wall_end-wall_start)-(window_end-window_start)) <= 2,
            'Publication clock window inconsistent')
    cohort = census.get('cohort')
    require(type(cohort) is dict and type(cohort.get('run_id')) is str and cohort['run_id']
            and cohort.get('case') == 'capacity' and type(cohort.get('target_id')) is str
            and cohort['target_id'], 'Run/case/target binding absent')
    for key in ('media_paths', 'provider_paths'):
        require(type(cohort.get(key)) is list and cohort[key]
                and all(type(path) is str and path.startswith('/') for path in cohort[key]),
                'Target path binding absent')
    published_rows = [row for row in targets if row['state'] == 'published']
    require(len(published_rows) >= thresholds['minimum_published']
            and any(row.get('id') == cohort['target_id'] for row in published_rows),
            'Bound native image target did not publish')
    for row in published_rows:
        require(type(row.get('published_at')) is str, 'Publication completion absent')
        completed_at = datetime.fromisoformat(row['published_at'])
        require(completed_at.tzinfo is not None and wall_start <= completed_at.timestamp() <= wall_end,
                'Publication completion outside measured window')
    published = len(published_rows)
    require(all(type(row) is dict and row.get('run_id') == cohort['run_id']
                and row.get('case') == cohort['case'] for row in requests),
            'Foreign run/case operation observation')
    posts = [row for row in requests if row.get('method') == 'POST' and 'started' in row]
    completed = [row for row in requests if row.get('method') == 'POST' and 'completed' in row]
    require(len(posts) >= 6 and len(completed) >= 6, 'Sustained provider mutations absent')
    require(all(row.get('path') in cohort['provider_paths'] for row in [*posts, *completed]),
            'Provider operation targets another account/path')
    mutations = pairs(posts, completed, window_start, window_end)
    started = [start['started'] for start, _ in mutations]
    require(max(started) - min(started) >= thresholds['minimum_busy_span_seconds'], 'Worker activity did not span workload')
    downloads = [row for row in requests if row.get('method') == 'GET'
                 and row.get('path', '').startswith('/media-test/') and 'output_bytes' in row]
    starts = [row for row in requests if row.get('method') == 'GET'
              and row.get('path', '').startswith('/media-test/') and 'started' in row]
    require(all(row.get('path') in cohort['media_paths'] for row in [*starts, *downloads]),
            'SDK operation targets another publication asset')
    media = pairs(starts, downloads, window_start, window_end)
    require(all(0 < integer(row['output_bytes']) <= 8_000_000 for _, row in media),
            'Actual bounded SDK media transfer absent')
    return dict(api_p95=p95, mean_cpu=cpu, published=published,
                server_bytes=received, client_bytes=sent, provider_mutations=len(completed), sql_calls=sql_calls)
