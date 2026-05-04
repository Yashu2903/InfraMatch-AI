import json
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ModuleNotFoundError:
    yaml = None


DEFAULT_RULES_PATH = Path(__file__).with_name("rules.yaml")


def parse_json_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [str(item) for item in value if item is not None]

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return []

        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item is not None]
        except json.JSONDecodeError:
            return []

    return []


def _parse_rules_text(text: str) -> dict:
    if yaml is not None:
        data = yaml.safe_load(text)
    else:
        # JSON is a valid subset of YAML. Keep the bundled rules file
        # JSON-compatible so the engine still runs without PyYAML installed.
        data = json.loads(text)

    if not isinstance(data, dict):
        raise ValueError("Rules file must parse to an object.")

    return data


def load_rules(path: str | Path = DEFAULT_RULES_PATH) -> list[dict]:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Compliance rules file not found: {path}")

    text = path.read_text(encoding="utf-8")
    data = _parse_rules_text(text)

    rules = data.get("rules", [])

    if not isinstance(rules, list):
        raise ValueError("Rules file must contain a top-level 'rules' list.")

    return rules


def get_attr(obj: Any, field_name: str) -> Any:
    return getattr(obj, field_name, None)


def get_source_value(source: str, supplier: Any, opportunity: Any) -> Any:
    """
    Supports source strings like:
    - opportunity.required_local_content
    - supplier.local_content_score
    """
    if not source or "." not in source:
        return None

    root, field_name = source.split(".", 1)

    if root == "supplier":
        return get_attr(supplier, field_name)

    if root == "opportunity":
        return get_attr(opportunity, field_name)

    return None


def compare_numeric(left: float, right: float, operator: str) -> bool:
    if operator == ">=":
        return left >= right

    if operator == ">":
        return left > right

    if operator == "<=":
        return left <= right

    if operator == "<":
        return left < right

    if operator == "==":
        return left == right

    raise ValueError(f"Unsupported numeric operator: {operator}")


def apply_numeric_threshold(rule: dict, supplier: Any, opportunity: Any) -> dict:
    field = rule["field"]
    operator = rule.get("operator", ">=")
    source = rule["source"]

    supplier_value = float(get_attr(supplier, field) or 0)
    required_value = float(get_source_value(source, supplier, opportunity) or 0)

    passed = compare_numeric(supplier_value, required_value, operator)

    if required_value <= 0:
        partial_score = 1.0
    elif operator in {">=", ">"}:
        partial_score = min(supplier_value / required_value, 1.0)
    elif operator in {"<=", "<"}:
        partial_score = 1.0 if passed else max(0.0, required_value / supplier_value)
    else:
        partial_score = 1.0 if passed else 0.0

    message = (
        f"Local content score {supplier_value:.1f}% "
        f"{'meets' if passed else 'is below'} "
        f"project requirement of {required_value:.1f}%."
    )

    return {
        "rule_id": rule["id"],
        "name": rule["name"],
        "type": rule["type"],
        "passed": passed,
        "partial_score": round(partial_score, 4),
        "weight": float(rule["weight"]),
        "weighted_score": round(partial_score * float(rule["weight"]), 4),
        "message": message,
        "supplier_value": supplier_value,
        "required_value": required_value,
    }


def apply_boolean_match(rule: dict, supplier: Any, opportunity: Any) -> dict:
    field = rule["field"]
    required_when = rule.get("required_when")

    requirement_active = bool(get_source_value(required_when, supplier, opportunity))
    supplier_value = bool(get_attr(supplier, field))

    if not requirement_active:
        passed = True
        partial_score = 1.0
        message = "Small-business set-aside is not required for this opportunity."
    else:
        passed = supplier_value is True
        partial_score = 1.0 if passed else 0.0

        if passed:
            message = "Supplier satisfies the small-business set-aside requirement."
        else:
            message = "Opportunity requires small-business participation, but supplier is not flagged as small business."

    return {
        "rule_id": rule["id"],
        "name": rule["name"],
        "type": rule["type"],
        "passed": passed,
        "partial_score": round(partial_score, 4),
        "weight": float(rule["weight"]),
        "weighted_score": round(partial_score * float(rule["weight"]), 4),
        "message": message,
        "supplier_value": supplier_value,
        "required_value": requirement_active,
    }


def apply_set_subset(rule: dict, supplier: Any, opportunity: Any) -> dict:
    field = rule["field"]
    required_source = rule["required"]

    # Map rule names to actual model JSON fields.
    supplier_json_field = f"{field}_json"
    opportunity_json_field = f"required_{field}_json"

    supplier_values = set(parse_json_list(get_attr(supplier, supplier_json_field)))

    if required_source.startswith("opportunity."):
        required_field = required_source.split(".", 1)[1]
        required_json_field = f"{required_field}_json"
        required_values = set(parse_json_list(get_attr(opportunity, required_json_field)))
    else:
        required_values = set(parse_json_list(required_source))

    missing = sorted(required_values - supplier_values)

    if not required_values:
        passed = True
        partial_score = 1.0
        message = "No specific certifications are required for this opportunity."
    else:
        passed = len(missing) == 0
        partial_score = len(required_values & supplier_values) / len(required_values)

        if passed:
            message = "Supplier has all required certifications."
        else:
            message = (
                "Supplier is missing required certifications: "
                + ", ".join(missing)
                + "."
            )

    return {
        "rule_id": rule["id"],
        "name": rule["name"],
        "type": rule["type"],
        "passed": passed,
        "partial_score": round(partial_score, 4),
        "weight": float(rule["weight"]),
        "weighted_score": round(partial_score * float(rule["weight"]), 4),
        "message": message,
        "supplier_value": sorted(supplier_values),
        "required_value": sorted(required_values),
        "missing": missing,
    }


def apply_rule(rule: dict, supplier: Any, opportunity: Any) -> dict:
    rule_type = rule["type"]

    if rule_type == "numeric_threshold":
        return apply_numeric_threshold(rule, supplier, opportunity)

    if rule_type == "boolean_match":
        return apply_boolean_match(rule, supplier, opportunity)

    if rule_type == "set_subset":
        return apply_set_subset(rule, supplier, opportunity)

    raise ValueError(f"Unsupported compliance rule type: {rule_type}")


def evaluate_rules(
    supplier: Any,
    opportunity: Any,
    rules_path: str | Path = DEFAULT_RULES_PATH,
) -> tuple[float, list[dict]]:
    rules = load_rules(rules_path)

    outcomes = []

    for rule in rules:
        outcome = apply_rule(rule, supplier, opportunity)
        outcomes.append(outcome)

    total_weight = sum(float(rule.get("weight", 0)) for rule in rules)

    if total_weight <= 0:
        return 0.0, outcomes

    weighted_score = sum(
        outcome["partial_score"] * outcome["weight"]
        for outcome in outcomes
    ) / total_weight

    return round(weighted_score, 4), outcomes


def compliance_fit(supplier: Any, opportunity: Any) -> float:
    score, _ = evaluate_rules(supplier, opportunity)
    return score
