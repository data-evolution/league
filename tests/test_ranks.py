import os
import unittest
from unittest.mock import patch, Mock
import requests
from src.ranks import RankService, attach_player_ranks


class RankTests(unittest.TestCase):
    def setUp(self):
        self.service = RankService()
        self.addCleanup(self.service.worker.shutdown)

    def test_missing_key(self):
        with patch.dict(os.environ, {"RIOT_API_KEY": ""}), patch('src.ranks.requests.get') as get:
            self.assertIn('API key needed', self.service.status({})['label'])
            get.assert_not_called()

    def test_rank_routing_and_cache(self):
        responses = [Mock(status_code=200), Mock(status_code=200)]
        responses[0].json.return_value = {"puuid": "abc"}
        responses[1].json.return_value = [{"queueType": "RANKED_SOLO_5x5", "tier": "GOLD", "rank": "II", "leaguePoints": 42}]
        with patch('src.ranks.requests.get', side_effect=responses) as get:
            self.service.lookup(('Some Player', 'NA1'), 'test-secret')
            self.assertIn('americas.api.riotgames.com', get.call_args_list[0].args[0])
            self.assertIn('Some%20Player/NA1', get.call_args_list[0].args[0])
            self.assertIn('na1.api.riotgames.com/lol/league/v4/entries/by-puuid/abc', get.call_args_list[1].args[0])
            with patch.dict(os.environ, {"RIOT_API_KEY": "test-secret"}):
                result = self.service.status({"riotId": "Some Player#NA1"})
            self.assertEqual(result['label'], 'Solo: Gold II · 42 LP')
            self.assertEqual(get.call_count, 2)
            self.assertEqual(result['tier'], 'GOLD')

    def test_unranked_frame_tier(self):
        with patch.object(self.service, 'request', side_effect=[{'puuid': 'abc'}, []]):
            self.service.lookup(('Unranked', 'NA1'), 'test-secret')
        self.assertEqual(self.service.cache[('Unranked', 'NA1')][1]['tier'], 'UNRANKED')

    def test_rate_limit_pauses_other_lookups(self):
        response = Mock(status_code=429, headers={"Retry-After": "120"})
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        with patch('src.ranks.requests.get', return_value=response) as get:
            self.service.lookup(('One', 'NA1'), 'secret')
            self.service.lookup(('Two', 'NA1'), 'secret')
            self.assertEqual(get.call_count, 1)
            self.assertIn('rate limited', self.service.cache[('Two', 'NA1')][1]['label'])

    def test_both_teams_including_active_player(self):
        payload = {"activePlayer": {"riotId": "Me#NA1"}, "allPlayers": [
            {"riotId": "Me#NA1", "team": "CHAOS"},
            {"riotId": "Enemy#NA1", "team": "ORDER"}]}
        with patch('src.ranks.rank_service.status', return_value={"label": "Solo: Unranked"}) as status:
            attach_player_ranks(payload)
            self.assertEqual(status.call_count, 2)
            self.assertIn('ranked', payload['allPlayers'][0])
            self.assertIn('ranked', payload['allPlayers'][1])

    def test_rejected_rank_logs_context_and_redacts_key(self):
        response = Mock(status_code=403, headers={}, text='Forbidden test-secret\nextra line')
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        with patch.object(self.service, 'request', wraps=self.service.request), patch('src.ranks.requests.get', return_value=response), self.assertLogs('src.ranks', level='INFO') as logs:
            self.service.lookup(('Player', 'NA1'), 'test-secret')
            self.service.lookup(('Next', 'NA1'), 'test-secret')
        output = '\n'.join(logs.output)
        self.assertIn("player='Player#NA1' stage=account status=403", output)
        self.assertIn('Forbidden [REDACTED]\\nextra line', output)
        self.assertNotIn('test-secret', output)
        self.assertIn('Rank lookups paused', output)
        self.assertIn("Rank skipped player='Next#NA1'", output)

    def test_bots_on_both_teams_skip_lookup(self):
        payload = {"allPlayers": [{"team": team, "isBot": True} for team in ("ORDER", "CHAOS")]}
        with patch('src.ranks.rank_service.status') as status:
            attach_player_ranks(payload)
            status.assert_not_called()
        for player in payload['allPlayers']:
            self.assertEqual(player['ranked'], {"label": "Bot"})
