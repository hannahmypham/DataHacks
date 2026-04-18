from snaptrash_common.schemas import PlasticItem
from snaptrash_ingestion.services.plastic_analysis import enrich


def test_pet_bottle_recyclable():
    item = enrich(PlasticItem(type="water bottle", resin_code=1))
    assert item.polymer_type == "PET"
    assert item.recyclable is True
    assert item.status == "recyclable"


def test_ps_foam_banned_in_ca():
    item = enrich(PlasticItem(type="foam container", resin_code=6), state="CA")
    assert item.polymer_type == "PS"
    assert item.harmful is True
    assert item.status == "banned_CA"
    assert item.alert is not None


def test_black_plastic_harmful():
    item = enrich(PlasticItem(type="black tray", is_black_plastic=True))
    assert item.harmful is True
    assert item.recyclable is False
