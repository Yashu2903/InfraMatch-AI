import argparse
import json

from inframatch.matching.ranker import rank_entrants, rank_suppliers


def print_result(item: dict) -> None:
    print(f"\n#{item['rank']} {item['supplier']}")
    print(f"Final score: {item['final_score']:.4f}")

    print("Top factors:")
    for factor in item["top_factors"]:
        print(
            f"  - {factor['factor']}: {factor['value']} "
            f"(weighted {factor['weighted_score']}) - {factor['note']}"
        )

    print("Concerns:")
    for concern in item["concerns"]:
        print(
            f"  - {concern['factor']}: {concern['value']} - {concern['note']}"
        )

    print("Compliance outcomes:")
    for outcome in item["compliance_outcomes"]:
        print(
            f"  - {outcome['rule']}: pass={outcome['passed']} "
            f"(score {outcome['score']}) - {outcome['note']}"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--opp-id", type=int, default=1)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--entrants", action="store_true")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.entrants:
        results = rank_entrants(opportunity_id=args.opp_id, top_n=args.top_n)
    else:
        results = rank_suppliers(opportunity_id=args.opp_id, top_n=args.top_n)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    label = "Top Emerging Suppliers" if args.entrants else "Top Ranked Suppliers"
    print(f"\n{label} for opportunity {args.opp_id}")

    for item in results:
        print_result(item)


if __name__ == "__main__":
    main()
