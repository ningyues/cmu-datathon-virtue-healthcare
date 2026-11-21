"""Rank and display nearby facilities using scores supplied by the search."""

from collections.abc import Iterable
from math import inf, isfinite

from app.location_matching import rank_by_distance


def _fit_score(value: object) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return score if isfinite(score) else None


def print_nearby_results(
    candidates: Iterable[dict], *, sort_by: str = "fit", service_search: bool = False,
) -> None:
    """Print up to ten results. A missing Fit Score displays as Pending."""
    ranked = [(row, _fit_score(row.get("fit_score"))) for row in rank_by_distance(candidates)]
    if not ranked:
        return

    if sort_by == "fit" and any(score is not None for _, score in ranked):
        # The stable sort keeps nearest first for tied and pending scores.
        ranked.sort(key=lambda item: -item[1] if item[1] is not None else inf)
        print("Sorted by Fit Score (highest first, then nearest)")
    elif service_search and sort_by != "distance":
        ranked.sort(key=lambda item: item[0]["service_match"] != "listed_in_dataset")
        pending = "Fit Scores pending. " if sort_by == "fit" else ""
        print(f"{pending}Sorted by dataset service evidence (claims first, then nearest)")
    elif sort_by == "fit":
        print("Fit Scores pending. Showing nearest facilities first.")
    else:
        print("Sorted by distance (nearest first)")

    print(f"{'Distance':>9}  {'Fit Score':>9}  Facility")
    for row, score in ranked[:10]:
        name = row["name_standardized"] or row["name"]
        city = row["address_city"]
        facility = f"{name} ({city})" if city else name
        distance = row["distance_km"]
        distance_text = f"{distance:.1f} km" if distance is not None else "—"
        score_text = f"{score:.2f}" if score is not None else "Pending"
        print(f"{distance_text:>9}  {score_text:>9}  {facility}")
        if service_search:
            evidence = row["service_evidence"]
            if evidence:
                print(f"{'':22}Dataset claim ({evidence['field']}): {evidence['text']}")
            else:
                print(f"{'':22}Related specialty only. Service not verified.")
