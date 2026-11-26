import re


def compare_income(payload):
    """Partial income model, independent of inventory value (never add them).

    CS uses a deliberately approximate 20g average, including jungle CS.
    Summoner's Rift global turret rewards: outer/nexus 50g per teammate,
    inner/inhibitor 25g. Plates, local rewards and bounties are excluded.
    https://wiki.leagueoflegends.com/en-us/Turret
    """
    players = payload.get("allPlayers", [])
    active = payload.get("activePlayer", {})
    me = next((p for p in players if any(
        active.get(key) and active[key] == p.get(key)
        for key in ("riotId", "summonerName")
    )), {})
    team = me.get("team")
    if team not in ("ORDER", "CHAOS") or payload.get("gameData", {}).get("mapNumber") != 11:
        return None
    sides = {side: [p for p in players if p.get("team") == side] for side in ("ORDER", "CHAOS")}
    if not all(sides.values()):
        return None
    income = {}
    for side, members in sides.items():
        scores = [p.get("scores", {}).get("creepScore") for p in members]
        income[side] = {"csGold": sum(scores) * 20 if all(isinstance(s, (int, float)) and s >= 0 for s in scores) else None,
                        "turretGold": 0, "turrets": 0}
    events = payload.get("events", {}).get("Events")
    if not isinstance(events, list):
        for value in income.values():
            value["turretGold"] = None
    else:
        seen = set()
        for event in events:
            if event.get("EventName") != "TurretKilled":
                continue
            turret = event.get("TurretKilled", "")
            # Attribute by the destroyed structure, even when a minion killed it.
            match = re.match(r"^Turret_T(Order|Chaos)_L[012]_P([1-5])_", turret)
            identity = (turret, event.get("EventTime"))
            if not match or identity in seen:
                continue
            seen.add(identity)
            side = "CHAOS" if match[1] == "Order" else "ORDER"
            per_player = 25 if match[2] in ("1", "2") else 50
            income[side]["turretGold"] += per_player * len(sides[side])
            income[side]["turrets"] += 1
    enemy = "CHAOS" if team == "ORDER" else "ORDER"
    return {"allies": income[team], "enemies": income[enemy], "goldPerCs": 20}


def compare_gold(payload):
    """Estimate total team gold earned from the live snapshot.

    The Live Client API does not expose enemy currentGold, so this uses a
    transparent estimate: starting gold, passive income, CS, kills, assists,
    and global turret rewards. It intentionally does not add item prices,
    because purchases are spending, not additional gold earned.
    """
    active = payload.get("activePlayer", {})
    players = payload.get("allPlayers", [])
    me = next((p for p in players if any(
        active.get(key) and active[key] == p.get(key)
        for key in ("riotId", "summonerName")
    )), None)
    if not me or me.get("team") not in ("ORDER", "CHAOS"):
        return None
    totals = {"ORDER": 0, "CHAOS": 0}
    present = set()
    game_time = float(payload.get("gameData", {}).get("gameTime", 0) or 0)
    passive_gold = max(0, game_time - 110) / 10 * 20.4
    for player in players:
        team = player.get("team")
        if team not in totals:
            continue
        present.add(team)
        scores = player.get("scores", {})
        totals[team] += 500 + passive_gold
        totals[team] += max(0, float(scores.get("creepScore", 0) or 0)) * 20
        totals[team] += max(0, float(scores.get("kills", 0) or 0)) * 300
        totals[team] += max(0, float(scores.get("assists", 0) or 0)) * 100
    if len(present) != 2:
        return None
    events = payload.get("events", {}).get("Events", [])
    if isinstance(events, list):
        team_sizes = {side: sum(player.get("team") == side for player in players) for side in totals}
        for event in events:
            if event.get("EventName") != "TurretKilled":
                continue
            match = re.match(r"^Turret_T(Order|Chaos)_L[012]_P([1-5])_", event.get("TurretKilled", ""))
            if not match:
                continue
            side = "CHAOS" if match[1] == "Order" else "ORDER"
            per_player = 25 if match[2] in ("1", "2") else 50
            totals[side] += per_player * team_sizes[side]
    enemy = "CHAOS" if me["team"] == "ORDER" else "ORDER"
    return {"allies": round(totals[me["team"]]), "enemies": round(totals[enemy])}
