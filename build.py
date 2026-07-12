#!/usr/bin/env python3
"""
build.py — SNER 2026 Dashboard builder
Fetches live data from Google Sheets (published as CSV) and generates index.html.
Run by Netlify on every deploy.
"""

import os, sys, json, csv, io, re
from datetime import date

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Path to the data file exported by Google Apps Script
DATA_FILE = "data.json"

# Minimum FGA (on_table + off_table) to appear in Qualifiers tab
MIN_FGA = 100

# Team assignments — update manually when players move between teams
# Cream Team = rows 3-18, Dumplings = rows 21-33, FA = rows 36-41
TEAM_MAP = {
    # Cream Team
    "Derik": "Cream", "Wil": "Cream",      "Alice": "Cream",
    "Erik": "Cream",  "Anel": "Cream",      "Jill": "Cream",
    "Dan": "Cream",   "AJ": "Cream",        "Karina": "Cream",
    "Karl": "Cream",  "Malorie": "Cream",   "Janet": "Cream",
    "Amy": "Cream",   "Grandpa Juan": "Cream", "AJD": "Cream",
    "Eric S": "Cream",
    # Dumplings
    "Andrew": "Dumplings", "Don": "Dumplings",    "Will": "Dumplings",
    "Joey": "Dumplings",   "Michael": "Dumplings", "Ian": "Dumplings",
    "Nathan": "Dumplings", "Audrey": "Dumplings",  "Nick": "Dumplings",
    "Sungwon": "Dumplings", "Jake": "Dumplings",   "Sam": "Dumplings",
    "Su": "Dumplings", "Matt": "Dumplings", "Trevor": "Dumplings", "Colin": "Dumplings", "Manny": "Dumplings",
    # FA = everyone else
}

# Undrafted Free Agents shown in FA Bids tab
FA_NAMES = ["Germaine", "Jen S", "Kate", "Ashley", "Gloria", "Liberty", "Ben","Matt M", "Kevin", "Patrick", "Will H", "Jordan", "Joe", "Simon", "Vijay", "Oliver", "Danny M", "Sydney", "Danny"]

# ── LOAD DATA ─────────────────────────────────────────────────────────────────
def fetch_sheet_csv(sheet_name):
    """Read match rows from data.json exported by Google Apps Script."""
    if not os.path.exists(DATA_FILE):
        print(f"  ERROR: {DATA_FILE} not found. Run the Apps Script export first.", file=sys.stderr)
        return []
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("rows", [])
    print(f"  → Loaded {len(rows)} rows from {DATA_FILE}")
    return rows

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

# ── PLAYER STATS ──────────────────────────────────────────────────────────────
def compute_player_stats(match_rows):
    stats = {}
    player_games = {}

    for row in match_rows:
        name = str(row.get("Player", "")).strip()
        if not name or name.lower() == "player":
            continue
        gnum = str(row.get("/", row.get("Game", ""))).strip()
        if name not in stats:
            stats[name] = dict(gp=0, mp=0, on_table=0, off_table=0,
                               points=0, pot_pts=0, bounce_sinks=0, sinks=0,
                               pts_def=0, ex_pts_def=0, pts_allow=0, beers=0, wins=0)
            player_games[name] = set()
        s = stats[name]
        if gnum:
            player_games[name].add(gnum)
        s["on_table"]    += safe_int(row.get("On Table", 0))
        s["off_table"]   += safe_int(row.get("Off Table", 0))
        s["points"]      += safe_int(row.get("Points", 0))
        s["pot_pts"]     += safe_int(row.get("Potential Points", 0))
        s["bounce_sinks"]+= safe_int(row.get("Bounce Sink", 0))
        s["sinks"]       += safe_int(row.get("Sink", 0))
        s["pts_def"]     += safe_int(row.get("Points Defended", 0))
        s["ex_pts_def"]  += safe_int(row.get("Extreme Points Defended", 0))
        s["pts_allow"]   += safe_int(row.get("Points Allowed", 0))
        s["beers"]       += safe_int(row.get("Total Beers", 0))
        s["wins"]        += safe_int(row.get("Win", 0))

    for name, s in stats.items():
        s["gp"] = len(player_games[name])
        s["mp"] = s["on_table"] + s["off_table"]   # FGA = On Table + Off Table

    # Shotguns per player (deduplicated by game)
    shotgun_counts = {}
    seen_sg = set()
    for row in match_rows:
        sg = str(row.get("Shotgun", "")).strip()
        gnum = str(row.get("/", row.get("Game", ""))).strip()
        if sg and gnum and (gnum, sg) not in seen_sg:
            seen_sg.add((gnum, sg))
            shotgun_counts[sg] = shotgun_counts.get(sg, 0) + 1

    players = []
    for name, s in stats.items():
        gp = s["gp"]; mp = s["mp"]
        if gp == 0 or mp == 0:
            continue
        on_table  = s["on_table"];  off_table = s["off_table"]
        points    = s["points"];    pot_pts   = s["pot_pts"]
        sinks     = s["sinks"];     pts_def   = s["pts_def"]
        ex_pts    = s["ex_pts_def"]; pts_allow = s["pts_allow"]
        beers     = s["beers"];     wins      = s["wins"]

        fg_pct        = div(on_table, mp)
        tfg_pct       = div(points + pot_pts, mp)
        ppg_raw       = div(points, gp)
        bpg_raw       = div(beers, gp)
        wr_pct        = div(wins, gp)
        def_ratio_raw = div(pts_def, pts_allow) if pts_allow else None
        toss_pace     = div(mp, gp)

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

        team     = TEAM_MAP.get(name, "Free Agent")
        shotguns = shotgun_counts.get(name, 0)

        players.append({
            "name": name, "team": team,
            "gp": gp, "mp": mp,
            "on_table": on_table, "off_table": off_table,
            "sinks": sinks, "pts_def": pts_def, "ex_pts_def": ex_pts,
            "pts_allow": pts_allow, "beers": beers, "wins": wins,
            "shotguns": shotguns,
            "fg_pct": fg_pct, "tfg_pct": tfg_pct,
            "wr_pct": round(wr_pct, 4) if wr_pct is not None else None,
            "def_ratio_raw": def_ratio_raw,
            "ppg_raw": ppg_raw,
            "bpg_raw": bpg_raw,
            "toss_pace": toss_pace,
            "u_sner": u_sner,
        })

    if not players:
        return players

    # Pace adjustment
    avg_pace = sum(p["toss_pace"] for p in players) / len(players)
    for p in players:
        pace_adj = div(avg_pace, p["toss_pace"], 1.0)
        p["a_sner"] = p["u_sner"] * pace_adj
        # Adjusted stats = raw * pace_adj (cols E, F, G in sheet)
        p["ppg"]       = round(p["ppg_raw"] * pace_adj, 4) if p["ppg_raw"] is not None else None
        p["bpg"]       = round(p["bpg_raw"] * pace_adj, 4) if p["bpg_raw"] is not None else None
        p["def_ratio"] = round(p["def_ratio_raw"] * pace_adj, 4) if p["def_ratio_raw"] is not None else None

    # qSNER = aSNER * (15 / avg_aSNER_of_qualifiers)
    # Qualifiers = players with FGA >= MIN_FGA (100 tosses)
    qualifiers = [p for p in players if p["mp"] >= MIN_FGA]
    avg_a_sner_q = sum(p["a_sner"] for p in qualifiers) / len(qualifiers) if qualifiers else 1.0
    if avg_a_sner_q == 0:
        avg_a_sner_q = 1.0
    for p in players:
        p["qSNER"] = round(p["a_sner"] * (15 / avg_a_sner_q), 4)

    # Clean up internal fields
    for p in players:
        for k in ["u_sner", "toss_pace", "a_sner", "ppg_raw", "bpg_raw", "def_ratio_raw"]:
            del p[k]

    return players

# ── TEAM STATS ────────────────────────────────────────────────────────────────
def compute_team_stats(players, match_rows):
    teams = {
        "Cream":      dict(shotguns=0, wins=0, losses=0, beers=0, pts_def=0,
                           ex_pts_def=0, sinks=0, refs=0, bounce_sinks=0,
                           pts_scored=0, pot_pts=0),
        "Dumplings":  dict(shotguns=0, wins=0, losses=0, beers=0, pts_def=0,
                           ex_pts_def=0, sinks=0, refs=0, bounce_sinks=0,
                           pts_scored=0, pot_pts=0),
        "Free Agent": dict(shotguns=0, wins=0, losses=0, beers=0, pts_def=0,
                           ex_pts_def=0, sinks=0, refs=0, bounce_sinks=0,
                           pts_scored=0, pot_pts=0),
    }

    for row in match_rows:
        team = str(row.get("Team", "")).strip()
        if team not in teams:
            continue
        t = teams[team]
        t["beers"]       += safe_int(row.get("Total Beers", 0))
        t["pts_def"]     += safe_int(row.get("Points Defended", 0))
        t["ex_pts_def"]  += safe_int(row.get("Extreme Points Defended", 0))
        t["sinks"]       += safe_int(row.get("Sink", 0))
        t["bounce_sinks"]+= safe_int(row.get("Bounce Sink", 0))
        t["pts_scored"]  += safe_int(row.get("Points", 0))
        t["pot_pts"]     += safe_int(row.get("Potential Points", 0))

    for row in match_rows:
        ref_team = str(row.get("Ref Team", "")).strip()
        if ref_team in teams:
            teams[ref_team]["refs"] += 1

    seen_sg = set()
    for row in match_rows:
        sg_player = str(row.get("Shotgun", "")).strip()
        gnum = str(row.get("/", row.get("Game", ""))).strip()
        if sg_player and gnum and (gnum, sg_player) not in seen_sg:
            seen_sg.add((gnum, sg_player))
            sg_team = str(row.get("Team Shogun", "")).strip()
            if sg_team in teams:
                teams[sg_team]["shotguns"] += 1

    seen_games = {}
    for row in match_rows:
        gnum = str(row.get("/", row.get("Game", ""))).strip()
        team_win = str(row.get("Team Win", "")).strip()
        if gnum and team_win and gnum not in seen_games:
            seen_games[gnum] = team_win
    for gnum, winner in seen_games.items():
        if winner in ("Cream", "Cream Team"):
            teams["Cream"]["wins"] += 1
            teams["Dumplings"]["losses"] += 1
        elif winner == "Dumplings":
            teams["Dumplings"]["wins"] += 1
            teams["Cream"]["losses"] += 1

    # Avg SNER — use qualified players only (FGA >= MIN_FGA)
    for team_key in teams:
        t_players = [p for p in players if p["team"] == team_key and p["mp"] >= MIN_FGA]
        if t_players:
            teams[team_key]["avg_sner"]    = round(sum(p["qSNER"] for p in t_players) / len(t_players), 2)
            teams[team_key]["avg_fg_pct"]  = round(
                sum(p["fg_pct"] for p in t_players if p["fg_pct"] is not None) /
                max(1, sum(1 for p in t_players if p["fg_pct"] is not None)), 4)
            teams[team_key]["avg_tfg_pct"] = round(
                sum(p["tfg_pct"] for p in t_players if p["tfg_pct"] is not None) /
                max(1, sum(1 for p in t_players if p["tfg_pct"] is not None)), 4)
        else:
            teams[team_key]["avg_sner"] = teams[team_key]["avg_fg_pct"] = teams[team_key]["avg_tfg_pct"] = None

    return teams

# ── HTML GENERATION ───────────────────────────────────────────────────────────
TEMPLATE_PATH = "template.html"
OUTPUT_PATH   = "index.html"

def inject_data(template_html, players, teams, build_date):
    TEAM_DISPLAY = {"Cream": "Cream Team", "Dumplings": "Dumplings", "Free Agent": "Free Agents"}

    def js_val(v):
        if v is None: return "null"
        if isinstance(v, bool): return "true" if v else "false"
        if isinstance(v, (int, float)): return str(v)
        return json.dumps(v)

    # ── P array: ALL players (Team Stats tab needs everyone) ──────────────────
    p_entries = []
    for p in players:
        display_team = TEAM_DISPLAY.get(p["team"], "Free Agents")
        entry = (
            f'  {{name:{js_val(p["name"])},team:{js_val(display_team)},'
            f'gp:{js_val(p["gp"])},mp:{js_val(p["mp"])},'
            f'sinks:{js_val(p["sinks"])},qSNER:{js_val(p["qSNER"])},'
            f'ppg:{js_val(p["ppg"])},def_ratio:{js_val(p["def_ratio"])},'
            f'bpg:{js_val(p["bpg"])},fg_pct:{js_val(p["fg_pct"])},'
            f'tfg_pct:{js_val(p["tfg_pct"])},pts_def:{js_val(p["pts_def"])},'
            f'ex_pts_def:{js_val(p["ex_pts_def"])},wr_pct:{js_val(p["wr_pct"])}}}'
        )
        p_entries.append(entry)

    # Build Q array (qualifiers only, FGA >= MIN_FGA) for Qualifiers tab
    qualified_entries = [e for e, p in zip(p_entries, players) if p["mp"] >= MIN_FGA]
    new_q_block = "var Q=[\n" + ",\n".join(qualified_entries) + "\n];"

    new_p_block = "var P=[\n" + ",\n".join(p_entries) + "\n];"
    html = re.sub(r'var P=\[.*?\];', new_p_block + "\n" + new_q_block, template_html, flags=re.DOTALL)

    # Make renderMonthly use Q instead of P by replacing the P.slice() line
    html = html.replace('function renderMonthly(){\n  var q=document.getElementById(\'ms-search\').value.toLowerCase();\n  var d=P.slice();',
                        'function renderMonthly(){\n  var q=document.getElementById(\'ms-search\').value.toLowerCase();\n  var d=Q.slice();')


    # ── FA_NAMES: update to current list ─────────────────────────────────────
    fa_js = "var FA_NAMES=" + json.dumps(FA_NAMES) + ";"
    html = re.sub(r'var FA_NAMES=\[.*?\];', fa_js, html)

    # ── Tab label: "Monthly Stats" → "Qualifiers" ────────────────────────────
    html = html.replace('>Monthly Stats<', '>Qualifiers<')

    # ── Team stats tbody ──────────────────────────────────────────────────────
    c  = teams["Cream"]
    d  = teams["Dumplings"]
    fa = teams["Free Agent"]

    def pct(v): return f"{round(v*100,1)}%" if v is not None else "—"

    cw = c["wins"]; cl = c["losses"]
    dw = d["wins"]; dl = d["losses"]
    total = cw + dw
    c_pct = f"{round(cw/total*100,1)}%" if total else "—"
    d_pct = f"{round(dw/total*100,1)}%" if total else "—"

    new_tbody = f"""        <tr><td class="dim">Record (W–L)</td><td class="vc hi">{cw} – {cl}</td><td class="vc lo">{dw} – {dl}</td><td class="vc">N/A</td></tr>
        <tr><td class="dim">Win %</td><td class="vc hi">{c_pct}</td><td class="vc lo">{d_pct}</td><td class="vc">—</td></tr>
        <tr><td class="dim">Core SNER</td><td class="vc hi">{c.get("avg_sner","—")}</td><td class="vc">{d.get("avg_sner","—")}</td><td class="vc">—</td></tr>
        <tr><td class="dim">FG %</td><td class="vc hi">{pct(c.get("avg_fg_pct"))}</td><td class="vc">{pct(d.get("avg_fg_pct"))}</td><td class="vc">—</td></tr>
        <tr><td class="dim">TFG %</td><td class="vc hi">{pct(c.get("avg_tfg_pct"))}</td><td class="vc">{pct(d.get("avg_tfg_pct"))}</td><td class="vc">—</td></tr>
        <tr><td class="dim">Shotguns</td><td class="vc hi">{c["shotguns"]}</td><td class="vc">{d["shotguns"]}</td><td class="vc">{fa["shotguns"]}</td></tr>
        <tr><td class="dim">Sinks</td><td class="vc hi">{c["sinks"]}</td><td class="vc">{d["sinks"]}</td><td class="vc">{fa["sinks"]}</td></tr>
        <tr><td class="dim">Pts Defended</td><td class="vc">{c["pts_def"]}</td><td class="vc hi">{d["pts_def"]}</td><td class="vc">{fa["pts_def"]}</td></tr>
        <tr><td class="dim">Ex Pts Defended</td><td class="vc hi">{c["ex_pts_def"]}</td><td class="vc">{d["ex_pts_def"]}</td><td class="vc">{fa["ex_pts_def"]}</td></tr>
        <tr><td class="dim">Points Scored</td><td class="vc hi">{c["pts_scored"]}</td><td class="vc">{d["pts_scored"]}</td><td class="vc">{fa["pts_scored"]}</td></tr>
        <tr><td class="dim">Potential Points</td><td class="vc hi">{c["pot_pts"]}</td><td class="vc">{d["pot_pts"]}</td><td class="vc">{fa["pot_pts"]}</td></tr>
        <tr><td class="dim">Beers</td><td class="vc">{c["beers"]}</td><td class="vc hi">{d["beers"]}</td><td class="vc">{fa["beers"]}</td></tr>
        <tr><td class="dim">Refs</td><td class="vc">{c["refs"]}</td><td class="vc hi">{d["refs"]}</td><td class="vc">{fa["refs"]}</td></tr>
        <tr><td class="dim">Bounce Sinks</td><td class="vc">{c["bounce_sinks"]}</td><td class="vc">{d["bounce_sinks"]}</td><td class="vc">{fa["bounce_sinks"]}</td></tr>"""

    html = re.sub(
        r'(<tbody>\s*)(.*?)(\s*</tbody>)',
        lambda m: m.group(1) + new_tbody + "\n      " + m.group(3),
        html, count=1, flags=re.DOTALL
    )

    # ── FA bids table headers ─────────────────────────────────────────────────
    fa_headers = "".join(
        f'<th class="center" style="min-width:70px">{name}</th>'
        for name in FA_NAMES
    )
    html = re.sub(
        r'(<tr>\s*<th style="min-width:110px">Stat</th>)(.*?)(</tr>)',
        lambda m: m.group(1) + fa_headers + m.group(3),
        html, count=1, flags=re.DOTALL
    )

    # ── Team banner ───────────────────────────────────────────────────────────
    tot = cw + dw
    cp = f"{round(cw/tot*100,1)}%" if tot else "—"
    dp = f"{round(dw/tot*100,1)}%" if tot else "—"
    headline = (
        f"<strong>Head-to-head:</strong> Cream Team won {cw}–{dw} "
        f"({cp} vs {dp}). Dumplings led in Pts Defended, Beers, and Refs. "
        f"Cream Team dominated in Shotguns, Sinks, Core SNER, and wins."
    )
    html = re.sub(
        r'(<div class="banner-warn">)(.*?)(</div>)',
        rf'\1{headline}\3', html, count=1, flags=re.DOTALL
    )

    # ── Build date ────────────────────────────────────────────────────────────
    html = re.sub(
        r'(Snappa League\s*·\s*)([^<]*?)(<)',
        rf'\g<1>Updated {build_date}\3', html, count=1
    )

    return html

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print(f"Loading data from {DATA_FILE}...")
    match_rows = fetch_sheet_csv("Match History")
    if not match_rows:
        print("ERROR: No data loaded. Push data.json from Apps Script first.", file=sys.stderr)
        sys.exit(1)

    print("Computing player stats...")
    players = compute_player_stats(match_rows)
    print(f"  → {len(players)} players computed")

    print("Computing team stats...")
    teams = compute_team_stats(players, match_rows)

    build_date = date.today().strftime("%-m/%-d/%Y")

    print(f"Reading {TEMPLATE_PATH}...")
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    print("Injecting data...")
    output = inject_data(template, players, teams, build_date)

    print(f"Writing {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✅ Done! {len(players)} players, built {build_date}")

if __name__ == "__main__":
    main()
