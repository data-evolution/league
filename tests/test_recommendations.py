import unittest

from src import app


def catalog():
    ids = ("3135", "6653", "3102", "3165", "3089", "3036", "3153", "3033", "3156", "3031", "4401", "3143", "3075", "6665", "3190", "3222", "3011", "3504")
    return {"patch": "test", "items": {item_id: {"name": item_id, "stats": {}, "description": ""} for item_id in ids}}


class RecommendationTests(unittest.TestCase):
    def payload(self, champion, items, enemy_champion="Tahm Kench", position="MIDDLE"):
        return {"activePlayer": {"summonerName": "Me"}, "allPlayers": [
            {"summonerName": "Me", "team": "ORDER", "championName": champion, "position": position, "items": items},
            {"summonerName": "Enemy", "team": "CHAOS", "championName": enemy_champion, "position": position, "items": []},
        ]}

    def reference(self, own_tags, enemy_tags):
        return {"champions": {"Diana": {"tags": own_tags}, "Jinx": {"tags": own_tags}, "Malphite": {"tags": own_tags}, "Milio": {"tags": own_tags}, "Tahm Kench": {"tags": enemy_tags}}}

    def test_ap_build_uses_magic_penetration_into_tank(self):
        choices, profile = app.recommend_items(self.payload("Diana", []), self.reference(["Mage"], ["Tank"]), catalog())
        self.assertEqual(profile["build"], "ap")
        self.assertEqual(choices[0]["itemId"], "3135")

    def test_ad_build_uses_armor_penetration_into_tank(self):
        choices, profile = app.recommend_items(self.payload("Jinx", []), self.reference(["Marksman"], ["Tank"]), catalog())
        self.assertEqual(profile["build"], "ad")
        self.assertEqual(choices[0]["itemId"], "3036")

    def test_tank_build_has_defensive_fallback(self):
        choices, profile = app.recommend_items(self.payload("Malphite", []), self.reference(["Tank"], ["Mage"]), catalog())
        self.assertEqual(profile["build"], "tank")
        self.assertEqual(choices[0]["itemId"], "4401")

    def test_support_build_detects_support_item(self):
        choices, profile = app.recommend_items(self.payload("Milio", [{"itemID": 3870}]), self.reference(["Mage"], ["Tank"]), catalog())
        self.assertEqual(profile["build"], "support")
        self.assertEqual(choices[0]["itemId"], "3190")

    def test_lane_counter_is_named_and_prioritized(self):
        choices, profile = app.recommend_items(self.payload("Diana", [], "Tahm Kench"), self.reference(["Mage"], ["Tank"]), catalog())
        self.assertEqual(profile["laneSummary"], "lane vs Tahm Kench (Middle)")
        self.assertTrue(choices[0]["reason"].startswith("Lane vs Tahm Kench:"))


if __name__ == "__main__":
    unittest.main()
