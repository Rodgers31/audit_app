"""Whitelisted workflow selection; execution still uses the native CLI owner.

This plan is independent of the UI publication calendar. It does not certify
source freshness and it is not a no-write preflight (operational receipts write).
"""
from dataclasses import dataclass
import ast
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from datetime import date
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote_plus

from .registries import _BUILTIN_DOMAIN_PACKAGES

LEGACY_DOMAINS = tuple(sorted(p.rsplit('.', 1)[1] for p in _BUILTIN_DOMAIN_PACKAGES))
DAILY = '0 2 * * 1-6'
WEEKLY = '0 3 * * 0'
OAG_SOURCE_ACCEPTANCE = 'oag-combined-catalogue-20261101'
OAG_ACCEPTANCE_MANIFEST = Path(__file__).resolve().parents[2] / 'docs/operations/2026-11-01-oag-catalogue-acceptance/manifest.json'
OAG_SOURCE_ONLY_CONTROLS = ('SOCIAL_GENERATION_HOOK_ENABLED', 'SOCIAL_REPORT_GENERATION_ENABLED',
                          'SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED',
                          'SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED')

# Reading these literal contracts must not execute domain registration or the
# services package: those imports initialize database engines before admission.
_SOURCE_ROOT = Path(__file__).resolve().parent
_SOURCE_LITERALS = {
    'extractors/cog_governors.py': {'SOURCE_URL':str, 'DEPUTIES_SOURCE_URL':str},
    'domains/economic_indicators/fetcher.py': {'_WB_BASE':str, '_WB_INDICATORS':dict},
    'domains/economic_indicators/cbk_inflation.py': {'CBK_INFLATION_URL':str},
    'domains/population/fetcher.py': {'_WB_BASE':str, '_WB_POPULATION_INDICATORS':dict, '_WB_SUPPLEMENTARY':dict},
    'domains/population/census_counties.py': {'CENSUS_VOLUME_I_URL':str},
    'domains/national_gdp/fetcher.py': {'_WB_GDP_URL':str, '_WB_POVERTY_URL':str, '_POVERTY_INDICATORS':dict},
    'domains/debt_timeline/fetcher.py': {'_WB_GDP_URL':str},
    'domains/imf_weo/fetcher.py': {'_BASE_URL':str, 'INDICATORS':tuple, 'COUNTRIES':tuple},
    'domains/revenue_by_source/kra_discovery.py': {'KRA_BASE':str, 'ANNUAL_SLUG':str},
    'domains/revenue_by_source/fetcher.py': {'_WB_BASE':str, '_WB_REVENUE_INDICATORS':dict},
    'kra_report_catalogue.py': {'CATALOGUE_URL':str},
    'domains/audits/fetcher.py': {'_WP_MEDIA_SEARCHES':tuple},
    'oag_discovery.py': {'OAG_ORIGIN':str},
    'domains/counties_budget/fetcher.py': {'_COB_COUNTY_BIRR_URLS':list},
    'domains/national_debt/wb_ids.py': {'_WB_BASE':str, 'WB_IDS_CREDITORS':list},
    'domains/national_debt/wb_ids_creditors.py': {'_IDS_BASE':str, 'SERIES':dict, 'TOTAL_SERIES':str, 'EXTERNAL_TOTAL_SERIES':str},
    'domains/national_debt/fx.py': {'_WB_BASE':str, 'FX_SERIES':str},
    'domains/national_debt/cbk_web_tables.py': {'BONDS_URL':str, 'KEY_RATES_URL':str},
    'domains/cra/source.py': {'URL':str},
    'domains/opendata/source.py': {'URL':str, 'REPORT_URL':str},
    'domains/opendata/discovery.py': {'INDEX':str},
    'domains/fiscal_summary/actuals.py': {'APDMR_URL':str, 'BROP_URL':str},
}


def _literal_table_schema(name, value):
    """The inventory cannot certify an empty or wrong-entry source family."""
    if type(value) is str:
        if not value or len(value)>2048: raise ValueError('Empty/oversized source constant')
    elif type(value) is dict:
        if not 1<=len(value)<=64 or any(type(k) is not str or not k for k in value):
            raise ValueError('Empty/malformed source table')
        if name in ('_WB_POPULATION_INDICATORS','_WB_SUPPLEMENTARY','_POVERTY_INDICATORS'):
            if any(type(v) is not str or not v for v in value.values()):
                raise ValueError('Wrong source indicator entry')
        elif name=='SERIES':
            if any(type(v) is not tuple or len(v)!=2 or any(type(s) is not str or not s for s in v) for v in value.values()):
                raise ValueError('Wrong IDS source entry')
        elif name in ('_WB_INDICATORS','_WB_REVENUE_INDICATORS'):
            fields = ({'description','divisor','indicator_type','measure','round_digits','unit'}
                      if name=='_WB_INDICATORS' else {'description','revenue_type','wb_name'})
            for row in value.values():
                if type(row) is not dict or set(row)!=fields: raise ValueError('Wrong source metadata schema')
                for key,item in row.items():
                    if key in ('divisor','round_digits'):
                        if type(item) not in (int,float) or not item>=0: raise ValueError('Wrong source numeric metadata')
                    elif type(item) is not str or not item: raise ValueError('Wrong source text metadata')
    elif type(value) in (tuple,list):
        if not 1<=len(value)<=32: raise ValueError('Empty/oversized source sequence')
        if name=='WB_IDS_CREDITORS':
            for row in value:
                if (type(row) is not dict or set(row)!={'code','combine_with','lender','debt_category'}
                        or any(type(row[k]) is not str or not row[k] for k in ('code','lender','debt_category'))
                        or row['combine_with'] is not None and type(row['combine_with']) is not str):
                    raise ValueError('Wrong aggregate IDS source entry')
        elif any(type(v) is not str or not v for v in value):
            raise ValueError('Wrong source sequence entry')


def _literal_declaration_shape(tree, expected, allowed_stores):
    """Reject writes/aliases/mutators rather than returning stale declarations.

    This validates a reviewed literal-contract shape, not arbitrary Python's
    behavior. Dynamic namespace/evaluation forms are outside that contract.
    """
    def root_name(node):
        while isinstance(node,(ast.Subscript,ast.Attribute)):node=node.value
        return node.id if isinstance(node,ast.Name) else None
    readonly={'get','items','keys','values','copy','format','join','lower','upper','strip','rstrip','lstrip','replace','startswith','endswith'}
    for node in ast.walk(tree):
        if isinstance(node,ast.Name) and node.id in expected and isinstance(node.ctx,(ast.Store,ast.Del)) and id(node) not in allowed_stores:
            raise ValueError('Source constant rebound or deleted')
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and node.name in expected:
            raise ValueError('Source constant rebound by definition')
        if isinstance(node,ast.alias) and (node.asname or node.name.split('.')[0]) in expected:
            raise ValueError('Source constant rebound by import')
        if isinstance(node,(ast.Global,ast.Nonlocal)) and set(node.names)&set(expected):
            raise ValueError('Mutable source namespace refused')
        if isinstance(node,ast.ExceptHandler) and node.name in expected:
            raise ValueError('Source constant rebound by handler')
        if type(node).__name__ in ('MatchAs','MatchStar') and getattr(node,'name',None) in expected:
            raise ValueError('Source constant rebound by pattern')
        if isinstance(node,(ast.Assign,ast.AnnAssign,ast.AugAssign,ast.Delete)):
            targets=node.targets if isinstance(node,(ast.Assign,ast.Delete)) else [node.target]
            if any(not isinstance(t,ast.Name) and root_name(t) in expected for t in targets):
                raise ValueError('Source constant table/property mutation refused')
            value=getattr(node,'value',None)
            if isinstance(value,ast.Name) and value.id in expected and expected[value.id] in (dict,list):
                raise ValueError('Mutable source constant alias refused')
        if isinstance(node,ast.Call):
            if isinstance(node.func,ast.Name) and node.func.id in ('globals','locals','vars','eval','exec'):
                raise ValueError('Dynamic source namespace refused')
            if isinstance(node.func,ast.Attribute) and root_name(node.func.value) in expected and node.func.attr not in readonly:
                raise ValueError('Source constant mutator refused')


def source_literals(module):
    """Read one closed literal contract; never import/evaluate provider code."""
    if type(module) is not str or module not in _SOURCE_LITERALS:
        raise ValueError('Unknown health source literal contract')
    path = _SOURCE_ROOT / module
    if (any((_SOURCE_ROOT / Path(*Path(module).parts[:i])).is_symlink() for i in range(1,len(Path(module).parts)+1))
            or not path.is_file() or not 1 <= path.stat().st_size <= 1024 * 1024):
        raise ValueError('Source literal contract missing, linked or exceeds bound')
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except (SyntaxError,UnicodeError) as exc:
        raise ValueError('Malformed health source literal module') from exc
    expected = _SOURCE_LITERALS[module]
    found = {}
    allowed_stores=set()
    # Reject reassignment even in a branch/global-mutating helper. A source
    # changing this declaration shape needs explicit health-contract review.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign,ast.AnnAssign,ast.AugAssign)):
            targets = node.targets if isinstance(node,ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target,ast.Name) and target.id in expected:
                    if node not in tree.body or isinstance(node,ast.AugAssign) or target.id in found:
                        raise ValueError('Ambiguous/reassigned health source constant')
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError,TypeError) as exc:
                        raise ValueError('Health source constant is not literal') from exc
                    if type(value) is not expected[target.id]:
                        raise ValueError('Wrong health source literal type')
                    _literal_table_schema(target.id,value)
                    # Explicitly reject nonfinite values anywhere in a table.
                    try:
                        json.dumps(value,allow_nan=False)
                    except (TypeError,ValueError) as exc:
                        raise ValueError('Invalid health source literal table') from exc
                    found[target.id] = value
                    allowed_stores.add(id(target))
    if set(found) != set(expected):
        raise ValueError('Health source constants missing')
    _literal_declaration_shape(tree,expected,allowed_stores)
    return found


def boolean(value):
    if type(value) is not str or value not in ('true', 'false'):
        raise ValueError('Source plan flags require literal true or false')
    return value == 'true'


@dataclass(frozen=True)
class SourcePlan:
    domains: tuple[str, ...]
    bootstrap: bool
    dry_run: bool
    audits_review: str = ""
    reacquire_pending_pdf: bool = False
    audits_source_acceptance: str = ''

    @property
    def argv(self):
        validate_plan(self)
        args = [sys.executable, '-m', 'seeding.cli', 'seed']
        for domain in self.domains:
            args.extend(['--domain', domain])
        if self.audits_review:
            args.extend(['--audits-reconciliation-review', self.audits_review])
        if self.audits_source_acceptance:
            args.extend(['--audits-source-manifest', str(OAG_ACCEPTANCE_MANIFEST)])
        if len(self.domains) > 1 and not self.dry_run:
            args.append('--fair-progress')
        return [*args, '--dry-run' if self.dry_run else '--no-dry-run']


def build_plan(*, event, schedule, domain, dry_run, cra, opendata, discovery,
               bootstrap='false', county_borrowing='false', audits_review='',
               reacquire_pending_pdf='false', audits_source_acceptance=''):
    # Nonempty choices satisfy Actions semantic validation. Preserve older API
    # dispatches carrying empty inputs, and keep schedule inputs strictly empty.
    if event == 'workflow_dispatch':
        domain = '' if domain == 'all' else domain
        audits_review = '' if audits_review == 'none' else audits_review
        audits_source_acceptance = '' if audits_source_acceptance == 'none' else audits_source_acceptance
    if type(audits_source_acceptance) is not str or audits_source_acceptance not in ('', OAG_SOURCE_ACCEPTANCE):
        raise ValueError('Unknown reviewed audits acquisition scope')
    if audits_review not in ('', 'oag-2542-20261026'):
        raise ValueError('Unknown source-checked audits review')
    enabled = {'cra': boolean(cra), 'opendata': boolean(opendata),
               'county_borrowing': boolean(county_borrowing)}
    discover = boolean(discovery)
    if discover and not enabled['opendata']:
        raise ValueError('KNBS discovery requires the OpenData opt-in too')
    dry = boolean(dry_run)
    boot = boolean(bootstrap)
    reacquire = boolean(reacquire_pending_pdf)
    if type(domain) is not str or domain not in ('', *LEGACY_DOMAINS, 'cra', 'opendata', 'county_borrowing'):
        raise ValueError('Unknown source plan domain')
    if event == 'schedule':
        if schedule not in (DAILY, WEEKLY) or domain or dry or boot or audits_review or reacquire or audits_source_acceptance:
            raise ValueError('Unsupported scheduled source plan')
        weekly = schedule == WEEKLY
        # Admit explicit opt-ins before legacy work can consume the shared
        # native budget. This is priority, not a completion/capacity promise;
        # the unchanged CLI records and fails any remaining budget drop.
        domains = (*(d for d, on in enabled.items() if weekly and on), *LEGACY_DOMAINS)
        return SourcePlan(domains, weekly, False)
    if event != 'workflow_dispatch' or schedule != '':
        raise ValueError('Unsupported source plan event')
    if audits_source_acceptance and (domain != 'audits' or dry or boot or audits_review or reacquire):
        raise ValueError('Reviewed audits acquisition requires only the manual live audits domain')
    if reacquire and (domain != 'pending_bills' or boot or audits_review):
        raise ValueError('PDF reacquisition requires only the manual pending-bills domain')
    if domain in enabled and not enabled[domain]:
        raise ValueError('Selected source requires its explicit opt-in')
    domains = (domain,) if domain else (*(d for d, on in enabled.items() if on), *LEGACY_DOMAINS)
    if audits_review and (dry or 'audits' not in domains):
        raise ValueError('Source-checked review requires a live audits selection')
    return SourcePlan(domains, boot, dry, audits_review, reacquire, audits_source_acceptance)


def environment_plan():
    return build_plan(event=os.environ['SEED_PLAN_EVENT'],
        schedule=os.environ.get('SEED_PLAN_SCHEDULE', ''),
        domain=os.environ.get('SEED_PLAN_DOMAIN', ''),
        dry_run=os.environ.get('SEED_PLAN_DRY_RUN') or 'false',
        bootstrap=os.environ.get('SEED_PLAN_BOOTSTRAP') or 'false',
        cra=os.environ.get('SEED_CRA_INGESTION_ENABLED', 'false'),
        opendata=os.environ.get('SEED_OPENDATA_INGESTION_ENABLED', 'false'),
        discovery=os.environ.get('SEED_KNBS_RELEASE_DISCOVERY_ENABLED', 'false'),
        county_borrowing=os.environ.get('SEED_COUNTY_BORROWING_INGESTION_ENABLED', 'false'),
        audits_review=os.environ.get('SEED_PLAN_AUDITS_REVIEW', ''),
        reacquire_pending_pdf=os.environ.get('SEED_PLAN_REACQUIRE_PENDING_BILLS_PDF', 'false'),
        audits_source_acceptance=os.environ.get('SEED_PLAN_AUDITS_SOURCE_ACCEPTANCE', ''))


def validate_plan(plan):
    """Guard both direct invocation and Actions output publication."""
    if (type(plan) is not SourcePlan or type(plan.domains) is not tuple
            or not 1 <= len(plan.domains) <= len(LEGACY_DOMAINS) + 3
            or any(type(d) is not str or d not in (*LEGACY_DOMAINS, 'cra', 'opendata', 'county_borrowing') for d in plan.domains)
            or len(set(plan.domains)) != len(plan.domains)
            or type(plan.bootstrap) is not bool or type(plan.dry_run) is not bool
            or type(plan.audits_review) is not str
            or plan.audits_review not in ('', 'oag-2542-20261026')
            or type(plan.reacquire_pending_pdf) is not bool
            or type(plan.audits_source_acceptance) is not str
            or plan.audits_source_acceptance not in ('', OAG_SOURCE_ACCEPTANCE)
            or (plan.audits_source_acceptance and (plan.domains != ('audits',) or plan.bootstrap or plan.dry_run or plan.audits_review or plan.reacquire_pending_pdf))
            or (plan.reacquire_pending_pdf and (plan.domains != ('pending_bills',) or plan.bootstrap or plan.audits_review))
            or (plan.audits_review and (plan.dry_run or 'audits' not in plan.domains))):
        raise ValueError('Invalid source plan output or invocation')


def health_source_lines(plan, settings=None):
    """Selected transport components; discovery/content acceptance is separate.

    Import-free literal adapters keep pre-admission planning independent of DB
    configuration. Actual fetcher-call controls bind these adapters to native
    HTTP paths. Dynamic document/IDS-period coverage remains in domain receipts.
    """
    from .config import SeedingSettings
    validate_plan(plan)
    settings = SeedingSettings() if settings is None else settings
    contracts = {}
    def literals(module):
        if module not in contracts:
            contracts[module] = source_literals(module)
        return contracts[module]
    def small_api(url):
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query,keep_blank_values=True))
        query.update(format='json',per_page='1')
        return urlunsplit(parts._replace(query=urlencode(query)))
    def indicators(module, table, optional=False):
        contract = literals(module)
        return [(code,small_api(contract['_WB_BASE']+'/'+code),False) if optional else
                (code,small_api(contract['_WB_BASE']+'/'+code)) for code in contract[table]]
    cog = literals('extractors/cog_governors.py')
    mapping = {
        'county_officials': [('governors',cog['SOURCE_URL']),('deputies',cog['DEPUTIES_SOURCE_URL'])],
        'learning_hub': [('curated learning reference','reference')],
        'economic_indicators': [('CBK inflation',literals('domains/economic_indicators/cbk_inflation.py')['CBK_INFLATION_URL'])],
        'population': [], 'national_gdp': [], 'revenue_by_source': [],
    }
    live = settings.live_pdf_fetch_enabled
    cob = settings.counties_budget_cob_wp_api_url
    county_urls = literals('domains/counties_budget/fetcher.py')['_COB_COUNTY_BIRR_URLS']
    county_listings = [('county listing',settings.counties_budget_cob_reports_url)]
    county_listings += [('county fallback '+str(i),url,False) for i,url in enumerate(county_urls,1)
                        if url != settings.counties_budget_cob_reports_url]
    if live:
        oag = literals('oag_discovery.py')['OAG_ORIGIN']
        searches = literals('domains/audits/fetcher.py')['_WP_MEDIA_SEARCHES']
        mapping.update({
            'audits': [('county catalogue',oag+'/county-executives-assemblies-reports/'),
                       ('sitemap index',oag+'/wp-sitemap.xml')]+[
                       ('media '+term,oag+'/wp-json/wp/v2/media?per_page=100&search='+quote_plus(term)) for term in searches],
            'counties_budget': [('media',cob)]+[(label,url,False) for label,url,*_ in county_listings],
            'national_budget': [('national listing',settings.cob_birr_page_url)],
            'stalled_projects': [('county listing',settings.counties_budget_cob_reports_url)],
            'fiscal_summary': [('COB national listing',settings.cob_birr_page_url),
                ('budget books',settings.treasury_budget_books_page_url),
                ('revenue and framework editions',settings.treasury_budget_summary_page_url,'treasury_editions')],
            'pending_bills': [('Treasury actuals',settings.treasury_brop_page_url)]+county_listings,
            'national_debt': [('public debt',settings.cbk_public_debt_page_url),
                ('configured bulletin',settings.cbk_statistical_bulletin_url) if settings.cbk_statistical_bulletin_url
                else ('bulletins',settings.cbk_statistical_bulletin_page_url)],
        })
        if settings.treasury_brop_url:
            mapping['pending_bills'].append(('Treasury fallback edition',settings.treasury_brop_url,False))
        # A delivered fiscal lane adds this exact native source. Until then the
        # baseline has no APDMR fetch; no peer module is imported or adopted.
        if (_SOURCE_ROOT/'domains/fiscal_summary/actuals.py').is_file():
            actuals=literals('domains/fiscal_summary/actuals.py')
            mapping['fiscal_summary'] += [('reviewed historical actuals',actuals['APDMR_URL']),
                                         ('reviewed historical BROP',actuals['BROP_URL'])]
    else:
        for domain in ('audits','counties_budget','national_budget','stalled_projects','fiscal_summary','pending_bills','national_debt','debt_timeline'):
            mapping[domain] = [('live PDF sources disabled','missing')]
    # The timeline's native bulletin overlay is independent of the global PDF
    # switch. A configured edition replaces discovery in the real resolver.
    mapping['debt_timeline'] = ([('configured bulletin',settings.cbk_statistical_bulletin_url)]
        if settings.cbk_statistical_bulletin_url else [('bulletins',settings.cbk_statistical_bulletin_page_url)])
    if not settings.counties_budget_prefer_live_source:
        mapping['counties_budget'] = [('live source preference disabled','missing')]
    if settings.enrich_with_worldbank:
        mapping['economic_indicators'] += indicators('domains/economic_indicators/fetcher.py','_WB_INDICATORS')
        mapping['population'] += indicators('domains/population/fetcher.py','_WB_POPULATION_INDICATORS')
        mapping['population'] += indicators('domains/population/fetcher.py','_WB_SUPPLEMENTARY',True)
        mapping['national_gdp'].append(('GDP',literals('domains/national_gdp/fetcher.py')['_WB_GDP_URL']))
        mapping['debt_timeline'].append(('GDP',literals('domains/debt_timeline/fetcher.py')['_WB_GDP_URL']))
        mapping['revenue_by_source'] += indicators('domains/revenue_by_source/fetcher.py','_WB_REVENUE_INDICATORS',True)
    else:
        mapping['population'].append(('national World Bank source disabled','missing'))
        mapping['national_gdp'].append(('GDP World Bank source disabled','missing'))
    if not plan.dry_run:
        mapping['population'].append(('county census edition',literals('domains/population/census_counties.py')['CENSUS_VOLUME_I_URL']))
    gdp = literals('domains/national_gdp/fetcher.py')
    mapping['national_gdp'] += [(field,small_api(gdp['_WB_POVERTY_URL'].format(indicator=code)),False)
                               for field,code in gdp['_POVERTY_INDICATORS'].items()]
    kra = literals('domains/revenue_by_source/kra_discovery.py')
    mapping['revenue_by_source'].append(('KRA listing',kra['KRA_BASE']+'/news-center/press-release'))
    ended = date.today().year-1 if date.today().month>=7 else date.today().year-2
    mapping['revenue_by_source'] += [('KRA candidate '+str(y),kra['KRA_BASE']+'/'+kra['ANNUAL_SLUG'].format(y1=y,y2=y+1),False)
                                    for y in (ended+1,ended,ended-1)]
    mapping['revenue_by_source'].append(('KRA catalogue authority',literals('kra_report_catalogue.py')['CATALOGUE_URL'],False))
    if settings.kra_revenue_url:
        mapping['revenue_by_source'].append(('configured KRA revenue',settings.kra_revenue_url,False))
    if live:
        wb = literals('domains/national_debt/wb_ids.py')
        for row in wb['WB_IDS_CREDITORS']:
            for code in (row['code'],row['combine_with']):
                if code:
                    mapping['national_debt'].append(('aggregate '+code,small_api(wb['_WB_BASE']+'/'+code),False))
        ids = literals('domains/national_debt/wb_ids_creditors.py')
        # A transport candidate is not an observed debt year. The native IDS
        # reader discovers its year and qualifies all stock/interest components.
        codes = set(ids['SERIES'])|{ids['TOTAL_SERIES'],ids['EXTERNAL_TOTAL_SERIES'],
                                  'DT.DOD.DPNG.CD','DT.DOD.DSTC.CD'}
        for code in sorted(codes):
            mapping['national_debt'].append(('IDS candidate '+code,ids['_IDS_BASE']+'/'+code+
                '/counterpart-area/all/time/YR'+str(date.today().year)+'?format=json&per_page=1'))
        for code in sorted(ids['SERIES']):
            interest = code.replace('DT.DOD.','DT.INT.')
            mapping['national_debt'].append(('interest candidate '+interest,ids['_IDS_BASE']+'/'+interest+
                '/counterpart-area/all/time/YR'+str(date.today().year)+'?format=json&per_page=1',False))
        fx = literals('domains/national_debt/fx.py')
        mapping['national_debt'].append(('USD KES FX',small_api(fx['_WB_BASE']+'/'+fx['FX_SERIES'])))
        tables = literals('domains/national_debt/cbk_web_tables.py')
        mapping['national_debt'] += [('bond register',tables['BONDS_URL'],False),('Tbill key rates',tables['KEY_RATES_URL'],False)]
    imf = literals('domains/imf_weo/fetcher.py')
    mapping['imf_weo'] = [(code,imf['_BASE_URL']+'/'+code+'/'+';'.join(imf['COUNTRIES'])) for code in imf['INDICATORS']]
    if 'cra' in plan.domains:
        mapping['cra'] = [('reviewed edition',literals('domains/cra/source.py')['URL'])]
    if 'opendata' in plan.domains:
        opendata = literals('domains/opendata/source.py')
        mapping['opendata'] = [('workbook',opendata['URL'])]
        if settings.knbs_release_discovery_enabled:
            mapping['opendata'] += [('release discovery',literals('domains/opendata/discovery.py')['INDEX']),
                                    ('report',opendata['REPORT_URL'])]
    if 'county_borrowing' in plan.domains:
        path = _SOURCE_ROOT/'fixtures/county_borrowing_editions.json'
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024*1024:
            raise ValueError('County borrowing source inventory refused')
        def unique_pairs(pairs):
            result = {}
            for key,value in pairs:
                if key in result: raise ValueError('Duplicate source inventory JSON key')
                result[key] = value
            return result
        editions = json.loads(path.read_text(),object_pairs_hook=unique_pairs)
        if type(editions) is not list or not 1 <= len(editions) <= 8:
            raise ValueError('County borrowing source inventory refused')
        seen = set(); mapping['county_borrowing'] = []
        for item in editions:
            if (type(item) is not dict or type(item.get('id')) is not str or item['id'] in seen
                    or type(item.get('url')) is not str):
                raise ValueError('County borrowing source identity refused')
            seen.add(item['id']); mapping['county_borrowing'].append(('reviewed edition '+item['id'],item['url']))
    override_fields = {'counties_budget':'budgets_dataset_url','audits':'audits_dataset_url',
        'economic_indicators':'economic_indicators_dataset_url','national_debt':'national_debt_dataset_url',
        'pending_bills':'pending_bills_dataset_url','debt_timeline':'debt_timeline_dataset_url',
        'fiscal_summary':'fiscal_summary_dataset_url','revenue_by_source':'revenue_by_source_dataset_url',
        'learning_hub':'learning_hub_dataset_url','national_budget':'national_budget_execution_dataset_url'}
    entries = {}
    for domain in plan.domains:
        specs = list(mapping.get(domain,[('unmodelled source','missing')]))
        configured = getattr(settings,override_fields.get(domain,''),None)
        if type(configured) is str and configured.startswith(('http:','https:')):
            specs.append(('configured dataset',configured))
        for component,url,*options in specs:
            critical = url != 'reference' and options != [False]
            discovery = options[0] if options and type(options[0]) is str else ''
            label = domain+' '+component
            if (not re.fullmatch(r'[a-zA-Z0-9_ .:/-]{1,160}',label) or type(url) is not str or len(url)>2048
                    or any(c in url for c in '\r\n|') or any(c.isspace() for c in url)):
                raise ValueError('Health source inventory malformed')
            if url not in ('reference','missing'):
                parsed = urlsplit(url)
                if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
                    raise ValueError('Health source URL requires credential-free verified HTTPS')
            # One transport attempt per endpoint/discovery contract, even when
            # several selected domains share it. Retain every domain label and
            # the strongest required flag. The job/source/attempt wall-clock
            # budgets stay unchanged as the diagnostic denominator expands.
            key = (url,discovery) if url not in ('reference','missing') else (url,label)
            if key in entries:
                old = entries[key]; old[0] += '/'+label; old[2] = old[2] or critical
            else:
                entries[key] = [label,url,critical,discovery]
    lines = []
    for label,url,critical,discovery in entries.values():
        if len(label)>512: raise ValueError('Health component label exceeds bound')
        fields = [label,url,'true' if critical else 'false']
        if discovery: fields.append(discovery)
        lines.append('|'.join(fields))
    if not 1<=len(lines)<=128 or len('\n'.join(lines).encode())>24000:
        raise ValueError(f'Health source inventory exceeds bound: {len(lines)} endpoints')
    return '\n'.join(lines)


def write_plan_outputs(plan):
    """Publish selection only to this Actions step's precreated output file."""
    validate_plan(plan)
    if 'GITHUB_OUTPUT' not in os.environ:
        return
    path = Path(os.environ['GITHUB_OUTPUT'])
    root = Path(__file__).resolve().parents[2]
    if (not path.is_file() or path.is_symlink() or path.resolve().is_relative_to(root)
            or path.stat().st_size > 64 * 1024):
        raise ValueError('Source plan output must be an external Actions output file')
    # Only selection metadata crosses the job boundary.
    with path.open('a', encoding='utf-8') as output:
        output.write('domains=' + json.dumps(plan.domains, separators=(',', ':')) + '\n')
        output.write('bootstrap=' + ('true' if plan.bootstrap else 'false') + '\n')


def main():
    try:
        if sys.argv[1:] not in (['--check'], ['--execute']):
            raise ValueError('Expected --check or --execute')
        plan = environment_plan()
        if sys.argv[1] == '--check':
            try:
                health_source_lines(plan)
            except (ValueError, OSError, SyntaxError):
                # Settings validation can include the rejected secret in its error.
                raise ValueError('Selected health source inventory refused') from None
            write_plan_outputs(plan)
        print(json.dumps({'domains': plan.domains, 'bootstrap': plan.bootstrap,
                          'dry_run': plan.dry_run, 'audits_review': plan.audits_review,
                          'reacquire_pending_pdf': plan.reacquire_pending_pdf,
                          'audits_source_acceptance': plan.audits_source_acceptance,
                          'evidence': 'selection_plan_only'}), flush=True)
        if sys.argv[1] == '--execute':
            args = plan.argv  # Validate direct plans before constructing execution options.
            options = {'check': False}
            if plan.reacquire_pending_pdf or plan.audits_source_acceptance:
                options['env'] = dict(os.environ, SEED_PDF_CACHE_TTL_SECONDS='0')
            if plan.audits_source_acceptance:
                # The manual source-only path must not inherit ordinary nightly
                # generation permissions. Never modify the parent's controls.
                options['env'].update(dict.fromkeys(OAG_SOURCE_ONLY_CONTROLS, 'false'))
            return subprocess.run(args, **options).returncode
        return 0
    except (KeyError, ValueError) as exc:
        print('Source plan refused: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
