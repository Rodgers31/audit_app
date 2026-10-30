"""Versioned, evidence-bound post composition. No model or network calls."""
from datetime import date
from functools import lru_cache
from pathlib import Path
import json
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from ..contracts import StrictModel, DocumentTarget, PostDocument, canonical_hash
from ..service import SocialError
from .contracts import SourceObservation

POLICY_VERSION = 'auditgava-editorial-v1'
TEMPLATES = {'factual-v3', 'financial-v5', 'report-availability-v4', 'catalogue-availability-v4'}
Platform = Literal['facebook', 'instagram', 'threads', 'x', 'tiktok']
Tag = Annotated[str, StringConstraints(strict=True, pattern=r'^[A-Za-z][A-Za-z0-9]{0,89}$')]


class PlatformRule(StrictModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    platform: Platform
    tag_limit: Annotated[int, Field(strict=True, ge=1, le=3)]
    caption_limit: Annotated[int, Field(strict=True, ge=100, le=2200)]
    limit_kind: str
    reference: str
    reference_status: Literal['primary_verified', 'primary_access_limited']


class TopicRule(StrictModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    terms: Annotated[tuple[Annotated[str, StringConstraints(strict=True, min_length=1)], ...], Field(min_length=1)]
    tag: Tag
    label: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=80)]


class EditorialPolicy(StrictModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: Literal['auditgava-editorial-v1']
    reviewed_on: date
    review_due: date
    brand_tag: Tag
    platforms: tuple[PlatformRule, ...]
    topics: tuple[TopicRule, ...]

    @model_validator(mode='after')
    def complete(self):
        if (len(self.platforms) != 5 or {p.platform for p in self.platforms} != {'facebook','instagram','x','threads','tiktok'}
                or self.review_due <= self.reviewed_on or not self.topics):
            raise ValueError('Complete dated editorial rules are required')
        return self


@lru_cache(maxsize=1)
def policy():
    # A missing/invalid deployed rule file is an explicit hold, never generic tags.
    try:
        value = EditorialPolicy.model_validate(json.loads(Path(__file__).with_name('editorial-policy-v1.json').read_text()))
        return value
    except (OSError, ValueError, TypeError):
        raise SocialError('EDITORIAL_POLICY_UNAVAILABLE', 'Editorial rules are unavailable. Restore the reviewed project policy.', 503) from None


class EditorialProfile(StrictModel):
    platform: Platform
    target: DocumentTarget

    @model_validator(mode='after')
    def configured(self):
        if self.target.overrides.model_fields_set:
            raise ValueError('Generated account defaults cannot contain fixed post overrides')
        return self


def profiles(values):
    if type(values) not in (list, tuple) or len(values) > 25:
        raise SocialError('EVIDENCE_INTEGRITY_FAILED', 'Saved editorial account profiles differ.', 503)
    try:
        # Stored profiles are JSON data, not preconstructed unchecked models.
        from ..contracts import canonical_json
        canonical_json(values)
        if any(type(value) is not dict for value in values):
            raise ValueError()
        result = tuple(EditorialProfile.model_validate(value) for value in values)
        if len({p.target.account_id for p in result}) != len(result):
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise SocialError('EVIDENCE_INTEGRITY_FAILED', 'Saved editorial account profiles differ.', 503) from None


def capture_profiles(db, targets, now):
    rules = policy()
    if not rules.reviewed_on <= now.date() <= rules.review_due:
        raise SocialError('EDITORIAL_POLICY_REVIEW_REQUIRED', 'Review the project editorial policy before preparing new drafts.', 422)
    from ..models import SocialAccount
    result = []
    for raw in targets:
        target = DocumentTarget.model_validate(raw)
        account = db.get(SocialAccount, target.account_id, populate_existing=True)
        if account is None:
            raise SocialError('ACCOUNT_UNAVAILABLE', 'A configured draft account is unavailable. Review the account defaults.', 422)
        if account.platform == 'tiktok':
            # Consent, creator settings and media disclosures belong to the
            # particular post. Account defaults cannot attest them on its behalf.
            target = target.model_copy(update={'tiktok_options': None})
        if target.format == 'text' and account.platform in ('instagram', 'tiktok'):
            target = target.model_copy(update={'format': 'image' if account.platform == 'instagram' else 'video'})
        try:
            result.append(EditorialProfile(platform=account.platform, target=target).model_dump(mode='json'))
        except ValueError:
            raise SocialError('EDITORIAL_DEFAULTS_REVIEW_REQUIRED', 'Choose supported account defaults without fixed post text or link overrides.', 422) from None
    return [p.model_dump(mode='json') for p in profiles(result)]


def context(observation):
    source = SourceObservation.model_validate(observation.model_dump(mode='python'))
    domain = getattr(source.report or source.financial, 'native_domain', None)
    metrics = ' '.join(f.metric for f in source.facts).casefold()
    topic = None
    for rule in policy().topics:
        if rule.tag.endswith('Budget') and not (domain == 'national_budget' or source.category == 'budget_update' or re.search(r'budget|expenditure|spending', metrics)):
            continue
        if any(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', metrics) for term in rule.terms):
            topic = (rule.tag, rule.label)
            break
    if topic is None:
        topic = ({'pending_bills': ('PendingBills', 'pending bills'), 'national_budget': ('KenyaBudget','national budget'),
                  'revenue_by_source': ('KenyaRevenue','revenue'), 'audits': ('PublicAudit','public audit')}.get(domain)
                 or (('CountyBudget','county budget') if source.report else None)
                 or {'budget_update': ('PublicBudget','budget'), 'debt_update': ('PublicDebt','public debt'),
                     'audit_finding': ('PublicAudit','public audit'), 'correction': ('DataCorrection','data correction')}.get(source.category)
                 or ('PublicData','public data'))
    entities = [source.report.entity] if source.report else [f.entity for f in source.facts]
    locations = []
    for entity in dict.fromkeys(entities):
        if re.search(r'\bcounty$', entity, re.I):
            value = ''.join(word.title() for word in re.findall(r'[A-Za-z0-9]+', entity.replace("'", '').replace('’', '')))
            if re.fullmatch(r'[A-Za-z][A-Za-z0-9]{0,89}', value):
                locations.append(value)
        elif re.search(r'\bkenya\b|\bnational government\b', entity, re.I):
            locations.append('Kenya')
    return topic, tuple(dict.fromkeys(locations))


def hashtags(observation, platform=None):
    rules = policy()
    maximum = 3 if platform is None else next((p.tag_limit for p in rules.platforms if p.platform == platform), None)
    if maximum is None:
        raise SocialError('UNSUPPORTED_PLATFORM', 'Choose a supported editorial account.', 422)
    (tag, _), locations = context(observation)
    candidates = dict.fromkeys((tag, *locations, rules.brand_tag))
    return tuple('#'+value for value in list(candidates)[:maximum])


def _fits(text, link, tags, rule):
    combined = '\n\n'.join(filter(None, (text, ' '.join(tags), link)))
    if rule.platform == 'x':
        from ..adapters.x_text import count_text
        return count_text(combined) <= rule.caption_limit
    return (len(combined.encode('utf-8')) if rule.platform == 'threads' else len(combined)) <= rule.caption_limit


def account_caption(source, full, link, tags, platform):
    rule = next(p for p in policy().platforms if p.platform == platform)
    if _fits(full, link, tags, rule):
        return full
    (_, label), _ = context(source)
    first = source.report or source.facts[0]
    if source.financial:
        # Numeric short copy keeps every qualification and the publisher. A
        # smaller account receives a neutral scoped invitation when that full
        # meaning cannot fit; caveats never disappear while the amount stays.
        paragraphs = full.split('\n\n')
        if paragraphs[0] == 'Correction awaiting human review.':
            paragraphs = paragraphs[1:]
        compact = '\n\n'.join([*paragraphs[:-1], 'Figures and sources on AuditGava.'])
        if source.correction_pending or source.category == 'correction':
            compact = 'Correction awaiting human review.\n\n' + compact
        if _fits(compact, link, tags, rule):
            return compact
    if source.report and getattr(source.report, 'evidence_kind', None) == 'publisher_catalogue':
        compact = f'{first.entity}: {label} report entry for {first.period}. Publication date not stated. Human review required.\n\nDetails and sources on AuditGava.'
    else:
        compact = f'{first.entity}: explore the {label} {"report" if source.report else "figures"} for {first.period} on AuditGava.'
        if source.correction_pending or source.category == 'correction':
            compact = 'Correction awaiting human review.\n\n'+compact
    compact += f'\n\nSource: {first.publisher}.'
    if not _fits(compact, link, tags, rule):
        raise SocialError('EDITORIAL_COPY_TOO_LONG', 'The verified scope cannot fit this account. Review the source adapter or account defaults.', 422)
    return compact


def document_for_revision(db, source, metadata):
    from .service import render_for_revision
    from .destination import draft_destination
    full = render_for_revision(source, metadata)
    link = draft_destination(db, source, template_version=metadata['template_version'])
    master_tags = hashtags(source)
    targets = []
    for profile in profiles(metadata['editorial_profiles']):
        tags = hashtags(source, profile.platform)
        text = account_caption(source, full, link, tags, profile.platform)
        target = profile.target.model_dump(mode='json')
        overrides = {}
        if text != full:
            overrides['text'] = {'mode': 'replace', 'value': text}
        if tags != master_tags:
            overrides['hashtags'] = {'mode': 'replace', 'value': list(tags)}
        target['overrides'] = overrides
        targets.append(target)
    return PostDocument.model_validate({'master': {'text': full, 'link': link, 'hashtags': list(master_tags)}, 'targets': targets})
