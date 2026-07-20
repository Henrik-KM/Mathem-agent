from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .browser_auth import (
    BrowserAuthError,
    CART_URL,
    get_auth_status,
    open_authenticated_browser,
    refresh_session,
    setup_account,
)
from .mathem import MathemAuthError, MathemClient, format_product
from .models import MealPlan
from .planner import demo_plan, generate_meal_plan, load_plan, save_plan

console = Console()
app = typer.Typer(help="Personal Mathem meal planner and basket builder.")
auth_app = typer.Typer(help="Mathem account and local session setup.")
cart_app = typer.Typer(help="Cart operations.")
app.add_typer(auth_app, name="auth")
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
        console.print(
            f"[bold]{idx}. {meal.title}[/bold]  "
            f"({meal.estimated_minutes} min, ca {meal.estimated_cost:.0f} kr)"
        )
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


def _run_setup(existing_account: bool, install_browser: bool) -> None:
    try:
        result = setup_account(
            existing_account=existing_account,
            install_browser=install_browser,
        )
    except BrowserAuthError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    if result.likely_logged_in:
        console.print("\n[green]Mathem-sessionen är sparad.[/green]")
    else:
        console.print(
            "\n[yellow]Sessionen sparades, men webbadressen såg fortfarande ut som "
            "registrering/inloggning. Kör setup igen om cart-anropet nekas.[/yellow]"
        )
    console.print(f"Cookies: {result.cookie_count}")
    console.print(f"Lokal sessionsfil: {result.cookie_file}")
    console.print("Lösenord och betalningsuppgifter har inte lagrats av Mathem Agent.")


@app.command("setup")
def setup(
    existing_account: Annotated[
        bool,
        typer.Option(
            "--existing-account",
            help="Open login instead of creating a new account.",
        ),
    ] = False,
    skip_browser_install: Annotated[
        bool,
        typer.Option(
            "--skip-browser-install",
            help="Skip automatic Chromium installation.",
        ),
    ] = False,
) -> None:
    """Create/login to Mathem in a local browser and save the session automatically."""
    _run_setup(existing_account=existing_account, install_browser=not skip_browser_install)


@auth_app.command("setup")
def auth_setup(
    existing_account: Annotated[
        bool,
        typer.Option("--existing-account", help="Open login instead of signup."),
    ] = False,
    skip_browser_install: Annotated[
        bool,
        typer.Option("--skip-browser-install"),
    ] = False,
) -> None:
    """Alias for the top-level setup command."""
    _run_setup(existing_account=existing_account, install_browser=not skip_browser_install)


@auth_app.command("status")
def auth_status() -> None:
    """Show whether a local Mathem browser session has been configured."""
    status = get_auth_status()
    table = Table(show_header=False)
    table.add_row("Konfigurerad", "ja" if status.configured else "nej")
    table.add_row("Webbläsarprofil", "finns" if status.profile_exists else "saknas")
    table.add_row("Sessionsfil", "finns" if status.cookie_file_exists else "saknas")
    table.add_row("Mathem-cookies", str(status.cookie_count))
    table.add_row("Senast exporterad", status.updated_at or "okänt")
    table.add_row("Lokal katalog", status.data_dir)
    console.print(table)
    if not status.configured:
        console.print("\nKör [bold]uv run mathem-agent setup[/bold].")


@auth_app.command("refresh")
def auth_refresh(
    visible: Annotated[
        bool,
        typer.Option("--visible", help="Show the browser while refreshing."),
    ] = False,
) -> None:
    """Refresh API cookies from the saved browser profile."""
    try:
        result = refresh_session(headless=not visible)
    except BrowserAuthError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]Sessionen uppdaterades.[/green] {result.cookie_count} Mathem-cookies sparades."
    )


@app.command()
def search(
    query: Annotated[
        str,
        typer.Argument(help="Product query, e.g. 'kyckling' or 'pasta prismatch'."),
    ],
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
    preferences: Annotated[
        str,
        typer.Option("--preferences", "--pref"),
    ] = "snabbt, billigt, vardag",
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
    plan_file: Annotated[
        Path,
        typer.Argument(help="Path to a plan JSON created by 'mathem-agent plan'."),
    ],
    confirm: Annotated[
        bool,
        typer.Option("--confirm", help="Actually add items to Mathem cart."),
    ] = False,
) -> None:
    """Add all products in a saved plan to your Mathem cart."""
    meal_plan = load_plan(plan_file)
    console.print(f"Plan total: [bold]{meal_plan.estimated_cart_total:.0f} kr[/bold]")
    for line in meal_plan.cart_lines:
        console.print(f"- {line.quantity} x {format_product(line.product)}")

    if not confirm:
        console.print(
            "\nDry run only. Re-run with --confirm to add these products to the Mathem cart."
        )
        return

    client = MathemClient()
    try:
        results = client.add_many_to_cart(
            (line.product.id, line.quantity) for line in meal_plan.cart_lines
        )
    except MathemAuthError as exc:
        console.print(f"[red]{exc}[/red]")
        console.print("Skapa kontot och sessionen med: [bold]uv run mathem-agent setup[/bold]")
        raise typer.Exit(2) from exc

    console.print("\nCart results:")
    console.print(json.dumps(results, ensure_ascii=False, indent=2))
    console.print(
        "\nÖppna den inloggade kassan med: [bold]uv run mathem-agent checkout[/bold]"
    )


def _open_checkout() -> None:
    try:
        open_authenticated_browser(CART_URL)
    except BrowserAuthError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        console.print("Öppnar Mathem i din vanliga webbläsare i stället.")
        webbrowser.open(CART_URL)


@cart_app.command("open")
def cart_open() -> None:
    """Open the Mathem cart in the saved authenticated browser profile."""
    _open_checkout()


@app.command()
def checkout() -> None:
    """Open the saved authenticated Mathem cart for delivery and payment confirmation."""
    _open_checkout()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
