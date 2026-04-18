from snaptrash_analytics.aggregations.restaurant_rolling import recommendation, top_category


def test_high_ps_recommendation():
    r = {"weekly_ps_count": 100, "compost_yield_rate": 0.7, "weekly_dollar_waste": 50}
    assert "PS foam" in recommendation(r)
    assert top_category(r) == "plastic"


def test_low_compost_yield():
    r = {"weekly_ps_count": 5, "compost_yield_rate": 0.3, "weekly_dollar_waste": 50}
    assert "Composting" in recommendation(r)


def test_on_track():
    r = {"weekly_ps_count": 5, "compost_yield_rate": 0.8, "weekly_dollar_waste": 50}
    assert "On track" in recommendation(r)
