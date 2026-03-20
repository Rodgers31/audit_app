from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Response schemas
class ProvenanceResponse(BaseModel):
    source_document_id: int
    url: Optional[str]
    page: Optional[int]
    snippet: Optional[str]
    confidence: Optional[float]


class CountryResponse(BaseModel):
    id: int
    iso_code: str
    name: str
    currency: str
    timezone: str
    metadata: Dict[str, Any] = {}

    class Config:
        from_attributes = True


class EntityResponse(BaseModel):
    id: int
    country_id: int
    type: str
    canonical_name: str
    slug: str
    alt_names: List[str] = []
    metadata: Dict[str, Any] = {}

    class Config:
        from_attributes = True


class FiscalPeriodResponse(BaseModel):
    id: int
    country_id: int
    label: str
    start_date: datetime
    end_date: datetime

    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    id: int
    country_id: int
    publisher: str
    title: str
    url: Optional[str]
    doc_type: str
    fetch_date: datetime
    metadata: Dict[str, Any] = {}

    class Config:
        from_attributes = True


class BudgetLineResponse(BaseModel):
    id: int
    entity_id: int
    period_id: int
    category: str
    subcategory: Optional[str]
    allocated_amount: Optional[Decimal]
    actual_spent: Optional[Decimal]
    committed_amount: Optional[Decimal]
    currency: str
    source_document_id: int
    page_ref: Optional[str]
    notes: Optional[str]
    provenance: List[ProvenanceResponse] = []

    class Config:
        from_attributes = True


class LoanResponse(BaseModel):
    id: int
    entity_id: int
    lender: str
    principal: Decimal
    outstanding: Decimal
    issue_date: datetime
    maturity_date: Optional[datetime]
    currency: str
    source_document_id: int
    provenance: List[ProvenanceResponse] = []

    class Config:
        from_attributes = True


class AuditResponse(BaseModel):
    id: int
    entity_id: int
    period_id: int
    finding_text: str
    severity: str
    recommended_action: Optional[str]
    source_document_id: int
    provenance: List[ProvenanceResponse] = []
    query_type: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = None
    audit_opinion: Optional[str] = None
    audit_year: Optional[int] = None
    external_reference: Optional[str] = None
    management_response: Optional[str] = None
    follow_up_status: Optional[str] = None

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    query: str
    results: List[Dict[str, Any]]
    total: int
    skip: int
    limit: int


# Request schemas
class AnnotationCreate(BaseModel):
    ref_type: str = Field(..., regex="^(budget_line|audit|loan)$")
    ref_id: int
    text: str = Field(..., min_length=1, max_length=5000)
    public: bool = False


class DocumentUpload(BaseModel):
    country_id: int
    publisher: str
    title: str
    url: Optional[str]
    doc_type: str = Field(..., regex="^(budget|audit|report|loan|other)$")
    metadata: Dict[str, Any] = {}


class UserCreate(BaseModel):
    email: str = Field(..., regex=r"^[^@]+@[^@]+\.[^@]+$")
    password: str = Field(..., min_length=8)
    roles: List[str] = []


class UserResponse(BaseModel):
    id: int
    email: str
    roles: List[str]
    disabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


# Quick Questions schemas
class QuickQuestionBase(BaseModel):
    question_text: str
    correct_answer: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    explanation: Optional[str] = None
    category: str
    difficulty_level: int = Field(ge=1, le=5)
    source_url: Optional[str] = None
    tags: List[str] = []


class QuickQuestionCreate(QuickQuestionBase):
    pass


class QuickQuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    correct_answer: Optional[str] = None
    option_a: Optional[str] = None
    option_b: Optional[str] = None
    option_c: Optional[str] = None
    option_d: Optional[str] = None
    explanation: Optional[str] = None
    category: Optional[str] = None
    difficulty_level: Optional[int] = Field(None, ge=1, le=5)
    is_active: Optional[bool] = None
    source_url: Optional[str] = None
    tags: Optional[List[str]] = None


class QuickQuestionResponse(QuickQuestionBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuickQuestionPublic(BaseModel):
    """Public question response without correct answer"""

    id: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    category: str
    difficulty_level: int
    tags: List[str] = []

    class Config:
        from_attributes = True


class UserAnswerCreate(BaseModel):
    question_id: int
    selected_answer: str = Field(..., regex="^[ABCD]$")


class UserAnswerResponse(BaseModel):
    id: int
    question_id: int
    selected_answer: str
    is_correct: bool
    answered_at: datetime
    question: QuickQuestionResponse

    class Config:
        from_attributes = True


class QuestionStatsResponse(BaseModel):
    total_questions: int
    answered_today: int
    correct_today: int
    accuracy_rate: float
    streak: int
    favorite_category: Optional[str] = None
