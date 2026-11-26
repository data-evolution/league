import logging
import os
import time
from collections import Counter
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock

import requests
import urllib3
from flask import Flask, jsonify, render_template
if __package__:
    from .ranks import attach_player_ranks
    from .gold import compare_gold, compare_income
else:
    from ranks import attach_player_ranks
    from gold import compare_gold, compare_income


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
rank_logger = logging.getLogger(attach_player_ranks.__module__)
rank_logger.setLevel(logging.INFO)
rank_log_path = str(LOG_DIR / "ranks.log")
if not any(getattr(handler, "baseFilename", None) == rank_log_path for handler in rank_logger.handlers):
    rank_file_handler = RotatingFileHandler(
        rank_log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    rank_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    rank_logger.addHandler(rank_file_handler)

app = Flask(
    __name__,
    static_folder=str(PROJECT_ROOT / "static"),
    template_folder=str(PROJECT_ROOT / "templates"),
)

LOCAL_CLIENT_URL = os.getenv(
    "LOL_CLIENT_URL",
    "https://127.0.0.1:2999/liveclientdata/allgamedata",
)
VERIFY_LOCAL_TLS = os.getenv("LOL_CLIENT_VERIFY_TLS", "false").lower() == "true"
DATA_DRAGON_ROOT = "https://ddragon.leagueoflegends.com"
HTTP_TIMEOUT = float(os.getenv("LOL_HTTP_TIMEOUT", "4"))

if not VERIFY_LOCAL_TLS:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

http = requests.Session()
static_cache = {"expires": 0.0, "value": None}
static_lock = Lock()
champion_detail_cache = {}


class UpstreamError(RuntimeError):
    pass


def get_json(url, **kwargs):
    try:
        response = http.get(url, timeout=HTTP_TIMEOUT, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        app.logger.exception("Upstream JSON request failed: %s", url)
        raise UpstreamError(str(exc)) from exc


def data_dragon_static():
    """Cache the public, patch-scoped champion and item catalogs for ten minutes."""
    now = time.time()
    with static_lock:
        if static_cache["value"] and static_cache["expires"] > now:
            return static_cache["value"]

        versions = get_json(f"{DATA_DRAGON_ROOT}/api/versions.json")
        patch = versions[0]
        champion_data = get_json(
            f"{DATA_DRAGON_ROOT}/cdn/{patch}/data/en_US/champion.json"
        ).get("data", {})
        item_data = get_json(
            f"{DATA_DRAGON_ROOT}/cdn/{patch}/data/en_US/item.json"
        ).get("data", {})
        value = {"patch": patch, "champions": champion_data, "items": item_data}
        static_cache.update({"expires": now + 600, "value": value})
        return value


def champion_detail(champion_id, patch):
    if not champion_id:
        return None
    cache_key = f"{patch}:{champion_id}"
    if cache_key not in champion_detail_cache:
        try:
            champion_detail_cache[cache_key] = get_json(
                f"{DATA_DRAGON_ROOT}/cdn/{patch}/data/en_US/champion/{champion_id}.json"
            ).get("data", {}).get(champion_id)
        except UpstreamError:
            return None
    return champion_detail_cache[cache_key]


def enrich_live_payload(payload):
    """Add client-safe Data Dragon references without replacing live-client data."""
    try:
        catalog = data_dragon_static()
    except UpstreamError:
        return {"patch": None, "champions": {}, "items": {}, "activeChampion": None}

    champion_catalog = catalog["champions"]
    item_catalog = catalog["items"]
    champion_names = {
        player.get("championName")
        for player in payload.get("allPlayers", [])
        if player.get("championName")
    }
    active = payload.get("activePlayer", {})
    me = next((player for player in payload.get("allPlayers", []) if any(
        active.get(field) and active.get(field) == player.get(field)
        for field in ("riotId", "summonerName")
    )), {})
    active_name = active.get("championName") or me.get("championName")
    if active_name:
        champion_names.add(active_name)

    champions = {}
    for name in champion_names:
        summary = champion_catalog.get(name) or next(
            (entry for entry in champion_catalog.values() if entry.get("name") == name), None
        )
        if summary:
            champions[name] = {
                "id": summary.get("id"),
                "key": summary.get("key"),
                "name": summary.get("name"),
                "title": summary.get("title"),
                "tags": summary.get("tags", []),
                "icon": f"{DATA_DRAGON_ROOT}/cdn/{catalog['patch']}/img/champion/{summary['image']['full']}",
            }

    item_ids = {
        str(item.get("itemID"))
        for player in payload.get("allPlayers", [])
        for item in player.get("items", [])
        if item.get("itemID") is not None
    }
    items = {}
    for item_id in item_ids:
        item = item_catalog.get(item_id)
        if item:
            items[item_id] = {
                "name": item.get("name"),
                "description": item.get("description", ""),
                "stats": item.get("stats", {}),
                "icon": f"{DATA_DRAGON_ROOT}/cdn/{catalog['patch']}/img/item/{item_id}.png",
            }

    active_summary = champions.get(active_name)
    detail = champion_detail(active_summary.get("id"), catalog["patch"]) if active_summary else None
    return {
        "patch": catalog["patch"],
        "champions": champions,
        "items": items,
        "activeChampion": detail,
    }


def enemy_profile(payload, reference, catalog):
    active = payload.get("activePlayer", {})
    players = payload.get("allPlayers", [])
    me = next(
        (player for player in players if player.get("summonerName") == active.get("summonerName")),
        {},
    )
    team = active.get("team") or me.get("team") or "ORDER"
    enemies = [player for player in players if player.get("team") and player.get("team") != team]
    lane_opponent = next(
        (player for player in enemies if me.get("position") and player.get("position") == me.get("position")),
        None,
    )
    lane_tags = reference.get("champions", {}).get(
        lane_opponent.get("championName") if lane_opponent else None, {}
    ).get("tags", [])
    tags = Counter()
    enemy_names = []
    enemy_item_ids = set()
    for player in enemies:
        name = player.get("championName")
        if name:
            enemy_names.append(name)
            tags.update(reference.get("champions", {}).get(name, {}).get("tags", []))
        enemy_item_ids.update(
            str(item.get("itemID"))
            for item in player.get("items", [])
            if item.get("itemID") is not None
        )

    enemy_descriptions = [
        catalog.get("items", {}).get(item_id, {}).get("description", "").lower()
        for item_id in enemy_item_ids
    ]
    mr_items = sum("magic resist" in description for description in enemy_descriptions)
    healing_names = {"Aatrox", "Briar", "Dr. Mundo", "Swain", "Vladimir", "Soraka", "Warwick", "Sylas"}
    healing_pressure = bool(healing_names.intersection(enemy_names)) or any(
        word in " ".join(enemy_descriptions) for word in ("healing", "heal", "omnivamp")
    )
    profile = {
        "team": team,
        "enemyNames": enemy_names,
        "tags": dict(tags),
        "summary": f"{tags.get('Tank', 0)} tank · {tags.get('Mage', 0)} magic · {tags.get('Marksman', 0)} marksman",
        "healingPressure": healing_pressure,
        "mrItems": mr_items,
        "laneOpponent": {
            "champion": lane_opponent.get("championName"),
            "position": lane_opponent.get("position"),
            "tags": lane_tags,
        } if lane_opponent else None,
        "laneSummary": (
            f"lane vs {lane_opponent.get('championName')} ({lane_opponent.get('position', '').title()})"
            if lane_opponent else "lane matchup unavailable"
        ),
    }
    return profile


def recommend_items(payload, reference, catalog):
    profile = enemy_profile(payload, reference, catalog)
    active = payload.get("activePlayer", {})
    players = payload.get("allPlayers", [])
    me = next(
        (player for player in players if player.get("summonerName") == active.get("summonerName")),
        {},
    )
    owned = {
        str(item.get("itemID"))
        for item in me.get("items", [])
        if item.get("itemID") is not None
    }
    tags = profile["tags"]
    my_tags = reference.get("champions", {}).get(me.get("championName"), {}).get("tags", [])
    owned_items = [catalog.get("items", {}).get(item_id, {}) for item_id in owned]
    item_stats = [item.get("stats", {}) for item in owned_items]
    ability_power = sum(stats.get("FlatMagicDamageMod", 0) for stats in item_stats)
    attack_damage = sum(stats.get("FlatPhysicalDamageMod", 0) for stats in item_stats)
    durability = sum(stats.get(key, 0) for stats in item_stats for key in ("FlatHPPoolMod", "FlatArmorMod", "FlatSpellBlockMod"))
    support_item = any(3850 <= int(item_id) <= 3879 for item_id in owned if item_id.isdigit())
    if support_item or ("Support" in my_tags and not owned):
        build = "support"
    elif ability_power > attack_damage * 1.2 or ("Mage" in my_tags and not owned):
        build = "ap"
    elif attack_damage > ability_power * 1.2 or any(tag in my_tags for tag in ("Marksman", "Assassin", "Fighter")):
        build = "ad"
    elif durability >= 100 or "Tank" in my_tags:
        build = "tank"
    else:
        build = "adaptive"
    profile["build"] = build
    choices = []

    lane_name = (profile.get("laneOpponent") or {}).get("champion")

    def add(item_id, reason, trigger=True, lane=False):
        item_id = str(item_id)
        if trigger and item_id in catalog.get("items", {}) and item_id not in owned and item_id not in {choice["itemId"] for choice in choices}:
            item = catalog.get("items", {}).get(item_id, {})
            choices.append({
                "itemId": item_id,
                "name": item.get("name", f"Item {item_id}"),
                "icon": f"{DATA_DRAGON_ROOT}/cdn/{catalog['patch']}/img/item/{item_id}.png",
                "reason": f"Lane vs {lane_name}: {reason}" if lane and lane_name else reason,
            })

    tanky_enemy = tags.get("Tank", 0) or profile["mrItems"] >= 2
    magic_pressure = tags.get("Mage", 0) + tags.get("Support", 0) >= 2
    physical_pressure = tags.get("Marksman", 0) + tags.get("Assassin", 0) + tags.get("Fighter", 0) >= 3
    lane_tags = (profile.get("laneOpponent") or {}).get("tags", [])
    lane_tanky = "Tank" in lane_tags
    lane_magic = "Mage" in lane_tags
    lane_physical = any(tag in lane_tags for tag in ("Marksman", "Assassin", "Fighter"))
    lane_healing = lane_name in {"Aatrox", "Briar", "Dr. Mundo", "Swain", "Vladimir", "Soraka", "Warwick", "Sylas"}
    if build == "ap":
        add("3135", "magic penetration is stronger into their tanky defenses.", lane_tanky, lane=True)
        add("3102", "a spell shield can deny their magic burst or crowd control.", lane_magic, lane=True)
        add("3135", "Enemy frontline or MR makes flat magic penetration less reliable.", tanky_enemy)
        add("6653", "Health-heavy targets reward extended damage.", tanky_enemy)
        add("3102", "Magic damage or crowd control makes a spell shield valuable.", magic_pressure)
        add("3165", "Enemy sustain is high enough that Grievous Wounds can matter.", profile["healingPressure"])
        add("3089", "A reliable AP multiplier when no specific counter is needed.")
    elif build == "ad":
        add("3036", "armor penetration helps your physical damage through their defenses.", lane_tanky, lane=True)
        add("3156", "a magic-damage shield helps you survive their burst.", lane_magic, lane=True)
        add("3036", "Armor penetration helps your physical damage through a tanky frontline.", tanky_enemy)
        add("3153", "Health-heavy targets make on-hit current-health damage valuable.", tanky_enemy)
        add("3033", "Enemy healing makes Mortal Reminder the AD anti-heal option.", profile["healingPressure"])
        add("3156", "Magic burst makes a magic-damage shield a safer damage slot.", magic_pressure)
        add("3031", "A high-damage crit option when no direct counter is required.")
    elif build == "tank":
        add("4401", "magic resistance and its shield answer their lane damage.", lane_magic, lane=True)
        add("3143", "armor and crit mitigation answer their physical lane damage.", lane_physical, lane=True)
        add("4401", "Magic-heavy enemies call for a large magic-resist shield.", magic_pressure)
        add("3143", "Physical carries and crits are reduced by armor and crit mitigation.", physical_pressure)
        add("3075", "Thornmail supplies armor and anti-heal into sustain-heavy physical teams.", profile["healingPressure"] and physical_pressure)
        add("6665", "A broadly useful durability option for mixed damage.")
    elif build == "support":
        add("3222", "cleanse and healing help answer their magic damage and crowd control.", lane_magic, lane=True)
        add("3011", "Grievous Wounds helps answer their lane sustain.", lane_healing, lane=True)
        add("3190", "Teamwide shielding is strong into burst or grouped fights.")
        add("3222", "Cleanse and heal support allies against magic damage and crowd control.", magic_pressure)
        add("3011", "Enemy healing calls for a support-friendly Grievous Wounds option.", profile["healingPressure"])
        add("3504", "Buff an allied attack-speed carry when the enemy has no clear counter angle.")
    else:
        add("6665", "A safe mixed-defense choice while your build direction is still unclear.")
        add("3102", "A spell shield helps against magic burst and crowd control.", magic_pressure)
        add("3033", "Grievous Wounds answers enemy sustain.", profile["healingPressure"])
    return choices[:3], profile


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "league-live-analysis"})


@app.get("/api/icons")
def icons():
    """Allow demo portraits to load without an active League game."""
    try:
        catalog = data_dragon_static()
        patch = catalog["patch"]
        return jsonify({"patch": patch, "champions": {
            entry["name"]: {"icon": f"{DATA_DRAGON_ROOT}/cdn/{patch}/img/champion/{entry['image']['full']}"}
            for entry in catalog["champions"].values()
        }})
    except UpstreamError:
        return jsonify({"error": "Champion icons temporarily unavailable"}), 503


@app.get("/api/live")
def live():
    try:
        payload = get_json(LOCAL_CLIENT_URL, verify=VERIFY_LOCAL_TLS)
        response = dict(payload)
        response["incomeComparison"] = compare_income(payload)
        attach_player_ranks(response)
        response["reference"] = enrich_live_payload(payload)
        try:
            catalog = data_dragon_static()
            response["goldComparison"] = compare_gold(payload)
            response["recommendations"], response["enemyProfile"] = recommend_items(
                payload, response["reference"], catalog
            )
        except UpstreamError:
            response["goldComparison"] = None
            response["recommendations"], response["enemyProfile"] = [], {}
        return jsonify(response)
    except UpstreamError as exc:
        return jsonify({"ok": False, "error": str(exc), "source": LOCAL_CLIENT_URL}), 502


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "true").lower() == "true",
    )
