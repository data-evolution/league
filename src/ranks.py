"""Cached NA ranked lookups; background work never delays live game polling."""
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


def log_value(value, key):
    """Keep remote text on one line and remove any echoed credential."""
    text = str(value)
    if key:
        text = text.replace(key, "[REDACTED]")
    return repr(text[:500])


class RankService:
    def __init__(self):
        self.cache = {}
        self.lock = Lock()
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.retry_at = 0
        self.paused_label = "Rank unavailable"

    def status(self, player):
        key = os.getenv("RIOT_API_KEY", "").strip()
        if not key:
            return {"label": "Rank: API key needed"}
        name, tag = player.get("riotIdGameName"), player.get("riotIdTagLine")
        if not (name and tag):
            identity = player.get("riotId") or player.get("summonerName", "")
            if "#" not in identity:
                return {"label": "Rank: Riot ID unavailable"}
            name, tag = identity.rsplit("#", 1)
        identity = (name, tag)
        with self.lock:
            now = time.time()
            cached = self.cache.get(identity)
            if cached and cached[0] > now:
                return cached[1]
            if now < self.retry_at:
                return {"label": self.paused_label}
            pending = {"label": "Rank: loading..."}
            self.cache[identity] = (now + 120, pending)
            logger.info("Rank queued player=%s team=%s", log_value(f"{name}#{tag}", key), player.get("team", "unknown"))
            self.worker.submit(self.lookup, identity, key)
            return pending

    def request(self, url, key):
        endpoint = "account (americas)" if "/riot/account/" in url else "ranked (na1)"
        started = time.monotonic()
        response = requests.get(url, headers={"X-Riot-Token": key}, timeout=4)
        logger.info("Rank API endpoint=%s status=%s elapsed_ms=%.0f", endpoint, response.status_code, (time.monotonic() - started) * 1000)
        if response.status_code >= 400:
            logger.warning("Rank API rejected endpoint=%s status=%s body=%s retry_after=%s rate_limit_type=%s", endpoint, response.status_code, log_value(response.text, key), log_value(response.headers.get("Retry-After", ""), key), log_value(response.headers.get("X-Rate-Limit-Type", ""), key))
        if response.status_code in (401, 403, 429):
            delay = 300
            label = "Rank: key invalid or expired"
            if response.status_code == 429:
                label = "Rank: rate limited"
                try:
                    delay = max(1, float(response.headers.get("Retry-After", 60)))
                except ValueError:
                    delay = 60
            with self.lock:
                self.retry_at = time.time() + delay
                self.paused_label = label
            logger.warning("Rank lookups paused for %.0fs after HTTP %s; cached ranks remain visible", delay, response.status_code)
        response.raise_for_status()
        return response.json()

    def lookup(self, identity, key):
        ttl = 60
        result = {"label": "Rank unavailable"}
        player = log_value("#".join(identity), key)
        stage = "account"
        try:
            with self.lock:
                if time.time() < self.retry_at:
                    result = {"label": self.paused_label}
                    logger.info("Rank skipped player=%s pause_remaining_seconds=%.0f reason=%s", player, self.retry_at - time.time(), self.paused_label)
                    return
            logger.info("Rank lookup started player=%s", player)
            name, tag = (quote(part, safe="") for part in identity)
            account = self.request(f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{name}/{tag}", key)
            puuid = quote(account["puuid"], safe="")
            stage = "ranked"
            entries = self.request(f"https://na1.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}", key)
            if not isinstance(entries, list):
                raise ValueError("Invalid ranked response")
            queues = {}
            solo_tier = "UNRANKED"
            for entry in entries:
                queue = entry.get("queueType")
                if queue == "RANKED_SOLO_5x5":
                    solo_tier = entry["tier"]
                if queue in ("RANKED_SOLO_5x5", "RANKED_FLEX_SR"):
                    queues[queue] = f"{entry['tier'].title()} {entry['rank']} · {entry['leaguePoints']} LP"
            solo = queues.get("RANKED_SOLO_5x5", "Unranked")
            flex = queues.get("RANKED_FLEX_SR", "Unranked")
            result = {"label": f"Solo: {solo}", "detail": f"NA | Solo/Duo: {solo} | Flex: {flex}"}
            ttl = 600
            result["tier"] = solo_tier
            logger.info("Rank lookup succeeded player=%s result=%s cache_seconds=%s", player, log_value(result["label"], key), ttl)
        except requests.HTTPError as error:
            status = error.response.status_code
            labels = {404: "Rank: account not found", 401: "Rank: key invalid or expired", 403: "Rank: key invalid or expired", 429: "Rank: rate limited"}
            result = {"label": labels.get(status, "Rank unavailable")}
            logger.warning("Rank lookup failed player=%s stage=%s status=%s", player, stage, status)
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            logger.warning("Rank lookup failed player=%s stage=%s error_type=%s", player, stage, type(error).__name__)
        finally:
            with self.lock:
                self.cache[identity] = (time.time() + ttl, result)


rank_service = RankService()


def attach_player_ranks(payload):
    """Attach cached ranks for both teams, including the active player."""
    players = payload.get("allPlayers", [])
    for player in players:
        if player.get("team") in ("ORDER", "CHAOS"):
            player["ranked"] = {"label": "Bot"} if player.get("isBot") else rank_service.status(player)
