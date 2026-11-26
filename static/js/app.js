const state = { endpoint: '/api/live', demo: false, loading: false, iconsRetryAt: 0 };
const $ = (id) => document.getElementById(id);
const ICON_FALLBACK = '/static/img/unavailable.svg';
document.addEventListener('error', (event) => {
  const image = event.target;
  if (image instanceof HTMLImageElement && image.getAttribute('src') !== ICON_FALLBACK) {
    image.src = ICON_FALLBACK;
    image.title = image.title || 'Icon unavailable';
  }
}, true);
const text = (id, value) => { const el = $(id); if (el) el.textContent = value ?? '—'; };
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const formatTime = (seconds) => { const total = Math.max(0, Math.floor(Number(seconds) || 0)); return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`; };

const demoData = { gameData: { gameTime: 842, mapName: "Map11", gameMode: "CLASSIC" }, activePlayer: { championName: "Diana", summonerName: "Demo Player", level: 15, scores: { kills: 10, deaths: 10, assists: 10, creepScore: 112 }, abilities: { Q: { displayName: "Crescent Strike", abilityLevel: 5 }, W: { displayName: "Pale Cascade", abilityLevel: 5 }, E: { displayName: "Lunar Rush", abilityLevel: 3 }, R: { displayName: "Moonfall", abilityLevel: 2 }, Passive: { displayName: "Moonsilver Blade", abilityLevel: 0 } } }, allPlayers: [ { summonerName: "Demo Player", championName: "Diana", position: "MIDDLE", team: "CHAOS", scores: { kills: 10, deaths: 10, assists: 10, creepScore: 112 }, items: [] }, { summonerName: "Tahm player", championName: "Tahm Kench", position: "TOP", team: "ORDER", scores: { kills: 5, deaths: 2, assists: 6, creepScore: 130 }, items: [] }, { summonerName: "Viego player", championName: "Viego", position: "JUNGLE", team: "ORDER", scores: { kills: 7, deaths: 2, assists: 8, creepScore: 100 }, items: [] } ], events: { Events: [] }, reference: { patch: "demo", champions: {}, items: {}, activeChampion: null } };

function setTracker(name, value, detail, percent, status, label) {
  text(`${name}-target-value`, value);
  text(`${name}-target-detail`, detail);
  const stateEl = $(`${name}-state`);
  stateEl.textContent = label;
  stateEl.className = status;
  const bar = $(`${name}-bar`);
  bar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  bar.className = status;
}

function render(data) {
  const players = Array.isArray(data.allPlayers) ? data.allPlayers : [];
  const game = data.gameData || {};
  const active = data.activePlayer || {};
  const activeScores = active.scores || {};
  const me = players.find((player) => ['riotId', 'summonerName'].some((key) => active[key] && player[key] === active[key])) || players.find((player) => active.championName && player.championName === active.championName) || {};
  const score = Object.keys(activeScores).length ? activeScores : (me.scores || {});
  const team = active.team || me.team || 'ORDER';
  const allies = players.filter((player) => player.team === team);
  const enemies = players.filter((player) => player.team && player.team !== team);
  const teamKills = allies.reduce((sum, player) => sum + Number(player.scores?.kills || 0), 0);
  const enemyKills = enemies.reduce((sum, player) => sum + Number(player.scores?.kills || 0), 0);
  const minutes = Math.max(Number(game.gameTime || 0) / 60, 1);
  const cs = Number(score.creepScore || 0);
  const level = Number(active.level || me.level || 0);
  const deaths = Number(score.deaths || 0);
  const kp = teamKills ? (Number(score.kills || 0) + Number(score.assists || 0)) / teamKills * 100 : 0;
  const wardScore = Number(score.wardScore || 0);
  const reference = data.reference || {};
  const activeRef = reference.activeChampion || {};
  const championRef = reference.champions?.[active.championName || me.championName];

  text('game-time', formatTime(game.gameTime));
  text('champion-name', active.championName || me.championName);
  text('champion-level', `level ${level || '—'}`);
  text('kda', `${score.kills || 0} / ${score.deaths || 0} / ${score.assists || 0}`);
  text('cs', `${cs} CS · ${(cs / minutes).toFixed(1)} / min`);
  text('team-kills', teamKills);
  text('enemy-kills', `enemy ${enemyKills}`);
  text('patch-label', `Patch ${reference.patch || '—'}`);
  text('game-mode', game.gameMode || '—');
  text('roster-count', `${players.length} detected`);
  text('item-patch', `Data Dragon ${reference.patch || '—'}`);
  text('active-role', me.position || 'ACTIVE PLAYER');
  text('active-champion', active.championName || me.championName || '—');
  text('active-stats', `${active.championStats?.abilityPower ? Math.round(active.championStats.abilityPower) + ' AP · ' : ''}${active.championStats?.abilityHaste || 0} haste · ${active.championStats?.moveSpeed ? Math.round(active.championStats.moveSpeed) + ' MS' : 'stats pending'}`);
  text('enemy-profile', data.enemyProfile?.summary || 'enemy comp —');
  if (data.enemyProfile?.build) {
    text('enemy-profile', `${data.enemyProfile.summary} · your ${data.enemyProfile.build.toUpperCase()}`);
  }
  if (data.enemyProfile?.laneSummary) {
    text('enemy-profile', `${data.enemyProfile.laneSummary} / your ${(data.enemyProfile.build || 'adaptive').toUpperCase()}`);
  }
  let activeStatGrid = $('active-stat-grid');
  if (!activeStatGrid) {
    activeStatGrid = document.createElement('div');
    activeStatGrid.id = 'active-stat-grid';
    activeStatGrid.className = 'active-stat-grid';
    activeStatGrid.setAttribute('aria-label', 'Current champion stats');
    document.querySelector('.active-summary').append(activeStatGrid);
  }
  const stats = active.championStats || {};
  const statNumber = (value) => Number.isFinite(Number(value)) ? Math.round(Number(value)) : '—';
  const resourceName = stats.resourceType === 'MANA' ? 'Mana' : (stats.resourceType || 'Resource');
  const damage = `${statNumber(stats.abilityPower)} AP · ${statNumber(stats.attackDamage)} AD`;
  const defenses = `${statNumber(stats.armor)} AR · ${statNumber(stats.magicResist)} MR`;
  const penetration = stats.magicPenetrationFlat ? `${statNumber(stats.magicPenetrationFlat)} Mpen` : `${statNumber(stats.armorPenetrationFlat)} ArPen`;
  const liveStats = [
    ['♥', 'Health', `${statNumber(stats.currentHealth)} / ${statNumber(stats.maxHealth)}`],
    ['◆', resourceName, `${statNumber(stats.resourceValue)} / ${statNumber(stats.resourceMax)}`],
    ['⚔', 'Damage', damage],
    ['⬟', 'Defense', defenses],
    ['↗', 'Utility', `${statNumber(stats.abilityHaste)} AH · ${statNumber(stats.moveSpeed)} MS`],
    ['¤', 'Gold', `${statNumber(active.currentGold)} g · ${penetration}`],
  ];
  activeStatGrid.innerHTML = liveStats.map(([icon, label, value]) => `<div class="active-stat"><span><i class="stat-icon" aria-hidden="true">${icon}</i>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join('');
  text('session-status', state.demo ? 'Demo signal' : 'Live game found');
  text('session-meta', `${game.mapName || 'Map'} · ${formatTime(game.gameTime)}`);
  const gold = state.demo ? { allies: 7200, enemies: 11500 } : data.goldComparison;
  const goldAvailable = gold && Number.isFinite(gold.allies) && Number.isFinite(gold.enemies);
  const goldDelta = goldAvailable ? gold.allies - gold.enemies : 0;
  const goldFormat = value => Math.round(value).toLocaleString();
  const eventList = data.events?.Events || [];
  const identityNames = new Set([
    active.summonerName, active.riotIdGameName, me.summonerName, me.riotIdGameName,
    active.summonerName?.split('#')[0], me.summonerName?.split('#')[0],
  ].filter(Boolean).map((name) => String(name).toLowerCase()));
  const eventCreditsMe = (event) => [event.KillerName, ...(event.Assisters || [])]
    .filter(Boolean).some((name) => identityNames.has(String(name).toLowerCase()));
  const objectiveCredits = (eventName) => eventList.filter((event) => event.EventName === eventName && eventCreditsMe(event)).length;
  const objectiveSplit = (eventName) => {
    const result = { kills: 0, assists: 0 };
    eventList.filter((event) => event.EventName === eventName).forEach((event) => {
      if (event.KillerName && identityNames.has(String(event.KillerName).toLowerCase())) result.kills += 1;
      if ((event.Assisters || []).some((name) => identityNames.has(String(name).toLowerCase()))) result.assists += 1;
    });
    return result;
  };
  const turretSplit = objectiveSplit('TurretKilled');
  const inhibSplit = objectiveSplit('InhibKilled');
  const dragonSplit = objectiveSplit('DragonKill');
  const objectivePlaceholder = Array.isArray(eventList) && eventList.length ? null : 0;
  text('objective-turrets', objectivePlaceholder !== null ? '0/0' : `${turretSplit.kills}/${turretSplit.assists}`);
  text('objective-dragons', objectivePlaceholder !== null ? '0/0' : `${dragonSplit.kills}/${dragonSplit.assists}`);
  text('objective-inhibitors', objectivePlaceholder !== null ? '0/0' : `${inhibSplit.kills}/${inhibSplit.assists}`);
  text('gold-objectives', `Your objectives: turrets ${objectiveCredits('TurretKilled')} · inhibitors ${objectiveCredits('InhibKilled')}`);
  text('gold-allies', goldAvailable ? `${goldFormat(gold.allies)} g` : '—');
  text('gold-enemies', goldAvailable ? `${goldFormat(gold.enemies)} g` : '—');
  text('gold-difference', goldAvailable ? (goldDelta === 0 ? 'Even item value' : `${goldFormat(Math.abs(goldDelta))} g ${goldDelta > 0 ? 'ahead' : 'behind'}`) : 'Comparison unavailable');
  $('gold-difference').style.color = goldAvailable ? (goldDelta < 0 ? 'var(--red)' : 'var(--accent)') : 'var(--muted)';
  $('gold-share').style.width = `${goldAvailable && gold.allies + gold.enemies > 0 ? 100 * gold.allies / (gold.allies + gold.enemies) : 50}%`;
  $('gold-share').parentElement.style.opacity = goldAvailable ? '1' : '.3';

  const csTarget = Math.max(1, Math.round(minutes * 7));
  setTracker('cs', `${cs}`, `${(cs / minutes).toFixed(1)} CS / min`, cs / csTarget * 100, cs / csTarget >= 1 ? 'good' : cs / csTarget >= .85 ? 'warn' : 'bad', cs / csTarget >= 1 ? 'on pace' : cs / csTarget >= .85 ? 'close' : 'behind');
  setTracker('level', `${level} / 18`, `level ${level} reached`, level / 18 * 100, level >= 16 ? 'good' : level >= 13 ? 'warn' : 'bad', level >= 16 ? 'on pace' : level >= 13 ? 'close' : 'behind');
  setTracker('death', `${deaths}`, deaths <= 5 ? `${5 - deaths} left` : `${deaths - 5} over target`, deaths <= 5 ? (5 - deaths) / 5 * 100 : 0, deaths <= 3 ? 'good' : deaths <= 5 ? 'warn' : 'bad', deaths <= 3 ? 'safe' : deaths <= 5 ? 'limit' : 'over');
  setTracker('kp', `${Math.round(kp)}%`, `${Number(score.kills || 0) + Number(score.assists || 0)} of ${teamKills} team kills`, kp, kp >= 65 ? 'good' : kp >= 50 ? 'warn' : 'bad', kp >= 65 ? 'on target' : kp >= 50 ? 'close' : 'low');
  const wardTarget = Math.max(1, minutes * 1.5);
  setTracker('ward', wardScore.toFixed(1), `${(wardScore / minutes).toFixed(1)} score / min`, wardScore / wardTarget * 100, wardScore >= wardTarget ? 'good' : wardScore >= wardTarget * .8 ? 'warn' : 'bad', wardScore >= wardTarget ? 'on pace' : wardScore >= wardTarget * .8 ? 'close' : 'behind');

  const icon = $('champion-icon');
  if (championRef?.icon) { icon.src = championRef.icon; icon.alt = active.championName || ''; icon.classList.remove('hidden'); } else icon.classList.add('hidden');
  const lanes = ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY'];
  const laneName = { TOP: 'Top', JUNGLE: 'Jungle', MIDDLE: 'Mid', BOTTOM: 'Bot', UTILITY: 'Support' };
  const tiers = ['iron', 'bronze', 'silver', 'gold', 'platinum', 'emerald', 'diamond', 'master', 'grandmaster', 'challenger', 'unranked'];
  const playerForLane = (side, lane) => players.find((player) => player.team === side && player.position === lane);
  const buildType = (player) => {
    let ap = 0;
    let ad = 0;
    for (const item of player.items || []) {
      const ref = reference.items?.[String(item.itemID)] || {};
      const stats = ref.stats || {};
      ap += Number(stats.FlatMagicDamageMod || 0);
      ad += Number(stats.FlatPhysicalDamageMod || 0);
      const description = String(ref.description || '').toLowerCase();
      if (!stats.FlatMagicDamageMod && /ability power|<attention>ap<\/attention>/.test(description)) ap += 1;
      if (!stats.FlatPhysicalDamageMod && /attack damage|<attention>ad<\/attention>/.test(description)) ad += 1;
    }
    const championTags = reference.champions?.[player.championName]?.tags || [];
    if (ap && ad) return ap / ad > 1.4 ? 'AP' : ad / ap > 1.4 ? 'AD' : 'Mixed';
    if (ap || championTags.includes('Mage')) return 'AP';
    if (ad || championTags.some((tag) => ['Marksman', 'Assassin', 'Fighter'].includes(tag))) return 'AD';
    return 'Build unknown';
  };
  const teamBuildCounts = (side) => {
    const counts = { AP: 0, AD: 0 };
    players.filter((player) => player.team === side).forEach((player) => {
      const type = buildType(player);
      if (type === 'AP' || type === 'Mixed') counts.AP += 1;
      if (type === 'AD' || type === 'Mixed') counts.AD += 1;
    });
    return counts;
  };
  const playerCard = (player, side, lane, index) => {
    if (!player) return `<div class="lane-player missing">No ${laneName[lane]} data</div>`;
    const ref = reference.champions?.[player.championName];
    const scores = player.scores || {};
    const isEnemy = side !== team;
    const tier = state.demo ? (index % 2 ? 'gold' : 'diamond') : String(player.ranked?.tier || '').toLowerCase();
    const frame = `rank-frame rank-${tiers.includes(tier) ? tier : 'unknown'}`;
    const rank = state.demo ? `${tier[0].toUpperCase()}${tier.slice(1)} (demo)` : (player.ranked?.label?.replace('Solo: ', '') || 'Rank unavailable');
    const detail = state.demo ? `Demo sample: ${tier} rank` : (player.ranked?.detail || player.ranked?.label || 'NA ranked data unavailable');
    const info = `${player.championName || 'Unknown'} · ${laneName[lane]} · ${scores.creepScore || 0} CS · ${buildType(player)} · ${rank}`;
    return `<div class="lane-player ${isEnemy ? 'enemy-player' : 'ally-player'}"><img class="champion-mini ${frame}" src="${ref?.icon || ''}" title="${escapeHtml(detail)}" alt="${escapeHtml(player.championName || 'Champion')}"><div class="player-copy"><div class="player-name">${escapeHtml(player.summonerName || 'Unknown')}</div><div class="player-meta player-info" title="${escapeHtml(detail)}">${escapeHtml(info)}</div></div><div class="player-kda">${scores.kills || 0}/${scores.deaths || 0}/${scores.assists || 0}</div></div>`;
  };
  const enemyTeam = team === 'ORDER' ? 'CHAOS' : 'ORDER';
  const allyBuilds = teamBuildCounts(team);
  const enemyBuilds = teamBuildCounts(enemyTeam);
  text('ally-team-label', `${team === 'ORDER' ? 'Order' : 'Chaos'} · your team · AP ${allyBuilds.AP} / AD ${allyBuilds.AD}`);
  text('enemy-team-label', `${enemyTeam === 'ORDER' ? 'Order' : 'Chaos'} · enemy · AP ${enemyBuilds.AP} / AD ${enemyBuilds.AD}`);
  $('roster').innerHTML = players.length ? lanes.map((lane, index) => `<div class="lane-row"><div class="lane-label">${laneName[lane]}</div>${playerCard(playerForLane(team, lane), team, lane, index)}${playerCard(playerForLane(team === 'ORDER' ? 'CHAOS' : 'ORDER', lane), team === 'ORDER' ? 'CHAOS' : 'ORDER', lane, index)}</div>`).join('') : '<div class="empty">Waiting for live client data.</div>';

  const activePlayer = players.find((player) => player.summonerName === active.summonerName) || me;
  const itemList = activePlayer.items || [];
  $('items').innerHTML = itemList.length ? itemList.map((item) => { const ref = reference.items?.[String(item.itemID)]; return `<img class="item-icon" src="${ref?.icon || ''}" title="${escapeHtml(item.displayName || ref?.name || 'Item')}" alt="${escapeHtml(item.displayName || 'Item')}">`; }).join('') : '<span class="eyebrow">No item data</span>';
  const abilities = active.abilities || {};
  const spellNames = ['Passive', 'Q', 'W', 'E', 'R'];
  const dataDragonSpells = activeRef.spells || [];
  $('abilities').innerHTML = spellNames.map((key, index) => { const ability = abilities[key] || {}; const spell = key === 'Passive' ? activeRef.passive : dataDragonSpells[index - 1]; const name = ability.displayName || spell?.name || key; return `<div class="ability" title="${escapeHtml(spell?.description || spell?.tooltip || '')}"><div class="ability-key">${key}</div><div class="ability-name">${escapeHtml(name)}</div><div class="ability-level">${ability.abilityLevel ? 'level ' + ability.abilityLevel : 'passive'}</div></div>`; }).join('');
  const recommendations = Array.isArray(data.recommendations) ? data.recommendations : [];
  $('recommendations').innerHTML = recommendations.length ? recommendations.map((recommendation) => `<div class="recommendation"><img src="${recommendation.icon || ''}" alt=""><div><div class="recommendation-name">${escapeHtml(recommendation.name)}</div><div class="recommendation-reason">${escapeHtml(recommendation.reason)}</div></div></div>`).join('') : '<div class="empty">No counter-build signal yet.</div>';

  const events = data.events?.Events || [];
  text('event-count', `${events.length} events`);
  $('events-list').innerHTML = events.length ? events.slice(-8).reverse().map((event) => `<div class="event"><span class="event-name">${escapeHtml(event.EventName || 'Event')}${event.KillerName ? ` · ${escapeHtml(event.KillerName)}` : ''}${event.VictimName ? ` → ${escapeHtml(event.VictimName)}` : ''}</span><span class="event-time">${formatTime(event.EventTime)}</span></div>`).join('') : '<div class="empty">Events will appear here.</div>';
  const countEvent = (name) => events.filter((event) => event.EventName === name).length;
  text('turret-count', countEvent('TurretKilled'));
  text('dragon-count', countEvent('DragonKill'));
  text('inhibitor-count', countEvent('InhibKilled'));
  const result = events.find((event) => event.EventName === 'GameEnd');
  text('game-result', result?.Result || 'In progress');
  document.querySelectorAll('img').forEach((image) => {
    if (!image.getAttribute('src')) {
      image.src = ICON_FALLBACK;
      image.title = image.title || 'Icon metadata unavailable';
    }
  });
}

async function refresh() {
  if (state.loading) return;
  state.loading = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(state.endpoint, { cache: 'no-store', signal: controller.signal });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    if (!payload.gameData || !payload.activePlayer || !Array.isArray(payload.allPlayers) || !payload.allPlayers.length) throw new Error('No active game');
    state.demo = false;
    render(payload);
  } catch {
    state.demo = true;
    renderDemo();
    loadDemoIcons();
  } finally {
    clearTimeout(timeout);
    state.loading = false;
  }
}

function renderDemo() {
  render(demoData);
  text('session-status', 'Demo data');
  text('session-meta', 'No live game available. Automatically checking every 2 seconds.');
}

async function loadDemoIcons() {
  if (Date.now() < state.iconsRetryAt) return;
  state.iconsRetryAt = Date.now() + 60000;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch('/api/icons', { signal: controller.signal });
    if (response.ok) {
      demoData.reference = await response.json();
      state.iconsRetryAt = Date.now() + 600000;
      if (state.demo) renderDemo();
    }
  } catch { /* Local placeholders remain available while offline. */ }
  finally { clearTimeout(timeout); }
}
refresh();
setInterval(() => refresh(), 2000);
