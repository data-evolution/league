import unittest
from unittest.mock import patch

from src import app


class IconTests(unittest.TestCase):
    def test_display_names_and_active_player_identity(self):
        catalog = {"patch": "test", "items": {}, "champions": {
            "TahmKench": {"id": "TahmKench", "name": "Tahm Kench", "image": {"full": "TahmKench.png"}},
            "Diana": {"id": "Diana", "name": "Diana", "image": {"full": "Diana.png"}},
        }}
        payload = {"activePlayer": {"riotId": "Player#123"}, "allPlayers": [
            {"riotId": "Player#123", "championName": "Diana"},
            {"championName": "Tahm Kench"},
        ]}
        with patch.object(app, "data_dragon_static", return_value=catalog), patch.object(app, "champion_detail", return_value={"id": "Diana"}) as detail:
            result = app.enrich_live_payload(payload)
            self.assertTrue(result["champions"]["Tahm Kench"]["icon"].endswith("TahmKench.png"))
            detail.assert_called_once_with("Diana", "test")
            response = app.app.test_client().get("/api/icons")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Tahm Kench", response.json["champions"])

    def test_fallback_asset(self):
        response = app.app.test_client().get("/static/img/unavailable.svg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/svg+xml")
        response.close()


if __name__ == "__main__":
    unittest.main()
