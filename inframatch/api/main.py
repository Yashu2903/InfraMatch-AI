import json
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from inframatch.api.schemas import (
    AssignSupplierRequest,
    DefectResultResponse,
    InspectionResponse,
    OpportunityCreate,
    OpportunityResponse,
    RankRequest,
    ReportResponse,
    SupplierResponse,
)
from inframatch.cv.inference import predict
from inframatch.db.models import DefectResult, Inspection, Match, Opportunity, Supplier
from inframatch.db.session import engine
from inframatch.matching.ranker import get_saved_matches, rank_entrants, rank_suppliers


UPLOAD_DIR = Path("uploads/inspections")
MODEL_PATH = Path("models/crack_resnet18.pt")
DEFAULT_CV_THRESHOLD = 0.5

app = FastAPI(
    title="InfraMatch AI API",
    version="0.6.0",
    description="Supplier matching, compliance, and inspection analysis API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later for deployed React frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def parse_json_list(value) -> list:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return []

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []

    return []


def supplier_to_response(supplier: Supplier) -> SupplierResponse:
    return SupplierResponse(
        id=supplier.id,
        canonical_supplier_id=supplier.canonical_supplier_id,
        canonical_name=supplier.canonical_name,
        uei=supplier.uei,
        state=supplier.state,
        past_awards_count=supplier.past_awards_count,
        total_award_value=supplier.total_award_value,
        avg_award_value=supplier.avg_award_value,
        last_award_date=(
            supplier.last_award_date.isoformat()
            if supplier.last_award_date
            else None
        ),
        naics_codes=parse_json_list(supplier.naics_codes_json),
        psc_codes=parse_json_list(supplier.psc_codes_json),
        agencies=parse_json_list(supplier.agencies_json),
        subagencies=parse_json_list(supplier.subagencies_json),
        local_content_score=supplier.local_content_score,
        small_business_flag=supplier.small_business_flag,
        certifications=parse_json_list(supplier.certifications_json),
        synthetic_esg_score=supplier.synthetic_esg_score,
        risk_score=supplier.risk_score,
    )


def opportunity_to_response(opportunity: Opportunity) -> OpportunityResponse:
    return OpportunityResponse(
        id=opportunity.id,
        title=opportunity.title,
        asset_type=opportunity.asset_type,
        state=opportunity.state,
        city=opportunity.city,
        naics_code=opportunity.naics_code,
        psc_code=opportunity.psc_code,
        awarding_agency=opportunity.awarding_agency,
        awarding_subagency=opportunity.awarding_subagency,
        budget=opportunity.budget,
        required_local_content=opportunity.required_local_content,
        requires_small_business=opportunity.requires_small_business,
        required_certifications=parse_json_list(
            opportunity.required_certifications_json
        ),
        risk_tolerance=opportunity.risk_tolerance,
    )


def inspection_to_response(inspection: Inspection) -> InspectionResponse:
    return InspectionResponse(
        id=inspection.id,
        opportunity_id=inspection.opportunity_id,
        supplier_id=inspection.supplier_id,
        status=inspection.status,
        uploaded_image_path=inspection.uploaded_image_path,
        created_at=inspection.created_at.isoformat(),
    )


def defect_result_to_response(result: DefectResult) -> DefectResultResponse:
    return DefectResultResponse(
        id=result.id,
        inspection_id=result.inspection_id,
        prediction=result.prediction,
        confidence=result.confidence,
        severity=result.severity,
        crack_ratio=result.crack_ratio,
        gradcam_path=result.gradcam_path,
        created_at=result.created_at.isoformat(),
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "database": str(engine.url),
        "model_exists": MODEL_PATH.exists(),
    }


@app.post("/opportunities", response_model=OpportunityResponse)
def create_opportunity(payload: OpportunityCreate):
    opportunity = Opportunity(
        title=payload.title,
        asset_type=payload.asset_type,
        state=payload.state,
        city=payload.city,
        naics_code=payload.naics_code,
        psc_code=payload.psc_code,
        awarding_agency=payload.awarding_agency,
        awarding_subagency=payload.awarding_subagency,
        budget=payload.budget,
        required_local_content=payload.required_local_content,
        requires_small_business=payload.requires_small_business,
        required_certifications_json=json.dumps(payload.required_certifications),
        risk_tolerance=payload.risk_tolerance,
    )

    with Session(engine) as session:
        session.add(opportunity)
        session.commit()
        session.refresh(opportunity)

    return opportunity_to_response(opportunity)


@app.get("/opportunities", response_model=list[OpportunityResponse])
def list_opportunities(
    state: Optional[str] = Query(default=None),
    asset_type: Optional[str] = Query(default=None),
):
    with Session(engine) as session:
        statement = select(Opportunity)

        if state:
            statement = statement.where(Opportunity.state == state)

        if asset_type:
            statement = statement.where(Opportunity.asset_type == asset_type)

        opportunities = session.exec(statement).all()

    return [opportunity_to_response(opp) for opp in opportunities]


@app.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
def get_opportunity(opportunity_id: int):
    with Session(engine) as session:
        opportunity = session.get(Opportunity, opportunity_id)

        if opportunity is None:
            raise HTTPException(status_code=404, detail="Opportunity not found.")

    return opportunity_to_response(opportunity)


@app.post("/opportunities/{opportunity_id}/rank")
def rank_opportunity_suppliers(opportunity_id: int, payload: RankRequest = RankRequest()):
    try:
        results = rank_suppliers(
            opportunity_id=opportunity_id,
            top_n=payload.top_n,
            save=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "opportunity_id": opportunity_id,
        "top_n": payload.top_n,
        "results": results,
    }


@app.get("/opportunities/{opportunity_id}/matches")
def list_saved_matches(opportunity_id: int):
    with Session(engine) as session:
        opportunity = session.get(Opportunity, opportunity_id)

        if opportunity is None:
            raise HTTPException(status_code=404, detail="Opportunity not found.")

    matches = get_saved_matches(opportunity_id)

    with Session(engine) as session:
        enriched = []

        for match in matches:
            supplier = session.get(Supplier, match["supplier_id"])

            enriched.append(
                {
                    **match,
                    "supplier": (
                        supplier_to_response(supplier).model_dump()
                        if supplier
                        else None
                    ),
                }
            )

    return {
        "opportunity_id": opportunity_id,
        "matches": enriched,
    }


@app.get("/opportunities/{opportunity_id}/entrants")
def list_entrant_matches(
    opportunity_id: int,
    top_n: int = Query(default=5, ge=1, le=50),
):
    try:
        results = rank_entrants(
            opportunity_id=opportunity_id,
            top_n=top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "opportunity_id": opportunity_id,
        "top_n": top_n,
        "results": results,
    }


@app.get("/suppliers", response_model=list[SupplierResponse])
def list_suppliers(
    state: Optional[str] = Query(default=None),
    naics: Optional[str] = Query(default=None),
    psc: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    with Session(engine) as session:
        statement = select(Supplier)

        if state:
            statement = statement.where(Supplier.state == state)

        suppliers = session.exec(statement).all()

    # SQLite JSON text filtering is easier and safer to do in Python for demo scale.
    if naics:
        suppliers = [
            supplier
            for supplier in suppliers
            if naics in parse_json_list(supplier.naics_codes_json)
        ]

    if psc:
        suppliers = [
            supplier
            for supplier in suppliers
            if psc in parse_json_list(supplier.psc_codes_json)
        ]

    paged = suppliers[offset : offset + limit]

    return [supplier_to_response(supplier) for supplier in paged]


@app.get("/suppliers/{supplier_id}", response_model=SupplierResponse)
def get_supplier(supplier_id: int):
    with Session(engine) as session:
        supplier = session.get(Supplier, supplier_id)

        if supplier is None:
            raise HTTPException(status_code=404, detail="Supplier not found.")

    return supplier_to_response(supplier)


@app.post("/opportunities/{opportunity_id}/assign", response_model=InspectionResponse)
def assign_supplier(opportunity_id: int, payload: AssignSupplierRequest):
    with Session(engine) as session:
        opportunity = session.get(Opportunity, opportunity_id)

        if opportunity is None:
            raise HTTPException(status_code=404, detail="Opportunity not found.")

        supplier = session.get(Supplier, payload.supplier_id)

        if supplier is None:
            raise HTTPException(status_code=404, detail="Supplier not found.")

        inspection = Inspection(
            opportunity_id=opportunity_id,
            supplier_id=payload.supplier_id,
            status="assigned",
        )

        session.add(inspection)
        session.commit()
        session.refresh(inspection)

    return inspection_to_response(inspection)


@app.post("/inspections/{inspection_id}/upload", response_model=InspectionResponse)
def upload_inspection_image(
    inspection_id: int,
    file: UploadFile = File(...),
):
    allowed_suffixes = {".jpg", ".jpeg", ".png"}

    suffix = Path(file.filename).suffix.lower()

    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail="Only .jpg, .jpeg, and .png files are supported.",
        )

    with Session(engine) as session:
        inspection = session.get(Inspection, inspection_id)

        if inspection is None:
            raise HTTPException(status_code=404, detail="Inspection not found.")

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        output_path = UPLOAD_DIR / f"inspection_{inspection_id}{suffix}"

        with output_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        inspection.uploaded_image_path = str(output_path)
        inspection.status = "image_uploaded"

        session.add(inspection)
        session.commit()
        session.refresh(inspection)

    return inspection_to_response(inspection)


@app.post("/inspections/{inspection_id}/analyze", response_model=DefectResultResponse)
def analyze_inspection_image(
    inspection_id: int,
    threshold: float = Query(default=DEFAULT_CV_THRESHOLD, ge=0.01, le=0.99),
):
    if not MODEL_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=(
                "Model file not found. Expected models/crack_resnet18.pt. "
                "Run Phase 5 training first."
            ),
        )

    with Session(engine) as session:
        inspection = session.get(Inspection, inspection_id)

        if inspection is None:
            raise HTTPException(status_code=404, detail="Inspection not found.")

        if not inspection.uploaded_image_path:
            raise HTTPException(
                status_code=400,
                detail="No image uploaded for this inspection.",
            )

        image_path = Path(inspection.uploaded_image_path)

        if not image_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Uploaded image not found on disk: {image_path}",
            )

        prediction_result = predict(
            image_path=image_path,
            model_path=MODEL_PATH,
            threshold=threshold,
        )

        defect_result = DefectResult(
            inspection_id=inspection_id,
            prediction=prediction_result["prediction"],
            confidence=float(prediction_result["confidence"]),
            severity=prediction_result["severity"],
            crack_ratio=prediction_result["crack_ratio"],
            gradcam_path=prediction_result["gradcam_path"],
        )

        inspection.status = "analyzed"

        session.add(defect_result)
        session.add(inspection)
        session.commit()
        session.refresh(defect_result)

    return defect_result_to_response(defect_result)


@app.get("/inspections/{inspection_id}/report", response_model=ReportResponse)
def get_inspection_report(inspection_id: int):
    with Session(engine) as session:
        inspection = session.get(Inspection, inspection_id)

        if inspection is None:
            raise HTTPException(status_code=404, detail="Inspection not found.")

        opportunity = session.get(Opportunity, inspection.opportunity_id)
        supplier = session.get(Supplier, inspection.supplier_id)

        if opportunity is None:
            raise HTTPException(status_code=404, detail="Opportunity not found.")

        if supplier is None:
            raise HTTPException(status_code=404, detail="Supplier not found.")

        match = session.exec(
            select(Match)
            .where(Match.opportunity_id == opportunity.id)
            .where(Match.supplier_id == supplier.id)
        ).first()

        defect_result = session.exec(
            select(DefectResult)
            .where(DefectResult.inspection_id == inspection_id)
            .order_by(DefectResult.created_at.desc())
        ).first()

    match_payload = None

    if match:
        match_payload = {
            "rank": match.rank,
            "final_score": match.final_score,
            "score_breakdown": parse_json_list(match.score_breakdown_json),
            "top_factors": parse_json_list(match.top_factors_json),
            "concerns": parse_json_list(match.concerns_json),
            "compliance_outcomes": parse_json_list(
                match.compliance_outcomes_json
            ),
        }

    return ReportResponse(
        inspection=inspection_to_response(inspection).model_dump(),
        opportunity=opportunity_to_response(opportunity).model_dump(),
        supplier=supplier_to_response(supplier).model_dump(),
        match=match_payload,
        defect_result=(
            defect_result_to_response(defect_result).model_dump()
            if defect_result
            else None
        ),
    )