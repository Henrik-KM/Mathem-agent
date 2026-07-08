from __future__ import annotations

import html
import json
import re
import time
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin

from .config import get_settings
from .models import MathemProduct

BASE_URL = "https://www.mathem.se"
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
RECIPE_LINK_RE = re.compile(
    r'href="(?P<href>[^"]*(?:/se/recipes/|/se/recept/)[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")


class MathemError(RuntimeError):
    pass


class MathemAuthError(MathemError):
    pass


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = (
            value.replace("\xa0", " ")
            .replace("kr", "")
            .replace("SEK", "")
            .replace("/kg", "")
            .replace("/l", "")
            .replace("/st", "")
            .strip()
        )
        cleaned = cleaned.replace(" ", "").replace(",", ".")
        match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
        if match:
            return float(match.group(0))
    return None


def _coalesce(*values: Any, default: str = "") -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def _string_values(obj: Any, max_values: int = 250) -> list[str]:
    values: list[str] = []
    stack = [obj]
    while stack and len(values) < max_values:
        current = stack.pop()
        if isinstance(current, str):
            if current.strip():
                values.append(current.strip())
        elif isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return values


def extract_next_data(html_text: str) -> dict[str, Any]:
    match = NEXT_DATA_RE.search(html_text)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def iter_product_items(obj: Any) -> Iterable[dict[str, Any]]:
    """Yield product-like nodes from Mathem's Next.js payload."""
    stack = [obj]
    seen_object_ids: set[int] = set()
    while stack:
        current = stack.pop()
        if id(current) in seen_object_ids:
            continue
        seen_object_ids.add(id(current))

        if isinstance(current, dict):
            attrs = current.get("attributes")
            if current.get("type") == "product" and isinstance(attrs, dict):
                yield current
                continue
            if any(key in current for key in ("grossPrice", "grossUnitPrice", "brand", "nameExtra")) and current.get("id"):
                yield {"type": "product", "attributes": current}
                continue
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def product_from_item(item: dict[str, Any]) -> MathemProduct | None:
    attrs = item.get("attributes", item)
    if not isinstance(attrs, dict):
        return None

    product_id = _coalesce(attrs.get("id"), item.get("id"), default="")
    name = str(_coalesce(attrs.get("name"), attrs.get("title"), default="")).strip()
    if not product_id or not name:
        return None

    labels: list[str] = []
    for classifier in attrs.get("clientClassifiers", []) or []:
        if isinstance(classifier, dict) and classifier.get("name"):
            labels.append(str(classifier["name"]))
        elif isinstance(classifier, str):
            labels.append(classifier)

    promotions: list[str] = []
    for promotion in attrs.get("promotions", []) or []:
        if isinstance(promotion, dict):
            text = _coalesce(
                promotion.get("title"),
                promotion.get("name"),
                promotion.get("description"),
                promotion.get("label"),
                default="",
            )
            if text:
                promotions.append(str(text))
        elif isinstance(promotion, str):
            promotions.append(promotion)

    raw_text = " ".join(_string_values(attrs))[:5000]
    url_value = str(_coalesce(attrs.get("url"), attrs.get("path"), attrs.get("href"), default=""))
    product_url = urljoin(BASE_URL, url_value) if url_value else ""

    return MathemProduct(
        id=product_id,
        name=name,
        brand=str(_coalesce(attrs.get("brand"), attrs.get("manufacturer"), default="")),
        description=str(
            _coalesce(
                attrs.get("nameExtra"),
                attrs.get("description"),
                attrs.get("packageSize"),
                attrs.get("quantity"),
                default="",
            )
        ),
        price=_as_float(
            _coalesce(
                attrs.get("grossPrice"),
                attrs.get("price"),
                attrs.get("currentPrice"),
                attrs.get("displayPrice"),
                default=None,
            )
        ),
        currency=str(_coalesce(attrs.get("currency"), default="SEK")),
        unit_price=_as_float(
            _coalesce(
                attrs.get("grossUnitPrice"),
                attrs.get("unitPrice"),
                attrs.get("comparePrice"),
                default=None,
            )
        ),
        unit_price_unit=str(
            _coalesce(
                attrs.get("unitPriceQuantityAbbreviation"),
                attrs.get("unit"),
                attrs.get("comparisonUnit"),
                default="",
            )
        ),
        labels=labels,
        promotions=promotions,
        url=product_url,
        raw_text=raw_text,
        raw=attrs,
    )


def products_from_html(html_text: str, limit: int = 50) -> list[MathemProduct]:
    next_data = extract_next_data(html_text)
    products: list[MathemProduct] = []
    seen: set[str] = set()
    for item in iter_product_items(next_data):
        product = product_from_item(item)
        if not product:
            continue
        product_id = str(product.id)
        if product_id in seen:
            continue
        seen.add(product_id)
        products.append(product)
        if len(products) >= limit:
            break
    return products


def recipes_from_html(html_text: str, limit: int = 100) -> list[dict[str, str]]:
    recipes: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in RECIPE_LINK_RE.finditer(html_text):
        href = html.unescape(match.group("href"))
        title_html = match.group("title")
        title = html.unescape(TAG_RE.sub("", title_html)).strip()
        if not title or href in seen:
            continue
        seen.add(href)
        recipes.append({"title": title, "url": urljoin(BASE_URL, href)})
        if len(recipes) >= limit:
            break
    return recipes


class MathemClient:
    def __init__(self, cookie: str | None = None, user_agent: str | None = None, timeout: float = 30.0):
        settings = get_settings()
        self.cookie = cookie if cookie is not None else settings.cookie
        self.user_agent = user_agent or settings.user_agent
        self.timeout = timeout

    def _headers(self, include_cookie: bool = False) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        }
        if include_cookie and self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            import httpx
        except Exception as exc:  # pragma: no cover
            raise MathemError("httpx is required. Run: uv sync") from exc

        full_url = urljoin(BASE_URL, url)
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                with httpx.Client(follow_redirects=True, timeout=self.timeout) as client:
                    response = client.request(method, full_url, **kwargs)
                if response.status_code in (429, 500, 502, 503, 504):
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            sleep_s = min(float(retry_after), 30.0)
                        except ValueError:
                            sleep_s = 2.0**attempt
                    else:
                        sleep_s = min(2.0**attempt, 10.0)
                    time.sleep(sleep_s)
                    continue
                response.raise_for_status()
                return response
            except Exception as exc:  # pragma: no cover
                last_exc = exc
                if attempt < 3:
                    time.sleep(min(2.0**attempt, 10.0))
                    continue
        raise MathemError(f"Mathem request failed: {last_exc}")

    def get_html(self, path_or_url: str, params: dict[str, Any] | None = None) -> str:
        response = self._request("GET", path_or_url, params=params, headers=self._headers())
        return response.text

    def search_products(self, query: str, limit: int = 20) -> list[MathemProduct]:
        html_text = self.get_html("/se/search/products/", params={"q": query})
        products = products_from_html(html_text, limit=limit)
        query_terms = [term for term in re.split(r"\W+", query.lower()) if len(term) >= 3]
        if query_terms:
            products.sort(
                key=lambda product: sum(term in product.display_name.lower() for term in query_terms),
                reverse=True,
            )
        return products[:limit]

    def list_prismatch_products(self, limit: int = 100) -> list[MathemProduct]:
        html_text = self.get_html("/se/categories/911-prismatch/")
        return products_from_html(html_text, limit=limit)

    def list_prismatch_recipes(self, limit: int = 100) -> list[dict[str, str]]:
        html_text = self.get_html("/se/about/prismatch/")
        recipes = recipes_from_html(html_text, limit=limit)
        if recipes:
            return recipes

        next_data = extract_next_data(html_text)
        strings = _string_values(next_data, max_values=2000)
        out: list[dict[str, str]] = []
        seen: set[str] = set()
        for value in strings:
            if 5 <= len(value) <= 90 and not value.startswith("http"):
                title = value.strip()
                lowered = title.lower()
                recipe_terms = ["med", "pasta", "gryta", "kyckling", "torsk", "lax", "biff", "stroganoff"]
                if any(term in lowered for term in recipe_terms) and title not in seen:
                    seen.add(title)
                    out.append({"title": title, "url": ""})
                if len(out) >= limit:
                    break
        return out

    def add_to_cart(self, product_id: int | str, quantity: int = 1) -> dict[str, Any]:
        if not self.cookie:
            raise MathemAuthError(
                "Missing Mathem session cookie. Set MATHEM_COOKIE in .env or create cookie.txt."
            )
        payload = {"items": [{"product_id": int(product_id), "quantity": int(quantity)}]}
        headers = self._headers(include_cookie=True)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json, text/plain, */*"
        response = self._request(
            "POST",
            "/tienda-web-api/v1/cart/items/?group_by=recipes",
            json=payload,
            headers=headers,
        )
        try:
            body = response.json() if response.content else {}
        except Exception:
            body = {"text": response.text[:1000]}
        return {
            "success": True,
            "status_code": response.status_code,
            "product_id": product_id,
            "quantity": quantity,
            "response": body,
        }

    def add_many_to_cart(self, items: Iterable[tuple[int | str, int]]) -> list[dict[str, Any]]:
        results = []
        for product_id, quantity in items:
            results.append(self.add_to_cart(product_id, quantity))
        return results


def format_product(product: MathemProduct) -> str:
    price = "?"
    if product.price is not None:
        price = f"{product.price:.2f} {product.currency}".replace(".", ",")
    unit = ""
    if product.unit_price is not None:
        suffix = f"/{product.unit_price_unit}" if product.unit_price_unit else ""
        unit = f" ({product.unit_price:.2f} kr{suffix})".replace(".", ",")
    badges = []
    if product.is_prismatch:
        badges.append("Prismatch")
    if product.is_offer:
        badges.append("Kampanj")
    badge_text = f" [{' · '.join(badges)}]" if badges else ""
    return f"{product.id}: {product.display_name} — {price}{unit}{badge_text}"
