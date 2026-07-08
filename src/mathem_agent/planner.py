from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .mathem import MathemClient
from .models import MealPlan, PlannedRecipe, RecipeIngredient
from .optimizer import PreferenceProfile, choose_best_product


@dataclass(frozen=True, slots=True)
class IngredientSlot:
    name: str
    queries: tuple[str, ...]
    reason: str
    optional: bool = False


@dataclass(frozen=True, slots=True)
class RecipeTemplate:
    key: str
    title: str
    minutes: int
    slots: tuple[IngredientSlot, ...]
    tags: tuple[str, ...] = ()


BASE_TEMPLATES: tuple[RecipeTemplate, ...] = (
    RecipeTemplate(
        key="pasta",
        title="Värdepasta med {protein} och {veg}",
        minutes=25,
        tags=("snabb", "vardag"),
        slots=(
            IngredientSlot("carb", ("pasta prismatch", "pasta"), "billig bas som ofta räcker till flera portioner"),
            IngredientSlot("protein", ("kyckling prismatch", "bacon prismatch", "kikärtor prismatch"), "protein med bra pris"),
            IngredientSlot("veg", ("paprika prismatch", "tomat prismatch", "spenat fryst"), "grönt med bra jämförpris"),
            IngredientSlot("sauce", ("grädde prismatch", "crème fraiche", "krossade tomater"), "binder ihop rätten"),
        ),
    ),
    RecipeTemplate(
        key="taco",
        title="Prismatch-tacos med {protein} och {veg}",
        minutes=25,
        tags=("snabb", "familj"),
        slots=(
            IngredientSlot("carb", ("tortillas prismatch", "tortillabröd"), "bas till tacos"),
            IngredientSlot("protein", ("nötfärs prismatch", "kycklingfärs", "sojafärs"), "huvudprotein"),
            IngredientSlot("veg", ("tomat", "gurka", "paprika prismatch"), "fräsch fyllning"),
            IngredientSlot("sauce", ("tacosås", "salsa", "gräddfil"), "sås och smak"),
        ),
    ),
    RecipeTemplate(
        key="curry",
        title="Kokosgryta med {protein} och {veg}",
        minutes=30,
        tags=("matlåda", "värmande"),
        slots=(
            IngredientSlot("carb", ("ris", "jasminris", "nudlar"), "mättande bas"),
            IngredientSlot("protein", ("kyckling prismatch", "tofu", "kikärtor prismatch"), "protein som fungerar i gryta"),
            IngredientSlot("veg", ("wokgrönsaker fryst", "paprika prismatch", "broccoli fryst"), "grönsaker med låg svinnrisk"),
            IngredientSlot("sauce", ("kokosmjölk prismatch", "curry paste", "krossade tomater"), "såsbas"),
        ),
    ),
    RecipeTemplate(
        key="bowl",
        title="Budgetbowl med {protein}, {veg} och {carb}",
        minutes=30,
        tags=("matlåda", "flexibel"),
        slots=(
            IngredientSlot("carb", ("ris", "bulgur", "potatis prismatch"), "billig bas"),
            IngredientSlot("protein", ("ägg prismatch", "tonfisk prismatch", "kikärtor prismatch"), "billigt protein"),
            IngredientSlot("veg", ("morötter", "avokado prismatch", "vitkål"), "grönt och crunch"),
            IngredientSlot("sauce", ("yoghurt naturell", "sweet chili", "majonnäs"), "enkel dressing"),
        ),
    ),
    RecipeTemplate(
        key="fish",
        title="Fiskmiddag med {protein}, {carb} och {veg}",
        minutes=30,
        tags=("fisk", "snabb"),
        slots=(
            IngredientSlot("protein", ("torsk prismatch", "lax prismatch", "fisk fryst prismatch"), "prismatchad fisk"),
            IngredientSlot("carb", ("potatis prismatch", "ris", "pasta"), "billigt tillbehör"),
            IngredientSlot("veg", ("spenat fryst", "ärtor frysta", "broccoli fryst"), "grönt med låg svinnrisk"),
            IngredientSlot("sauce", ("grädde prismatch", "citron", "smör"), "snabb sås"),
        ),
    ),
    RecipeTemplate(
        key="stroganoff",
        title="Snabb stroganoff med {protein} och {carb}",
        minutes=20,
        tags=("snabb", "billig"),
        slots=(
            IngredientSlot("protein", ("falukorv prismatch", "kycklingkorv", "sojakorv"), "billigt huvudprotein"),
            IngredientSlot("carb", ("ris", "pasta", "potatis"), "mättande bas"),
            IngredientSlot("sauce", ("krossade tomater", "tomatpuré", "grädde prismatch"), "stroganoffbas"),
            IngredientSlot("veg", ("morötter", "paprika prismatch", "gurka"), "enkelt tillbehör"),
        ),
    ),
)

VEGETARIAN_OVERRIDES = {
    "protein": ("tofu", "halloumi", "kikärtor prismatch", "bönor", "linser", "sojafärs"),
}

VEGAN_OVERRIDES = {
    "protein": ("tofu", "kikärtor prismatch", "bönor", "linser", "sojafärs"),
    "sauce": ("kokosmjölk prismatch", "krossade tomater", "havregrädde"),
}


def _slot_queries(slot: IngredientSlot, profile: PreferenceProfile) -> tuple[str, ...]:
    if profile.vegan and slot.name in VEGAN_OVERRIDES:
        return VEGAN_OVERRIDES[slot.name]
    if profile.vegetarian and slot.name in VEGETARIAN_OVERRIDES:
        return VEGETARIAN_OVERRIDES[slot.name]
    return slot.queries


def _render_title(template: RecipeTemplate, ingredients: list[RecipeIngredient]) -> str:
    by_slot = {ingredient.slot: ingredient.product.name for ingredient in ingredients}
    title = template.title
    for slot, value in by_slot.items():
        simple = value.split(",")[0].split("  ")[0]
        title = title.replace("{" + slot + "}", simple.lower())
    return title


def _steps(template: RecipeTemplate, ingredients: list[RecipeIngredient], people: int) -> list[str]:
    names = {ingredient.slot: ingredient.product.name for ingredient in ingredients}
    carb = names.get("carb", "basen")
    protein = names.get("protein", "proteinet")
    veg = names.get("veg", "grönsakerna")
    sauce = names.get("sauce", "såsen")

    if template.key == "pasta":
        return [
            f"Koka {carb} enligt förpackningen.",
            f"Stek {protein} tills den fått färg. Lägg i {veg} mot slutet.",
            f"Rör ned {sauce}, späd med lite pastavatten och vänd ihop med pastan.",
            f"Smaka av med salt, peppar och eventuell ost/krydda du redan har hemma. Servera {people} portioner.",
        ]
    if template.key == "taco":
        return [
            f"Stek {protein} med tacokrydda eller kryddor du har hemma.",
            f"Skär {veg} och värm {carb}.",
            f"Servera med {sauce}. Bygg tacos direkt vid bordet.",
        ]
    if template.key == "curry":
        return [
            f"Koka {carb}.",
            f"Stek {protein} och {veg} i en stor panna.",
            f"Häll på {sauce} och låt sjuda 8–10 minuter.",
            "Smaka av med soja, lime, curry eller chili efter vad du har hemma.",
        ]
    if template.key == "fish":
        return [
            f"Tillaga {carb}. Koka eller rosta beroende på produkt.",
            f"Stek eller ugnsbaka {protein} varsamt.",
            f"Värm {veg} och gör en snabb sås med {sauce}.",
            "Servera direkt. Lägg eventuell restfisk i matlåda först när den svalnat.",
        ]
    if template.key == "stroganoff":
        return [
            f"Koka {carb}.",
            f"Skiva och stek {protein}. Lägg i {veg} om den passar att steka.",
            f"Rör ned {sauce} och låt sjuda kort.",
            "Smaka av med senap, paprika, salt och peppar om du har hemma.",
        ]
    return [
        f"Tillaga {carb}.",
        f"Tillaga {protein} och {veg}.",
        f"Toppa med {sauce} och justera smaken med sådant du redan har hemma.",
    ]


def generate_meal_plan(
    people: int = 2,
    meals: int = 4,
    preferences: str = "",
    avoid: list[str] | None = None,
    max_budget: float | None = None,
    client: MathemClient | None = None,
    seed: int = 7,
) -> MealPlan:
    client = client or MathemClient()
    profile = PreferenceProfile.parse(preferences, avoid=avoid)
    rng = random.Random(seed)

    templates = list(BASE_TEMPLATES)
    if profile.fast:
        templates.sort(key=lambda template: template.minutes)
    else:
        rng.shuffle(templates)

    if profile.vegetarian or profile.vegan:
        templates = [template for template in templates if template.key not in {"fish"}]

    selected_templates = templates[: max(1, meals)]
    warnings: list[str] = []
    planned: list[PlannedRecipe] = []
    seen_products: set[str] = set()

    for template in selected_templates:
        ingredients: list[RecipeIngredient] = []
        for slot in template.slots:
            selected_product = None
            selected_query = ""
            for query in _slot_queries(slot, profile):
                candidates = client.search_products(query, limit=12)
                product = choose_best_product(candidates, query=query, profile=profile, exclude_ids=seen_products)
                if product:
                    selected_product = product
                    selected_query = query
                    break
            if not selected_product:
                if slot.optional:
                    continue
                warnings.append(f"Hittade ingen bra produkt för '{slot.name}' i {template.title}.")
                continue
            seen_products.add(str(selected_product.id))
            quantity = 1
            if people >= 4 and selected_product.price is not None and selected_product.price < 60:
                quantity = 2
            ingredients.append(
                RecipeIngredient(
                    slot=slot.name,
                    query=selected_query,
                    product=selected_product,
                    quantity=quantity,
                    reason=slot.reason,
                )
            )

        if not ingredients:
            continue
        title = _render_title(template, ingredients)
        planned.append(
            PlannedRecipe(
                title=title,
                servings=people,
                estimated_minutes=template.minutes,
                ingredients=ingredients,
                steps=_steps(template, ingredients, people),
                tags=list(template.tags),
            )
        )

    plan = MealPlan(
        people=people,
        meals=planned,
        preferences=preferences,
        avoid=list(avoid or []),
        warnings=warnings,
    )
    if max_budget is not None and plan.estimated_cart_total > max_budget:
        plan.warnings.append(
            f"Planen är cirka {plan.estimated_cart_total:.0f} kr, vilket är över budget {max_budget:.0f} kr. "
            "Kör igen med färre måltider eller striktare budgetpreferens."
        )
    return plan


def save_plan(plan: MealPlan, path: str | Path) -> None:
    Path(path).write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_plan(path: str | Path) -> MealPlan:
    data: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    return MealPlan.from_dict(data)


def demo_plan() -> MealPlan:
    """Offline demo used for tests/docs; does not contact Mathem."""
    from .models import MathemProduct

    products = [
        MathemProduct(id=1, name="Pasta Girandole", brand="Barilla", price=16.0, labels=["Prismatch"]),
        MathemProduct(id=2, name="Kikärtor", brand="Zeta", price=15.09, labels=["Prismatch"]),
        MathemProduct(id=3, name="Paprikamix Klass1", price=27.0, promotions=["Extrapris"]),
        MathemProduct(id=4, name="Kokosmjölk 18%", brand="Garant", price=11.95, labels=["Prismatch"]),
    ]
    recipe = PlannedRecipe(
        title="Demo: värdepasta med kikärtor och paprika",
        servings=2,
        estimated_minutes=25,
        ingredients=[
            RecipeIngredient("carb", "pasta", products[0], reason="billig bas"),
            RecipeIngredient("protein", "kikärtor", products[1], reason="billigt protein"),
            RecipeIngredient("veg", "paprika", products[2], reason="kampanjvara"),
            RecipeIngredient("sauce", "kokosmjölk", products[3], reason="billig sås"),
        ],
        steps=["Koka pasta.", "Stek paprika och kikärtor.", "Rör ned kokosmjölk och servera."],
    )
    return MealPlan(people=2, meals=[recipe], preferences="demo")
