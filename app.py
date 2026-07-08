from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from mathem_agent.mathem import MathemAuthError, MathemClient
from mathem_agent.planner import generate_meal_plan, save_plan

st.set_page_config(page_title="Mathem Agent", page_icon="🛒", layout="wide")

st.title("Mathem Agent")
st.caption("Personlig prototyp: Mathem-priser → meny → varukorg.")

with st.sidebar:
    st.header("Plan")
    people = st.number_input("Personer", min_value=1, max_value=8, value=2, step=1)
    meals = st.number_input("Middagar", min_value=1, max_value=7, value=4, step=1)
    budget = st.number_input("Maxbudget, kr", min_value=0, max_value=5000, value=850, step=50)
    preferences = st.text_area(
        "Preferenser",
        value="snabbt, billigt, mycket protein, inte för starkt",
        height=90,
    )
    avoid_raw = st.text_input("Undvik, kommaseparerat", value="")
    seed = st.number_input("Seed", min_value=0, max_value=9999, value=7, step=1)
    generate = st.button("Generera Mathem-plan", type="primary")

if generate:
    avoid = [part.strip() for part in avoid_raw.split(",") if part.strip()]
    with st.spinner("Hämtar Mathem-produkter och optimerar plan..."):
        st.session_state["plan"] = generate_meal_plan(
            people=int(people),
            meals=int(meals),
            preferences=preferences,
            avoid=avoid,
            max_budget=float(budget) if budget else None,
            seed=int(seed),
        )

plan = st.session_state.get("plan")

if not plan:
    st.info("Generera en plan i sidopanelen.")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Middagar", len(plan.meals))
col2.metric("Estimerad korg", f"{plan.estimated_cart_total:.0f} kr")
col3.metric("Personer", plan.people)

if plan.warnings:
    for warning in plan.warnings:
        st.warning(warning)

st.subheader("Meny")
for i, meal in enumerate(plan.meals, start=1):
    with st.expander(f"{i}. {meal.title} — {meal.estimated_minutes} min — ca {meal.estimated_cost:.0f} kr", expanded=True):
        st.write("Ingredienser")
        for ingredient in meal.ingredients:
            product = ingredient.product
            badges = []
            if product.is_prismatch:
                badges.append("Prismatch")
            if product.is_offer:
                badges.append("Kampanj")
            badge_text = f" — {' · '.join(badges)}" if badges else ""
            st.write(
                f"- {ingredient.quantity} × {product.display_name} "
                f"({product.price or 0:.0f} kr){badge_text}"
            )
        st.write("Steg")
        for step in meal.steps:
            st.write(f"- {step}")

st.subheader("Aggregerad varukorg")
cart_rows = []
for line in plan.cart_lines:
    cart_rows.append(
        {
            "qty": line.quantity,
            "product_id": line.product.id,
            "product": line.product.display_name,
            "price": line.product.price,
            "estimated_cost": line.estimated_cost,
            "signals": ", ".join(
                signal
                for signal, enabled in {
                    "Prismatch": line.product.is_prismatch,
                    "Kampanj": line.product.is_offer,
                }.items()
                if enabled
            ),
            "used_in": ", ".join(line.used_in),
        }
    )
st.dataframe(cart_rows, use_container_width=True)

left, right = st.columns(2)
with left:
    if st.button("Spara plan.json"):
        save_plan(plan, Path("plan.json"))
        st.success("Sparade plan.json")
with right:
    st.link_button("Öppna Mathem-varukorg", "https://www.mathem.se/se/cart/")

st.divider()
st.subheader("Lägg i Mathem-varukorg")
st.write("Detta använder din lokala Mathem-cookie från `.env` eller `cookie.txt`.")
confirm_text = st.text_input("Skriv ADD för att bekräfta", value="")
if st.button("Lägg alla produkter i varukorgen", disabled=confirm_text != "ADD"):
    client = MathemClient()
    try:
        with st.spinner("Lägger produkter i Mathem-varukorgen..."):
            results = client.add_many_to_cart((line.product.id, line.quantity) for line in plan.cart_lines)
        st.success("Klart. Kontrollera Mathem-varukorgen innan checkout.")
        st.code(json.dumps(results, ensure_ascii=False, indent=2), language="json")
    except MathemAuthError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Kunde inte lägga i varukorgen: {exc}")

with st.expander("Debug: plan JSON"):
    st.code(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), language="json")
