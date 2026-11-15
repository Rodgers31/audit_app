#!/usr/bin/env bash
# Create the model-only databases for the PostgreSQL refresh and fiscal tests.
set -euo pipefail

state="$RUNNER_TEMP/nightly-test-fixture.cid"
image='public.ecr.aws/docker/library/postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3'
if [[ ${1:-} == cleanup ]]; then
  if [[ -f $state ]]; then
    read -r cid < "$state"
    [[ $cid =~ ^[a-f0-9]{64}$ ]]
    [[ $(docker inspect --format '{{index .Config.Labels "audit.fixture"}}' "$cid") == nightly-ci ]]
    docker rm --force --volumes "$cid" >/dev/null
    rm -- "$state"
  fi
  exit 0
fi
[[ ${1:-} == prepare && ! -e $state ]]
token=$(python -c 'import secrets; print(secrets.token_hex(16))')

# The test verifies inet_server_addr() and inet_server_port(). Use the
# job runner's loopback directly, with no bridge address or published proxy.
docker run --detach --pull=never --network host --label audit.fixture=nightly-ci \
  --tmpfs /var/lib/postgresql/data --env POSTGRES_HOST_AUTH_METHOD=trust \
  --env POSTGRES_DB=auditgava_refresh_fixture "$image" \
  -p 55432 -c listen_addresses=127.0.0.1 > "$state"
read -r cid < "$state"
[[ $cid =~ ^[a-f0-9]{64}$ ]]

for _ in {1..45}; do
  if docker exec "$cid" pg_isready -q -h /var/run/postgresql -p 55432; then break; fi
  sleep 1
done
# Mark only the server reachable through this container's own socket. The
# image's temporary initialization server uses the default port/socket suffix.
docker exec -i "$cid" psql -X -h /var/run/postgresql -p 55432 -U postgres -d postgres \
  -v ON_ERROR_STOP=1 -v marker="nightly-acceptance-owned-v1:$token" <<'SQL'
CREATE DATABASE fiscal_fixture;
COMMENT ON DATABASE auditgava_refresh_fixture IS :'marker';
COMMENT ON DATABASE fiscal_fixture IS :'marker';
SQL
{
  printf 'REFRESH_FIXTURE_PG_URL=postgresql+psycopg2://postgres@127.0.0.1:55432/auditgava_refresh_fixture\n'
  printf 'REFRESH_FIXTURE_OWNED=true\nREFRESH_FIXTURE_TOKEN=%s\n' "$token"
  printf 'FISCAL_TEST_POSTGRES_URL=postgresql+psycopg2://postgres@127.0.0.1:55432/fiscal_fixture\n'
} >> "$GITHUB_ENV"
