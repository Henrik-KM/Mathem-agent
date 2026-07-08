from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .models import MathemProduct


@dataclass(frozen=True, slots=True)
class PreferenceProfile:
    raw: str = ""
    avoid: tuple[str, ...] = ()
    vegetarian: bool = False
    vegan: bool = False
    pescetarian: bool = False
    high_protein: bool = False
    fast: bool = False
    budget: bool = True
    mild: bool = False

    @classmethod
    def parse(cls, raw: str = "", avoid: list[str] | None = None) -> "PreferenceProfile":
        lowered = raw.lower()
        avoid_terms = tuple(term.strip().lower() for term in (avoid or []) if term.strip())
        return cls(
            raw=raw,
            avoid=avoid_terms,
            vegetarian=any(term in lowered for term in ("vegetar", "vego", "köttfri")),
            vegan="vegansk" in lowered or "vegan" in lowered,
            pescetarian="pesc" in lowered,
            high_protein="protein" in lowered,
            fast=any(term in lowered for term in ("snabb", "enkelt", "vardag", "max 30")),
            budget=not any(term in lowered for term in ("premium", "lyx", "fest")),
            mild=any(term in lowered for term in ("mild", "inte stark", "barnvän")),
        )


def tokenize(text: str) -> list[str]:
    return [part for part in re.split(r"\W+", text.lower()) if len(part) >= 3]


def product_contains_any(product: MathemProduct, terms: tuple[str, ...] | list[str]) -> bool:
    haystack = product.display_name.lower() + " " + product.raw_text.lower()
    return any(term.lower() in haystack for term in terms if term)


def score_product(product: MathemProduct, query: str, profile: PreferenceProfile) -> float:
    """Heuristic product score for a personal Mathem value basket."""
    if product_contains_any(product, profile.avoid):
        return -10_000.0

    text = product.display_name.lower() + " " + product.raw_text.lower()
    score = 0.0

    meat_terms = [
        "nötfärs",
        "kött",
        "fläsk",
        "bacon",
        "kyckling",
        "korv",
        "skinka",
        "lamm",
    ]
    fish_terms = ["lax", "torsk", "räkor", "fisk", "tonfisk"]
    dairy_egg_terms = ["ost", "mjölk", "grädde", "yoghurt", "ägg", "crème", "creme"]
    if profile.vegan and any(term in text for term in meat_terms + fish_terms + dairy_egg_terms):
        return -10_000.0
    if profile.vegetarian and any(term in text for term in meat_terms + fish_terms):
        return -10_000.0
    if profile.pescetarian and any(term in text for term in meat_terms):
        return -10_000.0

    query_terms = tokenize(query)
    name_terms = tokenize(product.display_name)
    score += 10.0 * sum(term in name_terms for term in query_terms)
    score += 3.0 * sum(term in text for term in query_terms)

    if product.is_prismatch:
        score += 35.0
    if product.is_offer:
        score += 18.0

    if product.price is not None:
        score += max(0.0, 45.0 - min(product.price, 45.0))
        if profile.budget:
            score += max(0.0, 35.0 - min(product.price, 35.0)) * 0.6
    else:
        score -= 20.0

    if product.unit_price is not None and math.isfinite(product.unit_price):
        score += max(0.0, 60.0 - min(product.unit_price, 60.0)) * 0.12

    if "garant" in text:
        score += 3.0
    if any(term in text for term in ("nyckelhål", "keyhole", "från sverige", "msc")):
        score += 2.0
    if profile.high_protein and any(
        term in text for term in ("kyckling", "ägg", "kvarg", "keso", "tofu", "tonfisk", "bön", "linser")
    ):
        score += 8.0

    if any(term in text for term in ("godis", "glass", "energidryck", "läsk", "blöjor", "hund", "katt")):
        score -= 25.0

    return score


def choose_best_product(
    products: list[MathemProduct],
    query: str,
    profile: PreferenceProfile,
    exclude_ids: set[str] | None = None,
) -> MathemProduct | None:
    exclude_ids = exclude_ids or set()
    candidates = [product for product in products if str(product.id) not in exclude_ids]
    if not candidates:
        candidates = products
    if not candidates:
        return None
    return max(candidates, key=lambda product: score_product(product, query=query, profile=profile))
