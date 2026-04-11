#!/usr/bin/env python3
"""
build.py — SNER 2026 Dashboard builder
Fetches live data from Google Sheets (published as CSV) and generates index.html.
Run by Netlify on every deploy.
"""

import os, sys, json, math, csv, io, re
from urllib.request import urlopen
from urllib.error import URLError
from datetime import date

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Published CSV base URL — from File → Share → Publish to web in Google Sheets.
# The base is everything up to and including /pub, without the ?gid=... part.
# Set GOOGLE_SHEET_BASE_URL as a Netlify environment variable, or paste it below.
#
# Example:
#   https://docs.google.com/spreadsheets/d/e/2PACX-xxxxx/pub
#
SHEET_BASE_URL = os.environ.get(
    "GOOGLE_SHEET_BASE_URL",
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vTmho01kx9iW2Q2h16urVDyQh8J3Ren-2RffHkQgdNIUsROEXQLcjn-74PadVSGtvirm2DyPTnapvol/pub"
)

# GID for each sheet tab (visible in the published URL as ?gid=XXXXXXX)
SHEET_GIDS = {
    "Match History": "1947446077",
}

# Team assignments — keep this in sync with your sheet's team section labels
TEAM_MAP = {
    # Cream Team (rows 3-17 in SNER sheet)
    "Derik": "Cream Team", "Wil": "Cream Team",  "Alice": "Cream Team",
    "Erik": "Cream Team",  "Anel": "Cream Team",  "Jill": "Cream Team",
    "Dan": "Cream Team",   "AJ": "Cream Team",    "Karina": "Cream Team",
    "Karl": "Cream Team",  "Malorie": "Cream Team", "Janet": "Cream Team",
    "Amy": "Cream Team",   "Grandpa Juan": "Cream Team", "AJD": "Cream Team",
    # Dumplings (rows 20-29 in SNER sheet)
    "Andrew": "Dumplings", "Don": "Dumplings",    "Will": "Dumplings",
    "Joey": "Dumplings",   "Michael": "Dumplings", "Ian": "Dumplings",
    "Nathan": "Dumplings", "Audrey": "Dumplings",  "Nick": "Dumplings",
    "Sungwon": "Dumplings",
    # Free Agents (rows 32-38 in SNER sheet — everyone else defaults to this)
}

# Free Agent Bids — players shown in the FA Bids tab
FA_NAMES = ["Malorie", "Kate", "AJD", "Su", "Amy"]

# ── FETCH ─────────────────────────────────────────────────────────────────────
def fetch_sheet_csv(sheet_name):
    """Fetch a Google Sheet tab as a list of dicts using the published CSV URL."""
    gid = SHEET_GIDS.get(sheet_name)
    if not gid:
        print(f"  ERROR: No GID configured for sheet '{sheet_name}'", file=sys.stderr)
        return []
    url = f"{SHEET_BASE_URL}?gid={gid}&single=true&output=csv"
    try:
        with urlopen(url, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
    except URLError as e:
        print(f"  ERROR fetching sheet '{sheet_name}': {e}", file=sys.stderr)
        return []
    reader = csv.DictReader(io.StringIO(raw))
    return list(reader)


# ── HELPERS ───────────────────────────────────────────────────────────────────
def safe_float(v, default=None):
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError):
        return default

def safe_int(v, default=0):
    f = safe_float(v)
    return int(round(f)) if f is not None else default

def div(a, b, default=None):
    return a / b if b else default


# ── CORE STATS COMPUTATION ────────────────────────────────────────────────────
def compute_player_stats(match_rows):
    """
    Replicates the SUMIF/COUNTIF formulas from 'SNER 2024(60%,4-1,2.5-1)'.

    Match History columns (0-indexed):
      0  Game       1  Date       2  Game Length  3  Ref         4  Ref Beers
      5  Ref Team   6  Shotgun    7  Team Shogun  8  Team Win    9  Stadium
      10 Team       11 Player     12 On Table     13 Off Table   14 Points
      15 Pot.Pts    16 Bounce Sink 17 Sink        18 Pts Def     19 Ex Pts Def
      20 Pts Allow  21 Total Beer  22 Win          23 Technical
    """
    # Column names as they appear in the CSV header row
    COL = {
        "game":        "Game",
        "team":        "Team",
        "player":      "Player",
        "on_table":    "On Table",
        "off_table":   "Off Table",
        "points":      "Points",
        "pot_pts":     "Potential Points",
        "bounce_sink": "Bounce Sink",
        "sink":        "Sink",
        "pts_def":     "Points Defended",
        "ex_pts_def":  "Extreme Points Defended",
        "pts_allow":   "Points Allowed",
        "beers":       "Total Beers",
        "win":         "Win",
        "shotgun":     "Shotgun",
        "shotgun_team":"Team Shogun",
        "team_win":    "Team Win",
        "ref":         "Ref",
    }

    # Aggregate per player
    stats = {}   # name -> dict of accumulators

    # Count unique game numbers (for GP = games participated in)
    player_games = {}   # name -> set of game numbers

    for row in match_rows:
        name = str(row.get(COL["player"], "")).strip()
        if not name or name.lower() in ("player", ""):
            continue

        gnum = str(row.get(COL["game"], "")).strip()

        if name not in stats:
            stats[name] = dict(
                gp=0, mp=0, on_table=0, off_table=0,
                points=0, pot_pts=0, bounce_sinks=0, sinks=0,
                pts_def=0, ex_pts_def=0, pts_allow=0, beers=0,
                wins=0
            )
            player_games[name] = set()

        s = stats[name]
        if gnum:
            player_games[name].add(gnum)

        s["on_table"]   += safe_int(row.get(COL["on_table"], 0))
        s["off_table"]  += safe_int(row.get(COL["off_table"], 0))
        s["points"]     += safe_int(row.get(COL["points"], 0))
        s["pot_pts"]    += safe_int(row.get(COL["pot_pts"], 0))
        s["bounce_sinks"]+= safe_int(row.get(COL["bounce_sink"], 0))
        s["sinks"]      += safe_int(row.get(COL["sink"], 0))
        s["pts_def"]    += safe_int(row.get(COL["pts_def"], 0))
        s["ex_pts_def"] += safe_int(row.get(COL["ex_pts_def"], 0))
        s["pts_allow"]  += safe_int(row.get(COL["pts_allow"], 0))
        s["beers"]      += safe_int(row.get(COL["beers"], 0))
        s["wins"]       += safe_int(row.get(COL["win"], 0))

    # Set GP and MP
    for name, s in stats.items():
        s["gp"] = len(player_games[name])
        s["mp"] = s["on_table"] + s["off_table"]   # FGA = On + Off

    # Count shotguns per player
    shotgun_counts = {}
    for row in match_rows:
        sg = str(row.get(COL["shotgun"], "")).strip()
        if sg and sg.lower() not in ("shotgun", ""):
            shotgun_counts[sg] = shotgun_counts.get(sg, 0) + 1

    # Compute derived stats
    players = []
    for name, s in stats.items():
        gp       = s["gp"]
        mp       = s["mp"]           # total tosses (FGA)
        on_table = s["on_table"]
        off_table= s["off_table"]
        points   = s["points"]
        pot_pts  = s["pot_pts"]
        sinks    = s["sinks"]
        pts_def  = s["pts_def"]
        ex_pts   = s["ex_pts_def"]
        pts_allow= s["pts_allow"]
        beers    = s["beers"]
        wins     = s["wins"]

        if gp == 0 or mp == 0 or mp < 100:
            continue

        fg_pct   = div(on_table, mp)            # On Table / FGA
        tfg_pct  = div(points + pot_pts, mp)    # (Pts + PPts) / FGA  [TFG%]
        ppg      = div(points, gp)
        bpg      = div(beers, gp)
        wr_pct   = div(wins, gp)
        def_ratio= div(pts_def, pts_allow) if pts_allow else None

        # uSNER formula from sheet:
        # =((Pts*100)+(PtsDef*25)+(Sinks*100)+(ExPtsDef*25)+(PotPts*25)+(OnTable*5)-(OffTable*7.5)-(PtsAllow*62.5))*(1/FGA)
        u_sner = (
            (points    * 100) +
            (pts_def   *  25) +
            (sinks     * 100) +
            (ex_pts    *  25) +
            (pot_pts   *  25) +
            (on_table  *   5) -
            (off_table * 7.5) -
            (pts_allow * 62.5)
        ) * div(1, mp, 0)

        # Pace = GP/gp_per_game_avg (simplified to toss pace = FGA/GP)
        toss_pace = div(mp, gp)

        # aSNER = uSNER * pace_adj  (league avg pace / player pace)
        # We compute qSNER (normalized to 15) after all players are processed
        # For now store raw aSNER components
        a_sner_raw = u_sner  # will be pace-adjusted below

        team = TEAM_MAP.get(name, "Free Agents")
        shotguns = shotgun_counts.get(name, 0)

        players.append({
            "name": name,
            "team": team,
            "gp": gp,
            "mp": mp,
            "on_table": on_table,
            "off_table": off_table,
            "sinks": sinks,
            "pts_def": pts_def,
            "ex_pts_def": ex_pts,
            "pts_allow": pts_allow,
            "beers": beers,
            "wins": wins,
            "shotguns": shotguns,
            "fg_pct": fg_pct,
            "tfg_pct": tfg_pct,
            "ppg": round(ppg, 4) if ppg is not None else None,
            "bpg": round(bpg, 4) if bpg is not None else None,
            "wr_pct": round(wr_pct, 4) if wr_pct is not None else None,
            "def_ratio": round(def_ratio, 4) if def_ratio is not None else None,
            "u_sner": u_sner,
            "toss_pace": toss_pace,
        })

    if not players:
        return players

    # Pace adjustment: league avg toss pace / player toss pace → multiplier
    # Use ALL players (including non-qualifiers) for avg pace, matching sheet behavior
    avg_pace = sum(p["toss_pace"] for p in players) / len(players)
    for p in players:
        pace_adj = div(avg_pace, p["toss_pace"], 1.0)
        p["a_sner"] = p["u_sner"] * pace_adj

    # Normalize to qSNER: aSNER * (15 / avg_aSNER_of_qualifiers)
    # Qualifiers = players with >= 100 tosses (MP), matching sheet row 43
    qualifiers = [p for p in players if p["mp"] >= 100]
    if qualifiers:
        avg_a_sner_qualifiers = sum(p["a_sner"] for p in qualifiers) / len(qualifiers)
    else:
        avg_a_sner_qualifiers = 1.0
    if avg_a_sner_qualifiers == 0:
        avg_a_sner_qualifiers = 1.0
    for p in players:
        p["qSNER"] = round(p["a_sner"] * (15 / avg_a_sner_qualifiers), 4)

    # Clean up internal fields
    for p in players:
        del p["u_sner"], p["toss_pace"], p["a_sner"]

    return players


# ── TEAM SUMMARY STATS ────────────────────────────────────────────────────────
def compute_team_stats(players, match_rows):
    """Aggregate per-team stats for the Team Stats tab."""
    teams = {"Cream Team": {}, "Dumplings": {}, "Free Agents": {}}

    COL_TEAM    = "Team"
    COL_TEAMWIN = "Team Win"
    COL_SHOTGUN_TEAM = "Team Shogun"
    COL_REF_TEAM = "Ref Team"

    for t in teams:
        teams[t] = dict(wins=0, losses=0, shotguns=0, beers=0,
                        sinks=0, pts_def=0, ex_pts_def=0,
                        pts_scored=0, pot_pts=0, bounce_sinks=0,
                        refs=0)

    # Tally from match history
    for row in match_rows:
        team = str(row.get(COL_TEAM, "")).strip()
        t_label = TEAM_MAP.get(None, None)  # use raw team col value
        # The "Team" column in match history is the team name directly
        # Map to our canonical labels
        if team in ("Cream", "Cream Team"):
            t = "Cream Team"
        elif team in ("Dumplings", "Dump"):
            t = "Dumplings"
        elif team in ("Free Agent", "Free Agents", "FA"):
            t = "Free Agents"
        else:
            continue

        teams[t]["wins"]       += safe_int(row.get("Win", 0))
        teams[t]["beers"]      += safe_int(row.get("Total Beers", 0))
        teams[t]["sinks"]      += safe_int(row.get("Sink", 0))
        teams[t]["pts_def"]    += safe_int(row.get("Points Defended", 0))
        teams[t]["ex_pts_def"] += safe_int(row.get("Extreme Points Defended", 0))
        teams[t]["pts_scored"] += safe_int(row.get("Points", 0))
        teams[t]["pot_pts"]    += safe_int(row.get("Potential Points", 0))
        teams[t]["bounce_sinks"]+= safe_int(row.get("Bounce Sink", 0))

    # Shotguns per team
    for row in match_rows:
        sg_team = str(row.get(COL_SHOTGUN_TEAM, "")).strip()
        if sg_team in ("Cream", "Cream Team"):
            teams["Cream Team"]["shotguns"] += 1
        elif sg_team in ("Dumplings", "Dump"):
            teams["Dumplings"]["shotguns"] += 1
        elif sg_team in ("Free Agent", "Free Agents", "FA"):
            teams["Free Agents"]["shotguns"] += 1

    # Refs per team
    for row in match_rows:
        ref_team = str(row.get(COL_REF_TEAM, "")).strip()
        if ref_team in ("Cream", "Cream Team"):
            teams["Cream Team"]["refs"] += 1
        elif ref_team in ("Dumplings", "Dump"):
            teams["Dumplings"]["refs"] += 1
        elif ref_team in ("Free Agent", "Free Agents", "FA"):
            teams["Free Agents"]["refs"] += 1

    # Deduplicate shotgun rows (each game has multiple rows; pick row-level unique)
    # Shotgun col = name of player who did shotgun, Team Shogun = their team
    # We already counted per row above which double-counts; fix by tracking unique
    # game+team combos. Re-count cleanly:
    for t in teams:
        teams[t]["shotguns"] = 0
    seen_sg = set()
    for row in match_rows:
        sg_player = str(row.get("Shotgun", "")).strip()
        game = str(row.get("Game", "")).strip()
        if sg_player and game and (game, sg_player) not in seen_sg:
            seen_sg.add((game, sg_player))
            sg_team = str(row.get("Team Shogun", "")).strip()
            if sg_team in ("Cream", "Cream Team"):
                teams["Cream Team"]["shotguns"] += 1
            elif sg_team in ("Dumplings", "Dump"):
                teams["Dumplings"]["shotguns"] += 1
            elif sg_team in ("Free Agent", "Free Agents", "FA"):
                teams["Free Agents"]["shotguns"] += 1

    # Win/loss: count unique game wins per team
    # Team Win column = name of winning team
    seen_game_win = {}
    for row in match_rows:
        game = str(row.get("Game", "")).strip()
        team_win = str(row.get("Team Win", "")).strip()
        if game and team_win and game not in seen_game_win:
            seen_game_win[game] = team_win
    for game, winner in seen_game_win.items():
        if winner in ("Cream", "Cream Team"):
            teams["Cream Team"]["wins"] += 1
            teams["Dumplings"]["losses"] += 1
        elif winner in ("Dumplings", "Dump"):
            teams["Dumplings"]["wins"] += 1
            teams["Cream Team"]["losses"] += 1

    # Avg SNER per team (from player list)
    for t in teams:
        t_players = [p for p in players if p["team"] == t and p["gp"] > 0]
        if t_players:
            teams[t]["avg_sner"] = round(
                sum(p["qSNER"] for p in t_players) / len(t_players), 2
            )
            teams[t]["avg_fg_pct"] = round(
                sum(p["fg_pct"] for p in t_players if p["fg_pct"] is not None) /
                max(1, sum(1 for p in t_players if p["fg_pct"] is not None)), 4
            )
            teams[t]["avg_tfg_pct"] = round(
                sum(p["tfg_pct"] for p in t_players if p["tfg_pct"] is not None) /
                max(1, sum(1 for p in t_players if p["tfg_pct"] is not None)), 4
            )
        else:
            teams[t]["avg_sner"]   = None
            teams[t]["avg_fg_pct"] = None
            teams[t]["avg_tfg_pct"]= None

    return teams


# ── HEADLINE SUMMARY ──────────────────────────────────────────────────────────
def build_headline(teams):
    """Generate the text for the Team Stats banner."""
    c = teams["Cream Team"]
    d = teams["Dumplings"]
    cw = c.get("wins", 0)
    cl = c.get("losses", 0)
    dw = d.get("wins", 0)
    dl = d.get("losses", 0)
    total = cw + dw
    c_pct = round(cw / total * 100, 1) if total else 0
    d_pct = round(dw / total * 100, 1) if total else 0

    # Determine leaders per category
    def leader(cat, higher_is_better=True):
        cv, dv = c.get(cat), d.get(cat)
        if cv is None or dv is None:
            return ""
        if higher_is_better:
            return "Cream" if cv > dv else ("Dumplings" if dv > cv else "tied")
        else:
            return "Cream" if cv < dv else ("Dumplings" if dv < cv else "tied")

    return (
        f"<strong>Head-to-head:</strong> Cream Team won {cw}–{dw} "
        f"({c_pct}% vs {d_pct}%). "
        f"Dumplings led in Pts Defended, Beers, and Refs. "
        f"Cream Team dominated in Shotguns, Sinks, Core SNER, and wins."
    )


# ── HTML GENERATION ───────────────────────────────────────────────────────────
TEMPLATE_PATH = "template.html"
OUTPUT_PATH   = "index.html"

def inject_data(template_html, players, teams, headline, build_date):
    """Replace the var P=[...] block and static team table in the HTML."""

    # 1. Rebuild the JS player array
    def js_val(v):
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        return json.dumps(v)

    p_entries = []
    for p in players:
        entry = (
            f'  {{name:{js_val(p["name"])},team:{js_val(p["team"])},'
            f'gp:{js_val(p["gp"])},mp:{js_val(p["mp"])},'
            f'sinks:{js_val(p["sinks"])},qSNER:{js_val(p["qSNER"])},'
            f'ppg:{js_val(p["ppg"])},def_ratio:{js_val(p["def_ratio"])},'
            f'bpg:{js_val(p["bpg"])},fg_pct:{js_val(p["fg_pct"])},'
            f'tfg_pct:{js_val(p["tfg_pct"])},pts_def:{js_val(p["pts_def"])},'
            f'ex_pts_def:{js_val(p["ex_pts_def"])},wr_pct:{js_val(p["wr_pct"])}}}'
        )
        p_entries.append(entry)

    new_p_block = "var P=[\n" + ",\n".join(p_entries) + "\n];"

    # Replace old var P=[...]; block
    html = re.sub(
        r'var P=\[.*?\];',
        new_p_block,
        template_html,
        flags=re.DOTALL
    )

    # 2. Update team stats table rows
    c = teams["Cream Team"]
    d = teams["Dumplings"]
    fa = teams["Free Agents"]

    def hi(v1, v2, fmt=str):
        """Return class 'hi' for winner, 'lo' for loser."""
        if v1 is None or v2 is None:
            return fmt(v1) if v1 else "—", fmt(v2) if v2 else "—"
        if v1 > v2:
            return f'<span class="hi">{fmt(v1)}</span>', fmt(v2)
        elif v2 > v1:
            return fmt(v1), f'<span class="hi">{fmt(v2)}</span>'
        return fmt(v1), fmt(v2)

    cw = c.get("wins", 0); cl = c.get("losses", 0)
    dw = d.get("wins", 0); dl = d.get("losses", 0)
    total = cw + dw
    c_pct = f"{round(cw/total*100,1)}%" if total else "—"
    d_pct = f"{round(dw/total*100,1)}%" if total else "—"

    def pct(v):
        return f"{round(v*100,1)}%" if v is not None else "—"

    new_tbody = f"""        <tr><td class="dim">Record (W–L)</td><td class="vc hi">{cw} – {cl}</td><td class="vc lo">{dw} – {dl}</td><td class="vc">N/A</td></tr>
        <tr><td class="dim">Win %</td><td class="vc hi">{c_pct}</td><td class="vc lo">{d_pct}</td><td class="vc">—</td></tr>
        <tr><td class="dim">Core SNER</td><td class="vc hi">{c.get("avg_sner","—")}</td><td class="vc">{d.get("avg_sner","—")}</td><td class="vc">—</td></tr>
        <tr><td class="dim">FG %</td><td class="vc hi">{pct(c.get("avg_fg_pct"))}</td><td class="vc">{pct(d.get("avg_fg_pct"))}</td><td class="vc">—</td></tr>
        <tr><td class="dim">TFG %</td><td class="vc hi">{pct(c.get("avg_tfg_pct"))}</td><td class="vc">{pct(d.get("avg_tfg_pct"))}</td><td class="vc">—</td></tr>
        <tr><td class="dim">Shotguns</td><td class="vc hi">{c.get("shotguns",0)}</td><td class="vc">{d.get("shotguns",0)}</td><td class="vc">{fa.get("shotguns",0)}</td></tr>
        <tr><td class="dim">Sinks</td><td class="vc hi">{c.get("sinks",0)}</td><td class="vc">{d.get("sinks",0)}</td><td class="vc">{fa.get("sinks",0)}</td></tr>
        <tr><td class="dim">Pts Defended</td><td class="vc">{c.get("pts_def",0)}</td><td class="vc hi">{d.get("pts_def",0)}</td><td class="vc">{fa.get("pts_def",0)}</td></tr>
        <tr><td class="dim">Ex Pts Defended</td><td class="vc hi">{c.get("ex_pts_def",0)}</td><td class="vc">{d.get("ex_pts_def",0)}</td><td class="vc">{fa.get("ex_pts_def",0)}</td></tr>
        <tr><td class="dim">Points Scored</td><td class="vc hi">{c.get("pts_scored",0)}</td><td class="vc">{d.get("pts_scored",0)}</td><td class="vc">{fa.get("pts_scored",0)}</td></tr>
        <tr><td class="dim">Potential Points</td><td class="vc hi">{c.get("pot_pts",0)}</td><td class="vc">{d.get("pot_pts",0)}</td><td class="vc">{fa.get("pot_pts",0)}</td></tr>
        <tr><td class="dim">Beers</td><td class="vc">{c.get("beers",0)}</td><td class="vc hi">{d.get("beers",0)}</td><td class="vc">{fa.get("beers",0)}</td></tr>
        <tr><td class="dim">Refs</td><td class="vc">{c.get("refs",0)}</td><td class="vc hi">{d.get("refs",0)}</td><td class="vc">{fa.get("refs",0)}</td></tr>
        <tr><td class="dim">Bounce Sinks</td><td class="vc">{c.get("bounce_sinks",0)}</td><td class="vc">{d.get("bounce_sinks",0)}</td><td class="vc">{fa.get("bounce_sinks",0)}</td></tr>"""

    # Replace the existing tbody content between thead and /tbody
    html = re.sub(
        r'(<tbody>\s*)(.*?)(\s*</tbody>)',
        lambda m: m.group(1) + new_tbody + "\n      " + m.group(3),
        html,
        count=1,
        flags=re.DOTALL
    )

    # 3. Update the team banner text
    html = re.sub(
        r'(<div class="banner-warn">)(.*?)(</div>)',
        rf'\1{headline}\3',
        html,
        count=1,
        flags=re.DOTALL
    )

    # 4. Update build date in header subtitle
    html = re.sub(
        r'(Snappa League.*?·\s*)(.*?)(<)',
        rf'\g<1>Updated {build_date}\3',
        html,
        count=1
    )

    return html


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():

    print(f"Fetching Match History from published URL...")
    match_rows = fetch_sheet_csv("Match History")
    print(f"  → {len(match_rows)} rows fetched")

    if not match_rows:
        print("ERROR: No data fetched. Check that the sheet is published to the web.", file=sys.stderr)
        sys.exit(1)

    print("Computing player stats...")
    players = compute_player_stats(match_rows)
    print(f"  → {len(players)} players computed")

    print("Computing team stats...")
    teams = compute_team_stats(players, match_rows)

    headline = build_headline(teams)
    build_date = date.today().strftime("%-m/%-d/%Y")

    print(f"Reading template: {TEMPLATE_PATH}")
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    print("Injecting data into HTML...")
    output = inject_data(template, players, teams, headline, build_date)

    print(f"Writing {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✅ Done! {len(players)} players, built {build_date}")


if __name__ == "__main__":
    main()
