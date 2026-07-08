from __future__ import annotations

import json
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .mathem import MathemAuthError, MathemClient, format_product
from .models import MealPlan
from .planner import demo_plan, generate_meal_plan, load_plan, save_plan

console = Console()
app = typer.Typer(help="Personal Mathem meal planner and basket builder.")
cart_app = typer.Typer(help="Cart operations.")
app.add_typer(cart_app, name="cart")


def _print_products(products) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", overflow="fold")
    table.add_column("Produkt")
    table.add_column("Pris", justify="right")
    table.add_column("Jämförpris", justify="right")
    table.add_column("Signal")
    for product in products:
        price = "" if product.price is None else f"{product.price:.2f} kr".replace(".", ",")
        unit = ""
        if product.unit_price is not None:
            unit = f"{product.unit_price:.2f} kr/{product.unit_price_unit}".replace(".", ",")
        signals = []
        if product.is_prismatch:
            signals.append("Prismatch")
        if product.is_offer:
            signals.append("Kampanj")
        table.add_row(str(product.id), product.display_name, price, unit, ", ".join(signals))
    console.print(table)


def _print_plan(plan: MealPlan) -> None:
    console.print(f"\n[bold]Plan för {plan.people} personer[/bold]")
    console.print(f"Estimerad Mathem-korg: [bold]{plan.estimated_cart_total:.0f} kr[/bold]\n")
    for idx, meal in enumerate(plan.meals, start=1):
        console.print(f"[bold]{idx}. {meal.title}[/bold]  ({meal.estimated_minutes} min, ca {meal.estimated_cost:.0f} kr)")
        for ingredient in meal.ingredients:
            product = ingredient.product
            signals = []
            if product.is_prismatch:
                signals.append("Prismatch")
            if product.is_offer:
                signals.append("Kampanj")
            signal_text = f" [{' · '.join(signals)}]" if signals else ""
            price = "?" if product.price is None else f"{product.price:.0f} kr"
            console.print(
                f"  - {ingredient.quantity} x {product.display_name} ({price}){signal_text}"
            )
        console.print("  Steg:")
        for step in meal.steps:
            console.print(f"    • {step}")
        console.print()
    if plan.warnings:
        console.print("[yellow]Varningar[/yellow]")
        for warning in plan.warnings:
            console.print(f"- {warning}")

    console.print("[bold]Aggregerad varukorg[/bold]")
    for line in plan.cart_lines:
        console.print(
            f"- {line.quantity} x {line.product.display_name} "
            f"({line.estimated_cost:.0f} kr) — används i: {', '.join(line.used_in)}"
        )


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Product query, e.g. 'kyckling' or 'pasta prismatch'.")],
    limit: Annotated[int, typer.Option("--limit", "-n")] = 10,
) -> None:
    """Search Mathem products."""
    client = MathemClient()
    products = client.search_products(query, limit=limit)
    if not products:
        console.print("No products found.")
        raise typer.Exit(1)
    _print_products(products)


@app.command()
def prismatch(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 30,
) -> None:
    """List Mathem prismatch products."""
    client = MathemClient()
    products = client.list_prismatch_products(limit=limit)
    _print_products(products)


@app.command("prismatch-recipes")
def prismatch_recipes(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 40,
) -> None:
    """List Mathem's public prismatch recipe links/titles."""
    client = MathemClient()
    recipes = client.list_prismatch_recipes(limit=limit)
    if not recipes:
        console.print("No recipes found.")
        raise typer.Exit(1)
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Recept")
    table.add_column("URL")
    for idx, recipe in enumerate(recipes, start=1):
        table.add_row(str(idx), recipe.get("title", ""), recipe.get("url", ""))
    console.print(table)


@app.command()
def plan(
    people: Annotated[int, typer.Option("--people", "-p")] = 2,
    meals: Annotated[int, typer.Option("--meals", "-m")] = 4,
    max_budget: Annotated[float | None, typer.Option("--max-budget", "-b")] = None,
    preferences: Annotated[str, typer.Option("--preferences", "-pref")] = "snabbt, billigt, vardag",
    avoid: Annotated[list[str], typer.Option("--avoid", "-a")] = [],
    save: Annotated[Path | None, typer.Option("--save", "-s")] = None,
    seed: Annotated[int, typer.Option("--seed")] = 7,
) -> None:
    """Generate a value-optimized Mathem meal plan."""
    meal_plan = generate_meal_plan(
        people=people,
        meals=meals,
        preferences=preferences,
        avoid=list(avoid),
        max_budget=max_budget,
        seed=seed,
    )
    _print_plan(meal_plan)
    if save:
        save_plan(meal_plan, save)
        console.print(f"\nSaved plan to [bold]{save}[/bold]")


@app.command()
def demo(
    save: Annotated[Path | None, typer.Option("--save", "-s")] = None,
) -> None:
    """Show an offline demo plan without contacting Mathem."""
    meal_plan = demo_plan()
    _print_plan(meal_plan)
    if save:
        save_plan(meal_plan, save)
        console.print(f"\nSaved demo plan to [bold]{save}[/bold]")


@cart_app.command("add")
def cart_add(
    plan_file: Annotated[Path, typer.Argument(help="Path to a plan JSON created by 'mathem-agent plan'.")],
    confirm: Annotated[bool, typer.Option("--confirm", help="Actually add items to Mathem cart.")] = False,
) -> None:
    """Add all products in a saved plan to your Mathem cart."""
    meal_plan = load_plan(plan_file)
    console.print(f"Plan total: [bold]{meal_plan.estimated_cart_total:.0f} kr[/bold]")
    for line in meal_plan.cart_lines:
        console.print(f"- {line.quantity} x {format_product(line.product)}")

    if not confirm:
        console.print("\nDry run only. Re-run with --confirm to add these products to the Mathem cart.")
        return

    client = MathemClient()
    try:
        results = client.add_many_to_cart((line.product.id, line.quantity) for line in meal_plan.cart_lines)
    except MathemAuthError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    console.print("\nCart results:")
    console.print(json.dumps(results, ensure_ascii=False, indent=2))


@cart_app.command("open")
def cart_open() -> None:
    """Open Mathem cart/checkout in the browser."""
    url = "https://www.mathem.se/se/cart/"
    console.print(url)
    try:
        webbrowser.open(url)
    except Exception:
        if sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", url], check=False)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
