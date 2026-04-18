from snaptrash_common.schemas import FoodItem
from snaptrash_ingestion.services.food_analysis import enrich


def test_enrich_leafy_greens_fresh():
    item = enrich(FoodItem(type="leafy greens", decay_stage=1, estimated_kg=1.0))
    assert item.shelf_life_remaining_days == 4
    assert item.dollar_value == 4.0
    assert item.co2_kg == 1.7
    assert item.compostable is True


def test_enrich_spoiled_meat_flagged_contaminated():
    item = enrich(FoodItem(type="raw chicken", decay_stage=5, estimated_kg=0.5, mold_visible=True))
    assert item.contaminated is True
    assert item.compostable is False
    assert item.shelf_life_remaining_days == 0
