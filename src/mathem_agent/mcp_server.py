from __future__ import annotations

from typing import Any

from .mathem import MathemClient
from .planner import generate_meal_plan


def _make_server() -> Any:
    try:
        from fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("fastmcp is required. Run: uv sync") from exc

    mcp = FastMCP("Mathem Agent")

    @mcp.tool
    def search_products(query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search Mathem products by query."""
        client = MathemClient()
        return [product.to_dict() for product in client.search_products(query, limit=limit)]

    @mcp.tool
    def list_prismatch_products(limit: int = 30) -> list[dict[str, Any]]:
        """List products from Mathem's public prismatch category."""
        client = MathemClient()
        return [product.to_dict() for product in client.list_prismatch_products(limit=limit)]

    @mcp.tool
    def list_prismatch_recipes(limit: int = 30) -> list[dict[str, str]]:
        """List recipe titles/links from Mathem's public prismatch page."""
        client = MathemClient()
        return client.list_prismatch_recipes(limit=limit)

    @mcp.tool
    def generate_meal_plan_tool(
        people: int = 2,
        meals: int = 4,
        preferences: str = "snabbt, billigt, vardag",
        avoid_csv: str = "",
        max_budget: float | None = None,
    ) -> dict[str, Any]:
        """Generate a Mathem product-backed meal plan."""
        avoid = [part.strip() for part in avoid_csv.split(",") if part.strip()]
        plan = generate_meal_plan(
            people=people,
            meals=meals,
            preferences=preferences,
            avoid=avoid,
            max_budget=max_budget,
        )
        return plan.to_dict()

    @mcp.tool
    def add_plan_to_cart(plan: dict[str, Any]) -> list[dict[str, Any]]:
        """Add a generated plan dict to the current Mathem basket using local session cookie."""
        from .models import MealPlan

        meal_plan = MealPlan.from_dict(plan)
        client = MathemClient()
        return client.add_many_to_cart((line.product.id, line.quantity) for line in meal_plan.cart_lines)

    return mcp


def main() -> None:
    _make_server().run()


if __name__ == "__main__":
    main()
