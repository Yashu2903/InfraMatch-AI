import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

STATES = ["CT", "DE", "MA", "MD", "NJ", "NY", "PA"]

STATE_CITIES = {
    "NY": [
        "New York",
        "Buffalo",
        "Rochester",
        "Syracuse",
        "Albany",
        "Yonkers",
        "White Plains",
        "Poughkeepsie",
        "Binghamton",
    ],
    "PA": [
        "Philadelphia",
        "Pittsburgh",
        "Allentown",
        "Erie",
        "Reading",
        "Scranton",
        "Harrisburg",
        "Lancaster",
        "Bethlehem",
    ],
    "NJ": [
        "Newark",
        "Jersey City",
        "Paterson",
        "Trenton",
        "Elizabeth",
        "Camden",
        "Edison",
        "Atlantic City",
        "Hoboken",
        "Princeton",
    ],
    "MD": [
        "Baltimore",
        "Annapolis",
        "Frederick",
        "Rockville",
        "Silver Spring",
        "Gaithersburg",
        "Hagerstown",
        "College Park",
        "Bowie",
        "Laurel",
    ],
    "MA": [
        "Boston",
        "Worcester",
        "Springfield",
        "Cambridge",
        "Lowell",
        "New Bedford",
        "Quincy",
        "Somerville",
        "Newton",
    ],
    "CT": ["Hartford", "New Haven", "Bridgeport", "Stamford", "Waterbury", "Norwalk", "Danbury"],
    "DE": ["Wilmington", "Dover", "Newark DE", "Middletown"],
}

ASSET_TO_NAICS = {
    "bridge_deck": ["541330", "541350"],
    "retaining_wall": ["541330", "237310"],
    "culvert": ["237310", "541350"],
    "pavement": ["237310", "541330"],
    "facade": ["541330", "541310"],
}

ASSET_TO_PSC = {
    "bridge_deck": ["C1LB", "C211", "Z1LB"],
    "retaining_wall": ["C211", "C219", "Z1LB"],
    "culvert": ["Z1LB", "C211"],
    "pavement": ["Z1LB", "Y1LB", "C211"],
    "facade": ["C211", "C219"],
}

SUBAGENCIES = [
    "Federal Highway Administration",
    "Public Buildings Service",
    "Federal Transit Administration",
    "Veterans Health Administration",
    "FEMA",
    "Federal Railroad Administration",
    "National Park Service",
    "Bureau of Reclamation",
    "Other",
]

SUBAGENCY_TO_AGENCY = {
    "Federal Highway Administration": "Department of Transportation",
    "Federal Transit Administration": "Department of Transportation",
    "Federal Railroad Administration": "Department of Transportation",
    "Public Buildings Service": "General Services Administration",
    "Veterans Health Administration": "Department of Veterans Affairs",
    "FEMA": "Department of Homeland Security",
    "National Park Service": "Department of the Interior",
    "Bureau of Reclamation": "Department of the Interior",
    "Other": "Other",
}

CERTIFICATIONS = [
    "PE_License",
    "ISO_9001",
    "DBE_Certified",
    "8(a)_Certified",
    "Bridge_Inspection_NHI",
    "OSHA_30",
]

SESSION_DEFAULTS = {
    "selected_opportunity_id": None,
    "selected_inspection_id": None,
    "created_inspections": [],
    "rank_results_by_opportunity": {},
    "entrant_results_by_opportunity": {},
    "defect_results_by_inspection": {},
    "report_by_inspection": {},
    "supplier_explorer_results": [],
}


st.set_page_config(
    page_title="InfraMatch AI",
    page_icon="🏗",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles():
    st.markdown(
        """
        <style>
        :root {
            --bg-top: #f2efe5;
            --bg-bottom: #d7e1da;
            --panel: rgba(255, 252, 247, 0.88);
            --panel-strong: #fffaf0;
            --line: rgba(55, 69, 58, 0.14);
            --text: #203228;
            --muted: #5e6d63;
            --accent: #1f6b52;
            --accent-2: #b46a2f;
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(180, 106, 47, 0.16), transparent 26%),
                radial-gradient(circle at top right, rgba(31, 107, 82, 0.18), transparent 24%),
                linear-gradient(180deg, var(--bg-top) 0%, var(--bg-bottom) 100%);
            color: var(--text);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #163a30 0%, #21493e 100%);
        }

        [data-testid="stSidebar"] * {
            color: #eef4f0;
        }

        [data-testid="stMetric"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 0.9rem 1rem;
            backdrop-filter: blur(8px);
            box-shadow: 0 10px 30px rgba(32, 50, 40, 0.06);
        }

        [data-testid="stForm"],
        [data-testid="stExpander"],
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 18px;
        }

        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
        }

        h1, h2, h3 {
            letter-spacing: -0.02em;
            color: var(--text);
        }

        .app-hero {
            padding: 1.35rem 1.5rem;
            border-radius: 24px;
            border: 1px solid var(--line);
            background: linear-gradient(135deg, rgba(255, 248, 237, 0.92), rgba(241, 247, 243, 0.82));
            box-shadow: 0 18px 40px rgba(24, 39, 31, 0.08);
            margin-bottom: 1rem;
        }

        .app-hero-title {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }

        .app-hero-copy {
            color: var(--muted);
            font-size: 1rem;
        }

        .stButton > button,
        [data-testid="baseButton-secondary"] {
            border-radius: 999px;
            border: 1px solid rgba(31, 107, 82, 0.22);
        }

        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, var(--accent) 0%, #2d8b69 100%);
            color: white;
            border: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialize_session_state():
    for key, value in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value.copy() if isinstance(value, dict | list) else value


def api_get(path: str, params: dict | None = None):
    response = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def api_post(path: str, json_body: dict | None = None, params: dict | None = None):
    response = requests.post(
        f"{API_BASE_URL}{path}",
        json=json_body,
        params=params,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def api_upload(path: str, file):
    files = {
        "file": (
            file.name,
            file.getvalue(),
            file.type or "application/octet-stream",
        )
    }
    response = requests.post(f"{API_BASE_URL}{path}", files=files, timeout=120)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=30, show_spinner=False)
def get_health():
    return api_get("/health")


@st.cache_data(ttl=30, show_spinner=False)
def get_opportunities():
    return api_get("/opportunities")


@st.cache_data(ttl=30, show_spinner=False)
def get_suppliers(limit: int = 500):
    return api_get("/suppliers", params={"limit": limit})


@st.cache_data(ttl=30, show_spinner=False)
def get_inspections():
    return api_get("/inspections")


def clear_cached_data():
    st.cache_data.clear()


def show_request_error(prefix: str, exc: Exception):
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        message = exc.response.text
    else:
        message = str(exc)
    st.error(f"{prefix}: {message}")


def format_money(value):
    if value is None:
        return "n/a"
    return f"${float(value):,.0f}"


def render_metric_row(items: list[tuple[str, Any]]):
    cols = st.columns(len(items))
    for col, (label, value) in zip(cols, items):
        col.metric(label, value)


def render_hero(title: str, copy: str):
    st.markdown(
        f"""
        <div class="app-hero">
            <div class="app-hero-title">{title}</div>
            <div class="app-hero-copy">{copy}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_opportunity_card(opp: dict):
    with st.container(border=True):
        st.subheader(opp["title"])
        render_metric_row(
            [
                ("State", opp["state"]),
                ("City", opp["city"]),
                ("Asset", opp["asset_type"]),
                ("Budget", format_money(opp["budget"])),
            ]
        )
        render_metric_row(
            [
                ("NAICS", opp["naics_code"]),
                ("PSC", opp["psc_code"]),
                ("Subagency", opp["awarding_subagency"]),
                ("Local Content Req.", f"{opp['required_local_content']:.1f}%"),
            ]
        )
        st.caption(
            f"Agency: {opp['awarding_agency']} | "
            f"Risk tolerance: {opp['risk_tolerance']} | "
            f"Small business required: {opp['requires_small_business']} | "
            f"Certifications: {', '.join(opp['required_certifications']) or 'None'}"
        )


def breakdown_chart(score_breakdown: list[dict]):
    if not score_breakdown:
        st.info("No score breakdown available.")
        return

    df = pd.DataFrame(score_breakdown)
    df["weighted_score"] = pd.to_numeric(df["weighted_score"], errors="coerce").fillna(0)

    fig = px.bar(
        df,
        x="factor",
        y="weighted_score",
        hover_data=["value", "weight", "note"],
        title="Score Breakdown",
        color="weighted_score",
        color_continuous_scale=["#d8b08c", "#2d8b69"],
    )
    fig.update_layout(
        height=320,
        xaxis_title="",
        yaxis_title="Weighted Score",
        coloraxis_showscale=False,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


def get_supplier_label(item: dict) -> str:
    supplier = item.get("supplier")
    if isinstance(supplier, dict):
        return supplier.get("canonical_name", "Unknown supplier")
    if isinstance(supplier, str) and supplier.strip():
        return supplier
    supplier_name = item.get("supplier_name")
    if isinstance(supplier_name, str) and supplier_name.strip():
        return supplier_name
    return "Unknown supplier"


def get_rank_results(opportunity_id: int) -> list[dict]:
    return st.session_state["rank_results_by_opportunity"].get(opportunity_id, [])


def save_rank_results(opportunity_id: int, results: list[dict]):
    st.session_state["rank_results_by_opportunity"][opportunity_id] = results


def get_entrant_results(opportunity_id: int) -> list[dict]:
    return st.session_state["entrant_results_by_opportunity"].get(opportunity_id, [])


def save_entrant_results(opportunity_id: int, results: list[dict]):
    st.session_state["entrant_results_by_opportunity"][opportunity_id] = results


def get_defect_result(inspection_id: int) -> dict | None:
    return st.session_state["defect_results_by_inspection"].get(inspection_id)


def save_defect_result(inspection_id: int, result: dict):
    st.session_state["defect_results_by_inspection"][inspection_id] = result


def get_report(inspection_id: int) -> dict | None:
    return st.session_state["report_by_inspection"].get(inspection_id)


def save_report(inspection_id: int, report: dict):
    st.session_state["report_by_inspection"][inspection_id] = report


def render_match_result(item: dict, show_assign: bool = True, opportunity_id: int | None = None):
    supplier_name = get_supplier_label(item)

    with st.expander(
        f"#{item.get('rank')} - {supplier_name} | Score {item.get('final_score')}",
        expanded=False,
    ):
        top_factors = item.get("top_factors", [])[:3]
        if top_factors:
            top_cols = st.columns(len(top_factors))
            for idx, factor in enumerate(top_factors):
                top_cols[idx].metric(
                    factor["factor"],
                    factor.get("value"),
                    f"weighted {factor.get('weighted_score')}",
                )
                top_cols[idx].caption(factor.get("note", ""))

        st.markdown("#### Breakdown")
        breakdown_chart(item.get("score_breakdown", []))

        st.markdown("#### Compliance Outcomes")
        outcomes = item.get("compliance_outcomes", [])
        if outcomes:
            for outcome in outcomes:
                status = "PASS" if outcome.get("passed") else "FAIL"
                st.write(f"{status} **{outcome.get('name')}** - {outcome.get('message')}")
        else:
            st.info("No compliance outcomes available.")

        concerns = item.get("concerns", [])
        if concerns:
            st.markdown("#### Concerns")
            for concern in concerns:
                st.warning(f"{concern.get('factor')}: {concern.get('note')}")

        if show_assign and opportunity_id is not None:
            if st.button(
                f"Assign supplier #{item.get('supplier_id')}",
                key=f"assign_{opportunity_id}_{item.get('supplier_id')}_{item.get('rank')}",
            ):
                try:
                    result = api_post(
                        f"/opportunities/{opportunity_id}/assign",
                        json_body={"supplier_id": item["supplier_id"]},
                    )
                    save_created_inspection(result)
                    st.success(f"Inspection created: #{result['id']}")
                    clear_cached_data()
                except Exception as exc:
                    show_request_error("Assignment failed", exc)


def get_existing_inspections():
    try:
        inspections = get_inspections()
        st.session_state["created_inspections"] = inspections
        return inspections
    except Exception:
        return st.session_state.get("created_inspections", [])


def save_created_inspection(inspection: dict):
    inspections = st.session_state.get("created_inspections", [])
    if inspection["id"] not in [item["id"] for item in inspections]:
        inspections.append(inspection)
    st.session_state["created_inspections"] = sorted(inspections, key=lambda item: item["id"])
    st.session_state["selected_inspection_id"] = inspection["id"]


def page_create_project():
    render_hero(
        "Create Project",
        "Create a synthetic infrastructure opportunity with asset, scope, compliance, and federal procurement metadata.",
    )

    with st.form("create_project_form"):
        asset_type = st.selectbox("Asset type", list(ASSET_TO_NAICS.keys()))

        col1, col2 = st.columns(2)
        with col1:
            state = st.selectbox("State", STATES, index=STATES.index("NJ"))
            city = st.selectbox("City", STATE_CITIES[state])

        with col2:
            naics_code = st.selectbox("NAICS code", ASSET_TO_NAICS[asset_type])
            psc_code = st.selectbox("PSC code", ASSET_TO_PSC[asset_type])

        subagency = st.selectbox("Awarding subagency", SUBAGENCIES)
        agency = SUBAGENCY_TO_AGENCY[subagency]

        title_default = f"{city} {asset_type.replace('_', ' ').title()} Project"
        title = st.text_input("Project title", value=title_default)

        col3, col4, col5 = st.columns(3)
        with col3:
            budget = st.number_input("Budget", min_value=25_000.0, value=250_000.0, step=25_000.0)
        with col4:
            required_local_content = st.slider("Required local content (%)", 0.0, 100.0, 50.0, 5.0)
        with col5:
            risk_tolerance = st.selectbox("Risk tolerance", ["low", "medium", "high"], index=1)

        requires_small_business = st.checkbox("Requires small business", value=False)

        required_certifications = st.multiselect(
            "Required certifications",
            CERTIFICATIONS,
            default=["PE_License"] if naics_code.startswith("541") else ["OSHA_30"],
        )

        submitted = st.form_submit_button("Create opportunity", type="primary")

    if submitted:
        payload = {
            "title": title,
            "asset_type": asset_type,
            "state": state,
            "city": city,
            "naics_code": naics_code,
            "psc_code": psc_code,
            "awarding_agency": agency,
            "awarding_subagency": subagency,
            "budget": budget,
            "required_local_content": required_local_content,
            "requires_small_business": requires_small_business,
            "required_certifications": required_certifications,
            "risk_tolerance": risk_tolerance,
        }

        try:
            created = api_post("/opportunities", json_body=payload)
            st.session_state["selected_opportunity_id"] = created["id"]
            clear_cached_data()
            st.success(f"Created opportunity #{created['id']}: {created['title']}")
            render_opportunity_card(created)
        except Exception as exc:
            show_request_error("Failed to create opportunity", exc)


def page_supplier_rankings():
    render_hero(
        "Supplier Rankings",
        "Rank suppliers using NAICS, PSC, subagency familiarity, local content, certifications, recency, and risk signals.",
    )

    try:
        opportunities = get_opportunities()
    except Exception as exc:
        show_request_error("Could not load opportunities. Is FastAPI running", exc)
        return

    if not opportunities:
        st.warning("No opportunities found. Create one first.")
        return

    labels = {
        f"#{opp['id']} - {opp['title']} ({opp['state']} | PSC {opp['psc_code']} | {opp['awarding_subagency']})": opp
        for opp in opportunities
    }

    default_index = 0
    selected_opportunity_id = st.session_state.get("selected_opportunity_id")
    if selected_opportunity_id is not None:
        matching_labels = [label for label, opp in labels.items() if opp["id"] == selected_opportunity_id]
        if matching_labels:
            default_index = list(labels.keys()).index(matching_labels[0])

    selected_label = st.selectbox("Select opportunity", list(labels.keys()), index=default_index)
    opportunity = labels[selected_label]
    opportunity_id = opportunity["id"]
    st.session_state["selected_opportunity_id"] = opportunity_id

    render_opportunity_card(opportunity)

    col1, col2 = st.columns([1, 1])
    with col1:
        top_n = st.number_input("Top N", min_value=5, max_value=50, value=10, step=5)
    with col2:
        st.metric("Saved ranking results", len(get_rank_results(opportunity_id)))

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        if st.button("Rank incumbents", type="primary", use_container_width=True):
            try:
                result = api_post(
                    f"/opportunities/{opportunity_id}/rank",
                    json_body={"top_n": int(top_n)},
                )
                save_rank_results(opportunity_id, result["results"])
                st.success("Ranking complete.")
            except Exception as exc:
                show_request_error("Ranking failed", exc)

    with action_col2:
        if st.button("Find emerging suppliers", use_container_width=True):
            try:
                entrants = api_get(f"/opportunities/{opportunity_id}/entrants", params={"top_n": 5})
                save_entrant_results(opportunity_id, entrants["results"])
                st.success("Emerging supplier analysis complete.")
            except Exception as exc:
                show_request_error("Entrant ranking failed", exc)

    results = get_rank_results(opportunity_id)
    entrants = get_entrant_results(opportunity_id)

    st.markdown("## Top Incumbent Suppliers")
    if results:
        for item in results:
            render_match_result(item, show_assign=True, opportunity_id=opportunity_id)
    else:
        st.info("No incumbent ranking stored for this opportunity yet.")

    st.markdown("## Top Emerging Suppliers")
    if entrants:
        for item in entrants:
            render_match_result(item, show_assign=True, opportunity_id=opportunity_id)
    else:
        st.info("No emerging supplier ranking stored for this opportunity yet.")


def page_inspection():
    render_hero(
        "Inspection",
        "Upload an inspection image, run crack detection, and review the latest Grad-CAM severity output.",
    )

    try:
        inspections = api_get("/inspections")
        st.session_state["created_inspections"] = inspections
    except Exception:
        inspections = get_existing_inspections()
    selected_default = st.session_state.get("selected_inspection_id")

    st.info(
        "Inspections are created when you assign a supplier from Supplier Rankings. "
        "Select an inspection, upload an image, then run analysis."
    )

    if not inspections and selected_default is None:
        st.warning("No inspection selected yet. Go to Supplier Rankings and assign a supplier.")
        return

    inspection_ids = sorted(
        set([item["id"] for item in inspections] + ([selected_default] if selected_default else []))
    )

    inspection_id = st.selectbox(
        "Inspection ID",
        inspection_ids,
        index=inspection_ids.index(selected_default) if selected_default in inspection_ids else 0,
    )
    st.session_state["selected_inspection_id"] = inspection_id

    if inspections:
        inspection_lookup = {item["id"]: item for item in inspections}
        selected_inspection = inspection_lookup.get(inspection_id)
        if selected_inspection:
            render_metric_row(
                [
                    ("Status", selected_inspection.get("status", "unknown")),
                    ("Opportunity", selected_inspection.get("opportunity_id")),
                    ("Supplier", selected_inspection.get("supplier_id")),
                    ("Created", selected_inspection.get("created_at", "n/a")[:10]),
                ]
            )

    uploaded_file = st.file_uploader("Upload inspection image", type=["jpg", "jpeg", "png"])

    if uploaded_file is not None:
        st.image(uploaded_file, caption="Uploaded image preview", use_container_width=True)

        if st.button("Upload image", use_container_width=True):
            try:
                result = api_upload(f"/inspections/{inspection_id}/upload", uploaded_file)
                save_created_inspection(result)
                st.success(f"Image uploaded for inspection #{inspection_id}")
            except Exception as exc:
                show_request_error("Upload failed", exc)

    threshold = st.slider("Crack probability threshold", 0.01, 0.99, 0.50, 0.01)

    if st.button("Analyze inspection", type="primary", use_container_width=True):
        try:
            result = api_post(
                f"/inspections/{inspection_id}/analyze",
                params={"threshold": threshold},
            )
            save_defect_result(inspection_id, result)
            st.success("Analysis complete.")
        except Exception as exc:
            show_request_error("Analysis failed", exc)

    result = get_defect_result(inspection_id)

    if result:
        st.markdown("## Analysis Result")
        render_metric_row(
            [
                ("Prediction", result["prediction"]),
                ("Confidence", f"{result['confidence']:.2%}"),
                ("Severity", result["severity"]),
                ("Crack ratio", "n/a" if result["crack_ratio"] is None else f"{result['crack_ratio']:.4%}"),
            ]
        )

        gradcam_path = result.get("gradcam_path")
        if gradcam_path and Path(gradcam_path).exists():
            st.image(gradcam_path, caption="Grad-CAM overlay", use_container_width=True)
        elif gradcam_path:
            st.warning(f"Grad-CAM path returned, but file not found locally: {gradcam_path}")


def page_full_report():
    render_hero(
        "Full Report",
        "View the combined opportunity, supplier, match rationale, compliance outcomes, and inspection result in one place.",
    )

    selected_inspection_id = st.session_state.get("selected_inspection_id")

    if selected_inspection_id is None:
        st.warning("No inspection selected. Assign a supplier first.")
        return

    inspection_id = st.number_input(
        "Inspection ID",
        min_value=1,
        value=int(selected_inspection_id),
        step=1,
    )
    st.session_state["selected_inspection_id"] = int(inspection_id)

    if st.button("Load report", type="primary", use_container_width=True):
        try:
            report = api_get(f"/inspections/{inspection_id}/report")
            save_report(int(inspection_id), report)
        except Exception as exc:
            show_request_error("Could not load report", exc)

    report = get_report(int(inspection_id))

    if not report:
        st.info("No report loaded for this inspection yet.")
        return

    st.markdown("## Opportunity")
    render_opportunity_card(report["opportunity"])

    st.markdown("## Assigned Supplier")
    supplier = report["supplier"]
    with st.container(border=True):
        st.subheader(supplier["canonical_name"])
        render_metric_row(
            [
                ("State", supplier["state"]),
                ("Awards", supplier["past_awards_count"]),
                ("Total Award Value", format_money(supplier["total_award_value"])),
                ("Risk Score", supplier["risk_score"]),
            ]
        )
        st.caption(f"PSC history: {', '.join(supplier['psc_codes'])}")
        st.caption(f"Subagency history: {', '.join(supplier['subagencies'][:8])}")

    match = report.get("match")
    if match:
        st.markdown("## Match Explanation")
        st.metric("Final match score", match["final_score"])
        breakdown_chart(match.get("score_breakdown", []))

        st.markdown("### Compliance Outcomes")
        for outcome in match.get("compliance_outcomes", []):
            status = "PASS" if outcome.get("passed") else "FAIL"
            st.write(f"{status} **{outcome.get('name')}** - {outcome.get('message')}")
    else:
        st.info("No stored match explanation was found for this inspection.")

    defect = report.get("defect_result")
    if defect:
        st.markdown("## Inspection Result")
        render_metric_row(
            [
                ("Prediction", defect["prediction"]),
                ("Confidence", f"{defect['confidence']:.2%}"),
                ("Severity", defect["severity"]),
                ("Crack ratio", "n/a" if defect["crack_ratio"] is None else f"{defect['crack_ratio']:.4%}"),
            ]
        )

        gradcam_path = defect.get("gradcam_path")
        if gradcam_path and Path(gradcam_path).exists():
            st.image(gradcam_path, caption="Grad-CAM overlay", use_container_width=True)

    st.download_button(
        "Download report JSON",
        data=json.dumps(report, indent=2),
        file_name=f"inframatch_report_{inspection_id}.json",
        mime="application/json",
        use_container_width=True,
    )


def page_supplier_explorer():
    render_hero(
        "Supplier Explorer",
        "Inspect supplier records by state, NAICS, and PSC to understand market depth before running match workflows.",
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        state = st.selectbox("State filter", ["All"] + STATES)
    with col2:
        naics = st.text_input("NAICS filter", value="")
    with col3:
        psc = st.text_input("PSC filter", value="")

    params = {"limit": 500}

    if state != "All":
        params["state"] = state

    if naics.strip():
        params["naics"] = naics.strip()

    if psc.strip():
        params["psc"] = psc.strip()

    if st.button("Load suppliers", type="primary", use_container_width=True):
        try:
            suppliers = api_get("/suppliers", params=params)
            st.session_state["supplier_explorer_results"] = suppliers
        except Exception as exc:
            show_request_error("Supplier load failed", exc)

    suppliers = st.session_state.get("supplier_explorer_results", [])

    if suppliers:
        rows = []
        for supplier in suppliers:
            rows.append(
                {
                    "id": supplier["id"],
                    "name": supplier["canonical_name"],
                    "state": supplier["state"],
                    "awards": supplier["past_awards_count"],
                    "total_award_value": supplier["total_award_value"],
                    "psc_codes": ", ".join(supplier["psc_codes"][:5]),
                    "subagencies": ", ".join(supplier["subagencies"][:4]),
                    "risk_score": supplier["risk_score"],
                    "local_content_score": supplier["local_content_score"],
                    "small_business_flag": supplier["small_business_flag"],
                }
            )

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No supplier results loaded yet.")


def render_sidebar():
    st.sidebar.title("InfraMatch AI")
    st.sidebar.caption("Supplier matching + compliance + inspection")

    if st.sidebar.button("Refresh cached API data", use_container_width=True):
        clear_cached_data()

    try:
        health = get_health()
        st.sidebar.success("API connected")
        st.sidebar.caption(f"Endpoint: {API_BASE_URL}")
        st.sidebar.caption(f"Model exists: {health.get('model_exists')}")
    except Exception:
        st.sidebar.error("API not reachable")
        st.sidebar.caption(f"Expected API: {API_BASE_URL}")

    st.sidebar.markdown("### Working Context")
    st.sidebar.caption(f"Opportunity: {st.session_state.get('selected_opportunity_id') or 'none'}")
    st.sidebar.caption(f"Inspection: {st.session_state.get('selected_inspection_id') or 'none'}")
    st.sidebar.caption(f"Tracked inspections: {len(get_existing_inspections())}")

    return st.sidebar.radio(
        "Navigation",
        [
            "Create Project",
            "Supplier Rankings",
            "Inspection",
            "Full Report",
            "Supplier Explorer",
        ],
    )


def main():
    initialize_session_state()
    inject_styles()
    page = render_sidebar()

    if page == "Create Project":
        page_create_project()
    elif page == "Supplier Rankings":
        page_supplier_rankings()
    elif page == "Inspection":
        page_inspection()
    elif page == "Full Report":
        page_full_report()
    elif page == "Supplier Explorer":
        page_supplier_explorer()


if __name__ == "__main__":
    main()
