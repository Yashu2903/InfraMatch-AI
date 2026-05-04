import json
from functools import lru_cache
from pathlib import Path
from typing import Any


POLICY_PATH = Path(__file__).resolve().parent / "policies" / "phase3_compliance.yaml"

try:
    import yaml  # type: ignore
except ModuleNotFoundError:
    yaml = None


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


def _load_policy_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Compliance policy file not found: {path}")

    return path.read_text(encoding="utf-8")


def _parse_policy_text(text: str) -> dict[str, Any]:
    if yaml is not None:
        parsed = yaml.safe_load(text)
    else:
        # JSON is a valid subset of YAML. The bundled policy file uses
        # JSON-compatible YAML so the repo stays runnable without PyYAML.
        parsed = json.loads(text)

    if not isinstance(parsed, dict):
        raise ValueError("Compliance policy must parse to an object.")

    return parsed


def _validate_rule(rule: dict[str, Any]) -> None:
    required_keys = {"id", "type", "supplier_field", "opportunity_field"}
    missing = sorted(required_keys - set(rule))

    if missing:
        raise ValueError(f"Compliance rule missing required keys: {missing}")

    if rule["type"] not in {"threshold_ratio", "boolean_requirement", "subset_ratio"}:
        raise ValueError(f"Unsupported compliance rule type: {rule['type']}")

    weight = float(rule.get("weight", 1.0))

    if weight < 0:
        raise ValueError(f"Compliance rule weight must be non-negative: {rule['id']}")


def _validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    rules = policy.get("rules")

    if not isinstance(rules, list) or not rules:
        raise ValueError("Compliance policy must contain a non-empty rules list.")

    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("Each compliance rule must be an object.")

        _validate_rule(rule)

    aggregate = policy.get("aggregate", {})

    if aggregate and aggregate.get("strategy", "weighted_average") != "weighted_average":
        raise ValueError("Only weighted_average compliance aggregation is supported.")

    return policy


@lru_cache(maxsize=1)
def load_compliance_policy(path: str | None = None) -> dict[str, Any]:
    policy_path = Path(path) if path else POLICY_PATH
    text = _load_policy_text(policy_path)
    policy = _parse_policy_text(text)
    return _validate_policy(policy)


def _get_field(source: Any, field_name: str) -> Any:
    return getattr(source, field_name, None)


def _evaluate_threshold_ratio(rule: dict[str, Any], supplier, opportunity) -> dict[str, Any]:
    required = float(_get_field(opportunity, rule["opportunity_field"]) or 0)
    actual = float(_get_field(supplier, rule["supplier_field"]) or 0)
    score = 1.0 if required <= 0 else min(actual / required, 1.0)
    passed = actual >= required if required > 0 else bool(
        rule.get("pass_when_requirement_missing", True)
    )
    messages = rule.get("messages", {})
    note = (
        messages.get("missing_requirement", "No requirement.")
        if required <= 0
        else messages.get("template", "{actual} vs {required}.").format(
            actual=actual,
            required=required,
        )
    )

    return {
        "rule": rule["id"],
        "rule_type": rule["type"],
        "required": round(required, 2),
        "actual": round(actual, 2),
        "passed": passed,
        "score": round(score, 4),
        "weight": float(rule.get("weight", 1.0)),
        "note": note,
    }


def _evaluate_boolean_requirement(rule: dict[str, Any], supplier, opportunity) -> dict[str, Any]:
    required = bool(_get_field(opportunity, rule["opportunity_field"]))
    actual = bool(_get_field(supplier, rule["supplier_field"]))
    score = 1.0 if (not required or actual) else 0.0
    passed = not required or actual
    messages = rule.get("messages", {})

    if not required:
        note = messages.get("missing_requirement", "No requirement.")
    elif actual:
        note = messages.get("pass", "Requirement satisfied.")
    else:
        note = messages.get("fail", "Requirement not satisfied.")

    return {
        "rule": rule["id"],
        "rule_type": rule["type"],
        "required": required,
        "actual": actual,
        "passed": passed,
        "score": round(score, 4),
        "weight": float(rule.get("weight", 1.0)),
        "note": note,
    }


def _evaluate_subset_ratio(rule: dict[str, Any], supplier, opportunity) -> dict[str, Any]:
    required_values = set(
        parse_json_list(_get_field(opportunity, rule["opportunity_field"]))
    )
    actual_values = set(parse_json_list(_get_field(supplier, rule["supplier_field"])))
    matched = sorted(actual_values & required_values)
    missing = sorted(required_values - actual_values)
    score = 1.0 if not required_values else len(matched) / len(required_values)
    passed = not missing
    messages = rule.get("messages", {})

    if not required_values:
        note = messages.get("missing_requirement", "No requirement.")
    elif not missing:
        note = messages.get("pass_template", "Matched: {matched_csv}.").format(
            matched_csv=", ".join(matched) or "none",
        )
    else:
        note = messages.get("fail_template", "Missing: {missing_csv}.").format(
            missing_csv=", ".join(missing) or "none",
        )

    return {
        "rule": rule["id"],
        "rule_type": rule["type"],
        "required": sorted(required_values),
        "actual": sorted(actual_values),
        "matched": matched,
        "missing": missing,
        "passed": passed,
        "score": round(score, 4),
        "weight": float(rule.get("weight", 1.0)),
        "note": note,
    }


def evaluate_rule(rule: dict[str, Any], supplier, opportunity) -> dict[str, Any]:
    rule_type = rule["type"]

    if rule_type == "threshold_ratio":
        return _evaluate_threshold_ratio(rule, supplier, opportunity)

    if rule_type == "boolean_requirement":
        return _evaluate_boolean_requirement(rule, supplier, opportunity)

    if rule_type == "subset_ratio":
        return _evaluate_subset_ratio(rule, supplier, opportunity)

    raise ValueError(f"Unsupported compliance rule type: {rule_type}")


def evaluate_compliance_policy(
    supplier,
    opportunity,
    policy: dict[str, Any] | None = None,
) -> tuple[float, list[dict[str, Any]]]:
    policy = policy or load_compliance_policy()
    enabled_rules = [rule for rule in policy["rules"] if rule.get("enabled", True)]

    if not enabled_rules:
        return 0.0, []

    outcomes = [evaluate_rule(rule, supplier, opportunity) for rule in enabled_rules]

    total_weight = sum(float(item["weight"]) for item in outcomes)

    if total_weight <= 0:
        return 0.0, outcomes

    weighted_score = sum(item["score"] * float(item["weight"]) for item in outcomes)
    return weighted_score / total_weight, outcomes
