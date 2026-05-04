from typing import Any, Optional

from pydantic import BaseModel, Field


class OpportunityCreate(BaseModel):
    title: str
    asset_type: str

    state: str
    city: str

    naics_code: str
    psc_code: str

    awarding_agency: str
    awarding_subagency: str

    budget: float
    required_local_content: float
    requires_small_business: bool
    required_certifications: list[str] = Field(default_factory=list)
    risk_tolerance: str = "medium"


class AssignSupplierRequest(BaseModel):
    supplier_id: int


class RankRequest(BaseModel):
    top_n: int = 10


class SupplierResponse(BaseModel):
    id: int
    canonical_supplier_id: str
    canonical_name: str
    uei: Optional[str] = None
    state: str

    past_awards_count: int
    total_award_value: float
    avg_award_value: float
    last_award_date: Optional[str] = None

    naics_codes: list[str]
    psc_codes: list[str]
    agencies: list[str]
    subagencies: list[str]

    local_content_score: float
    small_business_flag: bool
    certifications: list[str]
    synthetic_esg_score: float
    risk_score: float


class OpportunityResponse(BaseModel):
    id: int
    title: str
    asset_type: str

    state: str
    city: str

    naics_code: str
    psc_code: str

    awarding_agency: str
    awarding_subagency: str

    budget: float
    required_local_content: float
    requires_small_business: bool
    required_certifications: list[str]
    risk_tolerance: str


class InspectionResponse(BaseModel):
    id: int
    opportunity_id: int
    supplier_id: int
    status: str
    uploaded_image_path: Optional[str] = None
    created_at: str


class DefectResultResponse(BaseModel):
    id: int
    inspection_id: int
    prediction: str
    confidence: float
    severity: str
    crack_ratio: Optional[float] = None
    gradcam_path: Optional[str] = None
    created_at: str


class ReportResponse(BaseModel):
    inspection: dict[str, Any]
    opportunity: dict[str, Any]
    supplier: dict[str, Any]
    match: Optional[dict[str, Any]] = None
    defect_result: Optional[dict[str, Any]] = None