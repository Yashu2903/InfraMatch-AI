from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Supplier(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    canonical_supplier_id: str = Field(index=True, unique=True)
    canonical_name: str
    uei: Optional[str] = None
    state: str = Field(index=True)

    past_awards_count: int
    total_award_value: float
    avg_award_value: float
    last_award_date: Optional[date] = None

    naics_codes_json: str
    psc_codes_json: str
    agencies_json: str
    subagencies_json: str

    local_content_score: float
    small_business_flag: bool
    certifications_json: str
    synthetic_esg_score: float
    risk_score: float


class Opportunity(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    title: str
    asset_type: str = Field(index=True)

    state: str = Field(index=True)
    city: str

    naics_code: str = Field(index=True)
    psc_code: str = Field(index=True)

    awarding_agency: str
    awarding_subagency: str = Field(index=True)

    budget: float
    required_local_content: float
    requires_small_business: bool
    required_certifications_json: str
    risk_tolerance: str


class Match(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    opportunity_id: int = Field(index=True)
    supplier_id: int = Field(index=True)

    final_score: float
    rank: int

    score_breakdown_json: str
    top_factors_json: str
    concerns_json: str
    compliance_outcomes_json: str = "[]"

    created_at: datetime = Field(default_factory=datetime.utcnow)


class Inspection(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    opportunity_id: int = Field(index=True)
    supplier_id: int = Field(index=True)

    status: str = "created"
    uploaded_image_path: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)


class DefectResult(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    inspection_id: int = Field(index=True)

    prediction: str
    confidence: float
    severity: str
    crack_ratio: Optional[float] = None
    gradcam_path: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)