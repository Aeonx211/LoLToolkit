from collections import Counter
from dataclasses import dataclass
from itertools import pairwise

from .parse import TEAM_NAMES, TEAMS, Frame, ParsedMatch, other_team

# Typical (kill participation, damage, gold, tower damage, epic-monster damage, survival) share of team totals by
# role; used to judge "vastly exceeds their role". Unlike damage/gold, KP isn't exclusive: several players can be
# credited on the same kill, so a role's KP is typically 45-65% rather than the ~20% you'd expect from an even
# split, and the column doesn't sum to 1 across the team. Survival is the complement of each player's share of the
# team's deaths -- (1 - deaths_i / team_deaths) / 4 -- so it also sums to ~1 across the team and averages ~0.20
# everywhere a player's odds of dying aren't role-skewed (which, empirically, they aren't much: see below).
#
# Calibrated 2026-09 from every stored 5v5 Summoner's Rift match in data/toolkit.db (576 games, 1152 role-samples
# per role after filtering remakes and games missing a `teamPosition`) -- mean share per role, i.e. exactly the
# number the module docstring used to ask for instead of a hand-guess. Tower and epic-monster (dragon/herald/
# baron/grubs/atakhan) damage are now tracked separately (previously bundled into one `objective_damage` field that
# over-credited whichever of the two dominated a given game -- see TOWER_WEIGHT/NEUTRAL_WEIGHT below). This mean-
# fit baseline pulls the "typical" line for every role close to where it actually sits, which also compresses the
# ratio scale versus the old hand-guessed baseline (see SHARE_CAP_RATIO and Thresholds.carry_ratio/carry_margin
# for the consequence: a merely-good game and a truly dominant one now sit closer together than they used to,
# which is *why* Carried needed a margin-based rule instead of one fixed cutoff).
ROLE_BASELINE = {
    "TOP": (0.353, 0.225, 0.200, 0.336, 0.070, 0.199),
    "JUNGLE": (0.481, 0.184, 0.214, 0.075, 0.660, 0.204),
    "MIDDLE": (0.435, 0.235, 0.203, 0.257, 0.070, 0.201),
    "BOTTOM": (0.482, 0.233, 0.229, 0.262, 0.128, 0.196),
    "UTILITY": (0.521, 0.124, 0.154, 0.069, 0.042, 0.199),
}
# Simple mean of the five role baselines above; used as a fallback for a missing/unknown position.
DEFAULT_BASELINE = (0.454, 0.200, 0.200, 0.200, 0.194, 0.200)

# How much tower damage share, and epic-monster (dragon/herald/baron/grubs/atakhan) damage share, count toward
# impact, next to the equal split KP/damage/gold already have (which still splits the remaining 1 - TOWER_WEIGHT -
# NEUTRAL_WEIGHT). Kept at the same combined 0.15 budget the old single OBJECTIVE_WEIGHT used (a backtest against
# stored games showed weights much above this start moving everyone's impact number, not just outliers like a
# low-fight, high-turret-damage game) but split unevenly: neutral objectives are a harder, more team-wide prize
# to take (needs vision, timing, a won fight against the enemy jungler/team) than poking a tower down, so a unit
# of neutral-damage share counts for 2x a unit of tower-damage share.
TOWER_WEIGHT = 0.05
NEUTRAL_WEIGHT = 0.10

# Bonus-only weight on how much better than their role's baseline survival share (see ROLE_BASELINE) a player
# did. Only ever adds to impact (a player who dies *more* than the role baseline gets no penalty, just no bonus) --
# a backtest showed a full plus/minus term would double-punish deaths that KP/damage/gold already price in (a
# death usually costs the dead player gold/damage/kp too), while a bonus-only term for genuinely low deaths moved
# the population mean by <0.3% at this weight, i.e. it nudges outliers (very clean games) without reshaping the
# rest of the distribution.
DEATH_WEIGHT = 0.08

# Bonus-only weight for junglers who take a large share of their jungle monster kills from the enemy's half of the
# map (invaded/stolen camps) rather than farming their own. Real case: an enemy jungler who invaded early, then
# repeatedly took our camps and used the resulting lead to gank, scored impact_ratio 0.829 under kp/damage/gold/
# tower/neutral alone -- his neutral-damage share was huge (.822) but that's farming volume, not *whose* camps he
# was farming, and champion-damage share was low since he wasn't a laner. `totalEnemyJungleMinionsKilled` /
# `totalAllyJungleMinionsKilled` (present on every stored participant) let us isolate that directly. Backtested
# against 1245 stored jungle role-samples: mean enemy-jungle share is 0.096 (median 0.077, p90 0.211); the flagged
# game's jungler sat at 0.556, a ~5.8x outlier. At this weight/baseline the bonus is negligible (<0.005) for every
# other sampled game and moves only that one outlier from 0.829 to ~0.96, same "moves outliers not the population"
# bar as DEATH_WEIGHT.
INVASION_WEIGHT = 0.08
INVASION_BASELINE_SHARE = 0.10

# One-time bonus for a jungler who gets a kill or assist before EARLY_INVADE_WINDOW_S on the enemy half of the map
# -- an early invade, not just later camp theft. Flat and small because early-game kills are rare by construction
# (few kills happen in the first couple minutes at all), so this fires selectively.
EARLY_INVADE_BONUS = 0.03
EARLY_INVADE_WINDOW_S = 150.0

# Rough diagonal split of Summoner's Rift: team 100 spawns near (0, 0), team 200 near (MAP_HALF*2, MAP_HALF*2), so
# x + y above this line is closer to team 200's base and below it is closer to team 100's -- a coarse "whose half"
# check (doesn't account for river/objective camps sitting near the line), used for the early-invade flag and the
# early-invasion share below.
MAP_HALF = 14820.0

# Window used to compute the "first N minutes" enemy-jungle share for the Invader tag (see
# early_invasion_share() and archetypes.Thresholds.invader_share) -- deliberately the same idea as
# EARLY_INVADE_WINDOW_S but a bit wider, since a tag meant to say "invaded early" shouldn't fire off camp theft
# that only picked up once the enemy jungler was already dead for the game.
EARLY_INVASION_WINDOW_S = 300.0

# Typical share of team damage taken (Riot's own challenges.damageTakenOnTeamPercentage) by role. Calibrated
# 2026-09 from the same 655-game stored sample as ROLE_BASELINE (1308 role-samples/role). Frontliners (top/jungle)
# soak roughly 40% more of the team's incoming damage than backline roles, and until now nothing in weighted_impact
# credited that at all -- a tanky bruiser/jungler who peels for the team and eats cooldowns gets zero recognition
# from kp/damage/gold/objective shares alone, which all reward *dealing* damage or securing kills/objectives, not
# *absorbing* punishment.
DAMAGE_TAKEN_BASELINE = {
    "TOP": 0.247,
    "JUNGLE": 0.235,
    "MIDDLE": 0.185,
    "BOTTOM": 0.166,
    "UTILITY": 0.166,
}
DEFAULT_DAMAGE_TAKEN_BASELINE = 0.200

# Bonus-only weight for damage-taken share above role baseline. Gated by survival (see tank_bonus()): soaking a lot
# of damage while also dying a lot isn't the same skill as tanking it and living, so the raw excess is scaled down
# toward 0 the further the player's survival share sits below their role's baseline (a player who dies more than
# typical for their role gets little or none of this bonus, never a penalty beyond that).
TANK_WEIGHT = 0.06

# (p90, p95-p90) of Riot's challenges.soloKills by role, same 655-game sample -- the floor is the role's 90th
# percentile, so only the top ~10% of games get anything at all, reaching full weight at p95. Two earlier, looser
# cuts of this (mean/p90-mean, then p75/p95-p75) still moved the whole population's impact_ratio mean by 4.3% and
# 3.0% respectively (see ANALYSIS_VERSION=10/11 backtests) -- not the "moves outliers, not the population" bar
# SHARE_CAP_RATIO/DEATH_WEIGHT were held to. Span is floored at 1 for roles (bottom/utility) where p90 and p95
# land on the same integer.
SOLO_KILL_BASELINE = {
    "TOP": (6, 2),
    "JUNGLE": (4, 1),
    "MIDDLE": (6, 1),
    "BOTTOM": (3, 1),
    "UTILITY": (1, 1),
}
DEFAULT_SOLO_KILL_BASELINE = (4, 1)
SOLO_KILL_WEIGHT = 0.05

# Bonus for a personal multi-kill (Riot's own largestMultiKill: 1 = none, 2 = double, ... 5 = penta) -- a discrete,
# officially-scored signal for "picked off several enemies in one burst" that's independent of role and doesn't
# need any position/lane heuristics. No entry for a double kill: backtesting the full stored sample showed doubles
# happen in 29% of player-games -- not an outlier at all -- and gave that bonus alone ~4.4% population-wide drift
# on impact_ratio (see ANALYSIS_VERSION=10 backtest note on SOLO_KILL_BASELINE). Triple+ is rare enough to keep
# (7.5% triple, 1.1% quadra, 0.1% penta combined), so the bonus starts there.
MULTIKILL_BONUS = {3: 0.05, 4: 0.09, 5: 0.15}

# Cap on how far any single share component (kp, damage, gold, tower, neutral) is allowed to count above its role
# baseline, applied before weighting. Without it, one lumpy component -- a support's damage share on a poke champ,
# or a jungler's tower-damage share from backdooring a fight they weren't otherwise in -- can swing the whole
# ratio on its own (the Vel'Koz/Brand-support overrating this module used to flag as a TODO, and the same failure
# mode showing up from the objective-damage angle in a support who out-pokes their objective-damage baseline by
# 2-3x while contributing little else). A backtest across stored games shows 2.0x moves only the outlier tail
# (max player-game ratio drops from 2.17 to 1.94, and the share of player-games at/above the old carry_ratio=1.52
# drops ~17%) while leaving the bulk of the distribution (every role's mean/median) unchanged to three decimals.
SHARE_CAP_RATIO = 2.0


def lead_for(value, team):
    """Convert a blue-minus-red value into `team`'s lead."""
    return value if team == 100 else -value


def diff_series(pm: ParsedMatch, metric):
    return [(f.t, pm.team_total(f, metric, 100) - pm.team_total(f, metric, 200)) for f in pm.frames]


def value_at(series, t):
    if t <= series[0][0]:
        return series[0][1]
    for (t0, v0), (t1, v1) in pairwise(series):
        if t <= t1:
            return v1 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return series[-1][1]


def lead_peaks(series):
    """Largest lead each team held and when (earliest time it was reached)."""
    peaks = {}
    for team in TEAMS:
        best_t, best = series[0][0], 0
        for t, v in series:
            if lead_for(v, team) > best:
                best_t, best = t, lead_for(v, team)
        peaks[team] = (best, best_t)
    return peaks


def lead_flips(series, noise=500):
    flips, prev = [], 0
    for t, v in series:
        if abs(v) < noise:
            continue
        sign = 1 if v > 0 else -1
        if prev and sign != prev:
            flips.append(t)
        prev = sign
    return flips


def frame_at_or_before(pm: ParsedMatch, t):
    best = pm.frames[0]
    for f in pm.frames:
        if f.t <= t:
            best = f
    return best


def _share(values, pid, team_pids):
    total = sum(values.get(p, 0) for p in team_pids)
    return values.get(pid, 0) / total if total > 0 else 0.0


def _kp_share(pm: ParsedMatch, team, pid, end_kills, start_kills, end_kp, start_kp):
    """Player's (kills+assists) in the window, over the team's actual kills in that window (not a plain _share:
    several players can be credited on the same kill, so this doesn't sum to 1 across the team)."""
    team_kills = sum(end_kills.get(p, 0) - start_kills.get(p, 0) for p in team)
    if team_kills <= 0:
        return 0.0
    return (end_kp.get(pid, 0) - start_kp.get(pid, 0)) / team_kills


def shares_between(pm: ParsedMatch, f0: Frame | None, f1: Frame, pid):
    """(kill participation, damage, gold) share of the player's team gains between two frames (f0=None means
    game start)."""
    team = pm.team_pids(pm.players[pid].team_id)
    kp = _kp_share(pm, team, pid, f1.kills, f0.kills if f0 else {}, f1.kp, f0.kp if f0 else {})
    out = [kp]
    for metric in ("damage", "gold"):
        end = f1.get(metric)
        start = f0.get(metric) if f0 else {}
        deltas = {p: end.get(p, 0) - start.get(p, 0) for p in team}
        out.append(_share(deltas, pid, team))
    return tuple(out)


def impact(shares):
    return sum(shares) / len(shares)


def _capped(value, baseline_value, cap_ratio):
    """Ceiling a share at `cap_ratio` times its role baseline, so one lumpy component can't swing the whole ratio
    on its own. Never lowers a value that's already below baseline."""
    if cap_ratio is None or baseline_value <= 0:
        return value
    return min(value, cap_ratio * baseline_value)


def weighted_impact(shares, baseline=None, tower_weight=None, neutral_weight=None, death_weight=None,
                    cap_ratio=None):
    """Like impact(), but for a (kp, damage, gold, tower damage, neutral damage, survival) tuple: the first three
    split the remaining weight evenly (same as impact() alone), tower/neutral damage count for
    `tower_weight`/`neutral_weight` on top, and a player who survives more than their role baseline gets a
    bonus-only addition worth `death_weight` times how far above baseline they are (never a penalty for dying
    more than baseline -- see DEATH_WEIGHT).

    `baseline` is the role's ROLE_BASELINE/DEFAULT_BASELINE tuple, used to cap each share and as the survival
    reference point for the death bonus; omitting it (as when scoring the baseline itself) disables both the cap
    and the bonus, since there's nothing to compare against."""
    wt = TOWER_WEIGHT if tower_weight is None else tower_weight
    wn = NEUTRAL_WEIGHT if neutral_weight is None else neutral_weight
    wd = DEATH_WEIGHT if death_weight is None else death_weight
    cap = SHARE_CAP_RATIO if cap_ratio is None else cap_ratio
    kp, damage, gold, tower, neutral, survival = shares
    if baseline is not None:
        b_kp, b_damage, b_gold, b_tower, b_neutral, b_survival = baseline
        kp, damage, gold = _capped(kp, b_kp, cap), _capped(damage, b_damage, cap), _capped(gold, b_gold, cap)
        tower, neutral = _capped(tower, b_tower, cap), _capped(neutral, b_neutral, cap)
    else:
        b_survival = survival
    base = (1 - wt - wn) * impact((kp, damage, gold)) + wt * tower + wn * neutral
    return base + wd * max(0.0, survival - b_survival)


def final_shares(pm: ParsedMatch, pid):
    """(kill participation, damage, gold, tower damage, neutral/epic-monster damage, survival) share of the
    player's team totals over the whole game. Survival is the complement of the player's share of the team's
    deaths -- (1 - deaths_i / team_deaths) / 4 -- so, like the others, it sums to ~1 across the team."""
    player = pm.players[pid]
    team = [pm.players[p] for p in pm.team_pids(player.team_id)]
    team_kills = sum(p.kills for p in team)
    kp = (player.kills + player.assists) / team_kills if team_kills else 0.0
    out = [kp]
    for attr in ("damage", "gold", "tower_damage", "neutral_damage"):
        total = sum(getattr(p, attr) for p in team)
        out.append(getattr(player, attr) / total if total else 0.0)
    team_deaths = sum(p.deaths for p in team)
    out.append((1 - player.deaths / team_deaths) / 4 if team_deaths else 0.2)
    return tuple(out)


def invasion_share(player):
    """Share of a jungler's jungle-monster kills taken from the enemy's half of the map. 0 for non-junglers or
    junglers with no recorded jungle CS."""
    if player.position != "JUNGLE":
        return 0.0
    total = player.ally_jg + player.enemy_jg
    return player.enemy_jg / total if total > 0 else 0.0


def invasion_bonus(player):
    """Bonus-only addition (see INVASION_WEIGHT) for a jungler whose enemy-jungle share clears the population
    baseline -- farming your own camps earns nothing extra; taking the enemy's does."""
    share = invasion_share(player)
    if share <= INVASION_BASELINE_SHARE:
        return 0.0
    return INVASION_WEIGHT * (share - INVASION_BASELINE_SHARE) / (1 - INVASION_BASELINE_SHARE)


def early_invasion_share(pm: ParsedMatch, pid, window_s=None):
    """Share of a jungler's jungle-monster kills taken from the enemy's half of the map within the first
    `window_s` (default EARLY_INVASION_WINDOW_S) seconds -- unlike invasion_share(), which is a whole-game total,
    this reconstructs the split from per-minute timeline snapshots (cumulative `jungle` CS + `positions`), so it
    can say whether the theft actually happened *early* rather than just piling up late once the enemy jungler was
    already out of the game."""
    window_s = EARLY_INVASION_WINDOW_S if window_s is None else window_s
    player = pm.players[pid]
    if player.position != "JUNGLE":
        return 0.0
    on_enemy_half = (lambda x, y: x + y > MAP_HALF) if player.team_id == 100 else (lambda x, y: x + y < MAP_HALF)
    enemy_cs, total_cs, prev = 0, 0, None
    for f in pm.frames:
        if f.t > window_s:
            break
        if prev is not None:
            delta = f.jungle.get(pid, 0) - prev.jungle.get(pid, 0)
            if delta > 0:
                total_cs += delta
                pos = f.positions.get(pid) or prev.positions.get(pid)
                if pos and on_enemy_half(*pos):
                    enemy_cs += delta
        prev = f
    return enemy_cs / total_cs if total_cs > 0 else 0.0


def multikill_bonus(player):
    return MULTIKILL_BONUS.get(player.largest_multi_kill, 0.0)


def tank_bonus(player, survival_share, baseline_survival):
    """Bonus-only credit for damage-taken share above role baseline, scaled down (never up) by how far the
    player's survival share sits below their role's baseline -- see TANK_WEIGHT."""
    baseline_dt = DAMAGE_TAKEN_BASELINE.get(player.position, DEFAULT_DAMAGE_TAKEN_BASELINE)
    excess = max(0.0, player.damage_taken_pct - baseline_dt)
    if excess <= 0:
        return 0.0
    gate = min(1.0, survival_share / baseline_survival) if baseline_survival > 0 else 1.0
    return TANK_WEIGHT * (excess / (1 - baseline_dt)) * gate


def solo_kill_bonus(player):
    floor, span = SOLO_KILL_BASELINE.get(player.position, DEFAULT_SOLO_KILL_BASELINE)
    if span <= 0:
        return 0.0
    excess = max(0.0, player.solo_kills - floor)
    return SOLO_KILL_WEIGHT * min(1.0, excess / span)


def early_invade_kill(pm: ParsedMatch, pid):
    """Whether this jungler got a kill or assist before EARLY_INVADE_WINDOW_S on the enemy half of the map."""
    player = pm.players[pid]
    if player.position != "JUNGLE":
        return False
    on_enemy_half = (lambda x, y: x + y > MAP_HALF) if player.team_id == 100 else (lambda x, y: x + y < MAP_HALF)
    for k in pm.kills:
        if k.t > EARLY_INVADE_WINDOW_S or not k.position:
            continue
        if pid == k.killer or pid in k.assists:
            if on_enemy_half(*k.position):
                return True
    return False


def rolling_impact(pm: ParsedMatch, window_s):
    series = {pid: [] for pid in pm.players}
    for i, frame in enumerate(pm.frames):
        base = frame_at_or_before(pm, frame.t - window_s) if frame.t - window_s > 0 else None
        for pid in pm.players:
            series[pid].append(round(impact(shares_between(pm, base, frame, pid)), 3) if i else 0.0)
    return series


def player_impacts(pm: ParsedMatch):
    rows = []
    for pid, p in sorted(pm.players.items()):
        shares = final_shares(pm, pid)
        role_baseline = ROLE_BASELINE.get(p.position, DEFAULT_BASELINE)
        baseline = weighted_impact(role_baseline)
        value = weighted_impact(shares, role_baseline)
        early_invade = early_invade_kill(pm, pid)
        value += (invasion_bonus(p) + (EARLY_INVADE_BONUS if early_invade else 0.0) + multikill_bonus(p)
                  + tank_bonus(p, shares[5], role_baseline[5]) + solo_kill_bonus(p))
        rows.append({
            "participant_id": pid,
            "puuid": p.puuid,
            "riot_id": p.riot_id,
            "team_id": p.team_id,
            "champion": p.champion,
            "position": p.position,
            "win": p.win,
            "kda": [p.kills, p.deaths, p.assists],
            "items": p.items,
            "shares": {"kp": round(shares[0], 3), "damage": round(shares[1], 3), "gold": round(shares[2], 3),
                       "tower": round(shares[3], 3), "neutral": round(shares[4], 3),
                       "survival": round(shares[5], 3)},
            "invasion_share": round(invasion_share(p), 3),
            "early_invasion_share": round(early_invasion_share(pm, pid), 3),
            "early_invade": early_invade,
            "largest_multi_kill": p.largest_multi_kill,
            "damage_taken_pct": round(p.damage_taken_pct, 3),
            "solo_kills": p.solo_kills,
            "impact": round(value, 3),
            "impact_ratio": round(value / baseline, 3),
            "carried": False,
        })
    return rows


@dataclass
class Moment:
    start: float
    end: float
    kills: dict[int, int]
    objectives: list
    gold_swing: float

    @property
    def beneficiary(self):
        return 100 if self.gold_swing >= 0 else 200

    def to_dict(self):
        return {
            "start": self.start,
            "end": self.end,
            "kills": {str(k): v for k, v in self.kills.items()},
            "objectives": [{"t": o.t, "team": o.team, "kind": o.kind, "detail": o.detail} for o in self.objectives],
            "gold_swing": round(self.gold_swing),
            "beneficiary": self.beneficiary,
        }


def key_moments(pm: ParsedMatch, gold_series, gap_s):
    """Cluster kills and objectives that happen close together, and measure the gold swing across each cluster."""
    events = sorted([(k.t, k) for k in pm.kills] + [(o.t, o) for o in pm.objectives], key=lambda e: e[0])
    clusters = []
    for ev in events:
        if clusters and ev[0] - clusters[-1][-1][0] <= gap_s:
            clusters[-1].append(ev)
        else:
            clusters.append([ev])
    moments = []
    for cluster in clusters:
        start, end = cluster[0][0], cluster[-1][0]
        kills = {100: 0, 200: 0}
        objectives = []
        for _, ev in cluster:
            if hasattr(ev, "victim"):
                kills[ev.team] += 1
            else:
                objectives.append(ev)
        swing = value_at(gold_series, min(end + 45, pm.duration_s)) - value_at(gold_series, max(start - 15, 0))
        moments.append(Moment(start, end, kills, objectives, swing))
    return moments


def mmss(seconds):
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def fmt_gold(value):
    value = abs(value)
    return f"{value / 1000:.1f}k" if value >= 1000 else str(int(value))


def describe_moment(m: dict):
    team = m["beneficiary"]
    ours, theirs = m["kills"][str(team)], m["kills"][str(other_team(team))]
    phrases = []
    if ours + theirs >= 2:
        phrases.append(f"won a {ours}-{theirs} fight" if ours > theirs else f"traded kills {ours}-{theirs}")
    elif ours == 1:
        phrases.append("got a pick")
    taken = Counter(o["kind"] for o in m["objectives"] if o["team"] == team)
    if taken:
        names = [f"{n} {k}s" if n > 1 else k for k, n in taken.items()]
        phrases.append("took " + ", ".join(names))
    action = " and ".join(phrases) or "swung the gold"
    return f"{TEAM_NAMES[team]} {action} at {mmss(m['start'])} ({fmt_gold(m['gold_swing'])} swing)"
