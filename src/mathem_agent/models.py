from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class MathemProduct:
    id: int | str
    name: str
    brand: str = ""
    description: str = ""
    price: float | None = None
    currency: str = "SEK"
    unit_price: float | None = None
    unit_price_unit: str = ""
    labels: list[str] = field(default_factory=list)
    promotions: list[str] = field(default_factory=list)
    url: str = ""
    raw_text: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def display_name(self) -> str:
        parts = [self.name]
        if self.description:
            parts.append(self.description)
        if self.brand:
            parts.append(self.brand)
        return ", ".join(part for part in parts if part)

    @property
    def is_prismatch(self) -> bool:
        text = " ".join([self.name, self.description, self.brand, *self.labels, *self.promotions, self.raw_text])
        return "prismatch" in text.lower()

    @property
    def is_offer(self) -> bool:
        text = " ".join([*self.promotions, *self.labels, self.raw_text]).lower()
        offer_terms = ["extrapris", "erbjud", "rabatt", "kampanj", "välj & blanda", "köp fler"]
        return any(term in text for term in offer_terms) or bool(self.promotions)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("raw", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MathemProduct":
        return cls(**{key: value for key, value in data.items() if key in cls.__dataclass_fields__})


@dataclass(slots=True)
class RecipeIngredient:
    slot: str
    query: str
    product: MathemProduct
    quantity: int = 1
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "query": self.query,
            "product": self.product.to_dict(),
            "quantity": self.quantity,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecipeIngredient":
        return cls(
            slot=data["slot"],
            query=data["query"],
            product=MathemProduct.from_dict(data["product"]),
            quantity=int(data.get("quantity", 1)),
            reason=data.get("reason", ""),
        )


@dataclass(slots=True)
class PlannedRecipe:
    title: str
    servings: int
    estimated_minutes: int
    ingredients: list[RecipeIngredient]
    steps: list[str]
    tags: list[str] = field(default_factory=list)

    @property
    def estimated_cost(self) -> float:
        return sum(
            (ingredient.product.price or 0.0) * ingredient.quantity for ingredient in self.ingredients
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "servings": self.servings,
            "estimated_minutes": self.estimated_minutes,
            "ingredients": [ingredient.to_dict() for ingredient in self.ingredients],
            "steps": self.steps,
            "tags": self.tags,
            "estimated_cost": round(self.estimated_cost, 2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlannedRecipe":
        return cls(
            title=data["title"],
            servings=int(data["servings"]),
            estimated_minutes=int(data.get("estimated_minutes", 30)),
            ingredients=[RecipeIngredient.from_dict(item) for item in data.get("ingredients", [])],
            steps=list(data.get("steps", [])),
            tags=list(data.get("tags", [])),
        )


@dataclass(slots=True)
class CartLine:
    product: MathemProduct
    quantity: int
    used_in: list[str] = field(default_factory=list)

    @property
    def estimated_cost(self) -> float:
        return (self.product.price or 0.0) * self.quantity

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product.to_dict(),
            "quantity": self.quantity,
            "used_in": self.used_in,
            "estimated_cost": round(self.estimated_cost, 2),
        }


@dataclass(slots=True)
class MealPlan:
    people: int
    meals: list[PlannedRecipe]
    preferences: str = ""
    avoid: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def cart_lines(self) -> list[CartLine]:
        by_id: dict[str, CartLine] = {}
        for meal in self.meals:
            for ingredient in meal.ingredients:
                product_id = str(ingredient.product.id)
                if product_id not in by_id:
                    by_id[product_id] = CartLine(
                        product=ingredient.product,
                        quantity=0,
                        used_in=[],
                    )
                by_id[product_id].quantity += ingredient.quantity
                if meal.title not in by_id[product_id].used_in:
                    by_id[product_id].used_in.append(meal.title)
        return list(by_id.values())

    @property
    def estimated_cart_total(self) -> float:
        return sum(line.estimated_cost for line in self.cart_lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "people": self.people,
            "preferences": self.preferences,
            "avoid": self.avoid,
            "warnings": self.warnings,
            "estimated_cart_total": round(self.estimated_cart_total, 2),
            "meals": [meal.to_dict() for meal in self.meals],
            "cart_lines": [line.to_dict() for line in self.cart_lines],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MealPlan":
        return cls(
            people=int(data.get("people", 2)),
            preferences=data.get("preferences", ""),
            avoid=list(data.get("avoid", [])),
            warnings=list(data.get("warnings", [])),
            meals=[PlannedRecipe.from_dict(item) for item in data.get("meals", [])],
        )
