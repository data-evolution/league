import unittest
from unittest.mock import patch

from src import app
from src.gold import compare_gold, compare_income


class GoldTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"activePlayer": {"riotId": "Me#NA1", "currentGold": 900}, "allPlayers": [
            {"riotId": "Me#NA1", "team": "CHAOS", "items": [{"itemID": 1, "price": 100, "count": 2}]},
            {"riotId": "Enemy#NA1", "team": "ORDER", "items": [{"itemID": 2, "price": 200}]},
        ]}
        self.catalog = {"items": {"1": {"gold": {"total": 500}}, "2": {"gold": {"total": 1500}}}}

    def test_income_estimate_and_active_team(self):
        self.payload['gameData'] = {'gameTime': 1200}
        self.payload['allPlayers'][0]['scores'] = {'creepScore': 100, 'kills': 5, 'assists': 5}
        self.payload['allPlayers'][1]['scores'] = {'creepScore': 100, 'kills': 4, 'assists': 4}
        self.assertEqual(compare_gold(self.payload), {"allies": 6724, "enemies": 6324})

    def test_missing_item_price_does_not_block_income_estimate(self):
        del self.payload["allPlayers"][1]["items"][0]["price"]
        self.assertIsNotNone(compare_gold(self.payload))

    def test_missing_identity(self):
        self.payload["activePlayer"] = {}
        self.assertIsNone(compare_gold(self.payload))

    def test_starting_gold_without_scores(self):
        self.payload["allPlayers"][1]["items"][0]["price"] = 0
        self.assertEqual(compare_gold(self.payload)["enemies"], 500)

    def test_live_endpoint(self):
        with patch.object(app, "get_json", return_value=self.payload), patch.object(app, "attach_player_ranks"), patch.object(app, "enrich_live_payload", return_value={}), patch.object(app, "data_dragon_static", return_value=self.catalog), patch.object(app, "recommend_items", return_value=([], {})):
            result = app.app.test_client().get("/api/live")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["goldComparison"], {"allies": 500, "enemies": 500})

    def test_page(self):
        result = app.app.test_client().get("/")
        self.assertEqual(result.status_code, 200)
        self.assertIn(b'id="gold-allies"', result.data)
        self.assertIn(b'id="gold-objectives"', result.data)
        self.assertIn(b'v=utf8-2', result.data)

    def test_income_cs_and_minion_turret_kill(self):
        self.payload['gameData'] = {'mapNumber': 11}
        self.payload['allPlayers'][0]['scores'] = {'creepScore': 100}
        self.payload['allPlayers'][1]['scores'] = {'creepScore': 120}
        outer = {'EventName': 'TurretKilled', 'TurretKilled': 'Turret_TOrder_L1_P3_123_0', 'EventTime': 500, 'KillerName': 'Minion_T200'}
        inner = {'EventName': 'TurretKilled', 'TurretKilled': 'Turret_TChaos_L2_P2_456_0', 'EventTime': 600}
        self.payload['events'] = {'Events': [outer, outer, inner]}
        result = compare_income(self.payload)
        self.assertEqual(result['allies'], {'csGold': 2000, 'turretGold': 50, 'turrets': 1})
        self.assertEqual(result['enemies'], {'csGold': 2400, 'turretGold': 25, 'turrets': 1})
        # Total income is estimated independently of inventory prices.
        self.assertGreater(compare_gold(self.payload)['allies'], 0)

    def test_income_missing_data_and_unsupported_map(self):
        self.assertIsNone(compare_income(self.payload))
        self.payload['gameData'] = {'mapNumber': 11}
        result = compare_income(self.payload)
        self.assertIsNone(result['allies']['csGold'])
        self.assertIsNone(result['allies']['turretGold'])

    def test_turret_reward_paid_to_each_teammate(self):
        self.payload['gameData'] = {'mapNumber': 11}
        self.payload['allPlayers'].append({'team': 'CHAOS', 'items': []})
        self.payload['events'] = {'Events': [
            {'EventName': 'TurretKilled', 'TurretKilled': 'Turret_TOrder_L1_P1_123_0', 'EventTime': 100},
            {'EventName': 'TurretKilled', 'TurretKilled': 'Turret_TOrder_L1_P4_123_0', 'EventTime': 200},
            {'EventName': 'TurretKilled', 'TurretKilled': 'Turret_TOrder_L1_P4_123_0', 'EventTime': 500},
        ]}
        self.assertEqual(compare_income(self.payload)['allies']['turretGold'], 250)


if __name__ == "__main__":
    unittest.main()
