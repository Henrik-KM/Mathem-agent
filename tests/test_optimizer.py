from mathem_agent.models import MathemProduct
from mathem_agent.optimizer import PreferenceProfile, choose_best_product, score_product
from mathem_agent.planner import demo_plan


def test_prismatch_scores_higher_than_plain_expensive_product():
    profile = PreferenceProfile.parse("billigt")
    cheap = MathemProduct(id=1, name="Kikärtor", price=15, labels=["Prismatch"])
    expensive = MathemProduct(id=2, name="Kikärtor premium", price=45)
    assert score_product(cheap, "kikärtor", profile) > score_product(expensive, "kikärtor", profile)


def test_avoid_terms_filter_product():
    profile = PreferenceProfile.parse("", avoid=["svamp"])
    mushroom = MathemProduct(id=1, name="Champinjoner", description="svamp", price=10)
    tomato = MathemProduct(id=2, name="Tomat", price=12)
    assert choose_best_product([mushroom, tomato], "grönt", profile).id == 2


def test_demo_plan_has_cart_total():
    plan = demo_plan()
    assert plan.estimated_cart_total > 0
    assert len(plan.cart_lines) == 4
