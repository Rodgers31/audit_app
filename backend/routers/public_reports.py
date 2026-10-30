"""Public source pages; exact scope only, with no editorial-state exposure."""
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from services.public_report_view import public_report_view, ReportViewUnavailable
from seeding.source_observations import SourceObservationUnavailable, _read_limits

router = APIRouter(prefix='/api/v1/reports', tags=['Public report views'])
Domain = Literal['national_budget', 'revenue_by_source', 'audits', 'pending_bills', 'counties_budget']
Identifier = Annotated[int, Query(gt=0, le=2147483647)]


class PublicSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str
    publisher: str
    locator: str


class PublicFigure(BaseModel):
    model_config = ConfigDict(extra='forbid')
    entity: str
    metric: str
    period: str
    value: str
    display_value: str
    unit: str
    scale: str
    classification: Literal['actual', 'modelled', 'projected']
    comparison_basis: str
    locator: str


class PublicReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1]
    domain: Domain
    view: Literal['report', 'financial']
    snapshot: str
    title: str
    entity: str
    period: str
    period_start: date | None
    period_end: date | None
    publisher: str
    published_on: date | None
    catalogued_on: date | None
    availability: Literal['published', 'catalogued']
    figures: list[PublicFigure]
    sources: list[PublicSource]


@router.get('/{domain}/{document_id}', response_model=PublicReport)
def report_view(domain: Domain, document_id: int, response: Response,
                snapshot: Annotated[str, Query(pattern='^[a-f0-9]{64}$')],
                view: Literal['report', 'financial'] = 'report', entity: Identifier | None = None,
                record: Identifier | None = None, db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    if not 0 < document_id <= 2147483647:
        raise HTTPException(422, 'Choose a valid report.', headers={'Cache-Control': 'no-store'})
    try:
        # This router shares no admin dependency, query or mutable session.
        if db.in_transaction():
            raise ReportViewUnavailable()
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        _read_limits(db)
        return public_report_view(db, domain=domain, document_id=document_id, view=view,
                                  snapshot=snapshot, entity=entity, record=record)
    except SourceObservationUnavailable as error:
        raise HTTPException(503 if error.operational else 410, {'code': 'REPORT_VIEW_UNAVAILABLE',
            'message': 'This exact report view is unavailable. No different report or period has been substituted.'},
            headers={'Cache-Control': 'no-store'}) from None
    except (ReportViewUnavailable, ValueError, TypeError, KeyError):
        raise HTTPException(410, {'code': 'REPORT_VIEW_UNAVAILABLE',
            'message': 'This exact report view has changed or is unavailable. No different report or period has been substituted.'},
            headers={'Cache-Control': 'no-store'}) from None
    except SQLAlchemyError:
        raise HTTPException(503, {'code': 'REPORT_VIEW_UNAVAILABLE',
            'message': 'The report service is temporarily unavailable. Try again.'},
            headers={'Cache-Control': 'no-store'}) from None
