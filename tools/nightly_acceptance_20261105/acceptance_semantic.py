"""Supported local semantic importer, with explicit unmet operational authorities.

Unlike the structural envelope reader, this opens only an ownership-checked
read-only fixture session and runs the actual domain/catalog/HMAC adapters.
It cannot authorize deployment, source adoption or a hosted success claim.
"""
from datetime import datetime, timezone
from pathlib import Path
import sys

from common import BoundEvidence, fields, integer, loads, require, sha256
from acceptance_backend_config import validate_config
from acceptance_database import observe_catalog, observe_current_run
from acceptance_authority import observe_oag_acquisition, observe_oag_report, observe_fiscal_debt
from acceptance_refresh import binding, verify_capture
from acceptance_refresh_v2 import CONTEXT, PROTOCOL, load_refresh_json, verify_v2
from operational import CONTRACT, artifact, read_artifact

LEGACY_PROTOCOL = 'nightly-refresh-capture-v1'
PROTOCOLS = {'nightly-semantic-local-input-v1': LEGACY_PROTOCOL,
             'nightly-semantic-local-input-v2': PROTOCOL}


def observe(path, *, backend_config, signing_key_file, expected_refresh_protocol=None):
    backend = str(Path(__file__).absolute().parents[2] / 'backend')
    if backend not in sys.path: sys.path.insert(0, backend)
    from tests.acceptance_owned_pg import owned_reader
    with BoundEvidence() as originals:
        config = validate_config(originals.json(backend_config))
        value = originals.json(path)
        fields(value, ('schema', 'kind', 'binding', 'plan', 'context', 'current_report', 'pg_schema',
                       'refresh', 'census', 'oag', 'fiscal'))
        schema = value['schema']
        require(type(schema) is str and schema in PROTOCOLS, 'unknown semantic input')
        protocol = PROTOCOLS[schema]
        require(expected_refresh_protocol is None or expected_refresh_protocol == protocol,
                'semantic refresh protocol does not meet the requested version')
        is_v2 = protocol == PROTOCOL
        key = originals.read(signing_key_file, private=is_v2, maximum_bytes=65536 if is_v2 else 1024)
        binding(value['binding'])
        root = Path(path).absolute().parent
        def original(reference): return artifact(reference, root, originals)
        plan = loads(read_artifact(value['plan'], root, originals, maximum_bytes=65536))
        context = loads(read_artifact(value['context'], root, originals, maximum_bytes=65536))
        report = read_artifact(value['current_report'], root, originals, maximum_bytes=65536)
        census_raw = read_artifact(value['census'], root, originals, private=is_v2, maximum_bytes=65536)
        census = load_refresh_json(census_raw) if is_v2 else loads(census_raw)
        require(type(context) is dict and context.get('source_sha') == value['binding']['commit']
                and context.get('run_id') == str(value['binding']['run_id'])
                and context.get('run_attempt') == str(value['binding']['attempt']),
                'semantic manifest/current-run identity differs')
        if is_v2:
            bundle = load_refresh_json(read_artifact(value['refresh'], root, originals,
                                                    private=True, maximum_bytes=16384))
        else:
            refresh = verify_capture(original(value['refresh']), secret=key,
                                     expected_binding=value['binding'], expected_census=census)
        require(type(value['oag']) is list and len(value['oag']) <= 11, 'bounded exact OAG observation inventory required')
        oag, identities = [], set()
        revision = originals.json(CONTRACT)['schema_revision']
        with owned_reader(value['pg_schema'], token=config['fixture_token']) as session:
            catalog = observe_catalog(session, ['ingestion_jobs'], expected_revision=revision, expected_role='postgres')
            current = observe_current_run(session, plan, context, report, kind=value['kind'])
            if is_v2:
                expected_context = {field: current['report'][field] for field in CONTEXT}
                require(expected_context['schema_head'] == catalog['revision'], 'refresh and catalog schema differ')
                finished = datetime.strptime(context['cli_finished'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
                refresh = verify_v2(originals=originals, root=root, bundle=bundle, witness=census,
                                    secret=key, expected_context=expected_context,
                                    not_before=int(finished.timestamp()))
            audit_jobs = [row['job_id'] for row in current['report']['jobs'] if row['domain'] == 'audits']
            require(len(audit_jobs) == 1, 'exact current-run audits job required')
            for item in value['oag']:
                fields(item, ('scope', 'job_id', 'source_id', 'record_id', 'original', 'retained'))
                require(integer(item['job_id'], 1) == audit_jobs[0], 'OAG authority belongs to another job/run')
                integer(item['source_id'], 1)
                integer(item['record_id'], 1)
                require(item['source_id'] not in identities, 'duplicate OAG source identity')
                identities.add(item['source_id'])
                args = dict(job_id=item['job_id'], original_pdf=original(item['original']), retained_pdf=original(item['retained']))
                if item['scope'] == 'acquisition':
                    observation = observe_oag_acquisition(session, source_id=item['source_id'], validation_id=item['record_id'], **args)
                else:
                    require(item['scope'] == 'publication', 'unknown OAG authority scope')
                    observation = observe_oag_report(session, record_id=item['record_id'], **args)
                    require(observation['source_document_id'] == item['source_id'], 'OAG publication source differs')
                oag.append(observation)
            fiscal = None
            if value['fiscal'] is not None:
                fields(value['fiscal'], ('fiscal_years', 'debt_years'))
                fiscal = observe_fiscal_debt(session, **value['fiscal'])
        holds = ['final-native-runtime', 'final-source-adoption-authority', 'frozen-oag-edition-inventory', 'actual-cli-execution-identity',
                 'actual-frontend-rendered-values', 'hosted-full15-daily-weekly-replay', 'independent-container-cleanup']
        if len(oag) != 11 or any(row.get('publication_authority') is False for row in oag):
            holds.append('eleven-oag-publication-and-origin-authorities')
        if fiscal is None or fiscal['final_source_schema_acceptance'] == 'pending':
            holds.append('frozen-fiscal-debt-authority-schema')
        if is_v2:
            holds += ['independent-hosted-refresh-provenance', 'deployed-serving-instance-topology']
        return {'schema': 'nightly-semantic-local-observation-v2' if is_v2 else 'nightly-semantic-local-observation-v1',
                'generated_by': str(Path(__file__).absolute()), 'generator_sha256': sha256(__file__),
                'generated_at': datetime.now(timezone.utc).isoformat(), 'binding': value['binding'],
                'catalog': catalog, 'current_run': current, 'refresh': refresh, 'oag': oag, 'fiscal': fiscal,
                'holds': holds, 'production_accepted': False,
                'verdict': 'LOCAL_SEMANTIC_OBSERVATIONS_ONLY_OPERATIONAL_GATES_PENDING'}
