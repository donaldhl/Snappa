#!/usr/bin/env python3
"""
build.py — SNER 2026 Dashboard builder (self-contained: no template.html needed)
Reads data.json (exported by Google Apps Script) and writes index.html.
Tabs: Qualifiers (with All toggle) | Team Stats
"""

import os, sys, json, html as htmllib
from datetime import date

# ── CONFIG ────────────────────────────────────────────────────────────────────
DATA_FILE   = "data.json"
OUTPUT_PATH = "index.html"

MIN_FGA   = 100   # qualifier threshold (on_table + off_table)
CORE_FGA  = 450   # Core SNER: players with FGA >= 450 ; Bench: MIN_FGA <= FGA < 450

H2H_POINTS = 3    # points for winning the head-to-head record
CAT_POINTS = 1    # points per category / individual award

# Rookies of the year candidates — FILL THIS IN (names must match the sheet exactly)
ROOKIES = ROOKIES = ["Janet", "Grandpa Juan", "Trevor", "Matt", "Colin", "Manny", "Germaine", "Ashley", "Gloria", "Matt M", "Kevin", "Patrick", "Will H", "Jordan", "Joe", "Simon", "Oliver", "Danny M", "Sydney", "Danny", "Matt C", "Derek", "Brandon", "Sarah"]
# Most Improved: compares first half vs second half of the season's games.
# Each half needs at least this many tosses for a player to be eligible.
MIN_HALF_FGA = 40

# Column names used to find the referee in the match rows (first one found is used)
REF_COLS = ("Ref", "Referee")

# Numbers from your Google Sheet (Cream, Dumplings) — used only by the debug printout
SHEET_CHECK = {
    "qualifiers": (13, 11), "shotguns": (53, 56), "fg": (71.55, 70.25), "tfg": (34.27, 33.85),
    "sinks": (42, 45), "pts_def": (1829, 1938), "beers": (538, 651), "refs": (70, 94),
    "core": (23.10, 20.63), "bench": (13.65, 16.91),
}

TEAM_MAP = {
    # Cream Team
    "Derik": "Cream", "Wil": "Cream", "Alice": "Cream",
    "Erik": "Cream", "Anel": "Cream", "Jill": "Cream",
    "Dan": "Cream", "AJ": "Cream", "Karina": "Cream",
    "Karl": "Cream", "Malorie": "Cream", "Janet": "Cream",
    "Amy": "Cream", "Grandpa Juan": "Cream", "AJD": "Cream",
    "Eric S": "Cream",
    # Dumplings
    "Andrew": "Dumplings", "Don": "Dumplings", "Will": "Dumplings",
    "Joey": "Dumplings", "Michael": "Dumplings", "Ian": "Dumplings",
    "Nathan": "Dumplings", "Audrey": "Dumplings", "Nick": "Dumplings",
    "Sungwon": "Dumplings", "Jake": "Dumplings", "Sam": "Dumplings",
    "Su": "Dumplings", "Matt": "Dumplings", "Trevor": "Dumplings",
    "Colin": "Dumplings", "Manny": "Dumplings",
    # everyone else = Free Agent
}
TEAM_DISPLAY = {"Cream": "Cream Team", "Dumplings": "Dumplings", "Free Agent": "Free Agents"}

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

def gnum_of(row):
    return str(row.get("/", row.get("Game", ""))).strip()

def ref_of(row):
    for c in REF_COLS:
        v = str(row.get(c, "")).strip()
        if v:
            return v
    return ""

def load_rows():
    if not os.path.exists(DATA_FILE):
        print(f"ERROR: {DATA_FILE} not found.", file=sys.stderr)
        sys.exit(1)
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f).get("rows", [])

def u_sner(s):
    mp = s["on_table"] + s["off_table"]
    if not mp:
        return None
    return ((s["points"] * 100) + (s["pts_def"] * 25) + (s["sinks"] * 100) +
            (s["ex_pts_def"] * 25) + (s["pot_pts"] * 25) + (s["on_table"] * 5) -
            (s["off_table"] * 7.5) - (s["pts_allow"] * 62.5)) / mp

def blank():
    return dict(on_table=0, off_table=0, points=0, pot_pts=0, sinks=0, bounce_sinks=0,
                pts_def=0, ex_pts_def=0, pts_allow=0, beers=0, wins=0)

def accumulate(s, row):
    s["on_table"]     += safe_int(row.get("On Table", 0))
    s["off_table"]    += safe_int(row.get("Off Table", 0))
    s["points"]       += safe_int(row.get("Points", 0))
    s["pot_pts"]      += safe_int(row.get("Potential Points", 0))
    s["bounce_sinks"] += safe_int(row.get("Bounce Sink", 0))
    s["sinks"]        += safe_int(row.get("Sink", 0))
    s["pts_def"]      += safe_int(row.get("Points Defended", 0))
    s["ex_pts_def"]   += safe_int(row.get("Extreme Points Defended", 0))
    s["pts_allow"]    += safe_int(row.get("Points Allowed", 0))
    s["beers"]        += safe_int(row.get("Total Beers", 0))
    s["wins"]         += safe_int(row.get("Win", 0))

# ── PLAYER STATS ──────────────────────────────────────────────────────────────
def compute_players(rows):
    stats, games = {}, {}
    for row in rows:
        name = str(row.get("Player", "")).strip()
        if not name or name.lower() == "player":
            continue
        stats.setdefault(name, blank())
        games.setdefault(name, set())
        g = gnum_of(row)
        if g:
            games[name].add(g)
        accumulate(stats[name], row)

    # shotguns & refs, deduplicated per game
    shotguns, refs, seen_sg, seen_ref = {}, {}, set(), set()
    for row in rows:
        g = gnum_of(row)
        sg = str(row.get("Shotgun", "")).strip()
        if sg and g and (g, sg) not in seen_sg:
            seen_sg.add((g, sg)); shotguns[sg] = shotguns.get(sg, 0) + 1
        rf = ref_of(row)
        if rf and g and (g, rf) not in seen_ref:
            seen_ref.add((g, rf)); refs[rf] = refs.get(rf, 0) + 1

    players = []
    for name, s in stats.items():
        gp, mp = len(games[name]), s["on_table"] + s["off_table"]
        if gp == 0 or mp == 0:
            continue
        pts_allow = s["pts_allow"]
        players.append(dict(
            name=name, team=TEAM_MAP.get(name, "Free Agent"), gp=gp, mp=mp,
            sinks=s["sinks"], pts_def=s["pts_def"], ex_pts_def=s["ex_pts_def"],
            beers=s["beers"], wins=s["wins"],
            shotguns=shotguns.get(name, 0), refs=refs.get(name, 0),
            fg_pct=div(s["on_table"], mp), tfg_pct=div(s["points"] + s["pot_pts"], mp),
            wr_pct=div(s["wins"], gp),
            _ppg=div(s["points"], gp), _bpg=div(s["beers"], gp),
            _def=div(s["pts_def"], pts_allow), _pace=div(mp, gp),
            _u=u_sner(s),
        ))

    avg_pace = div(sum(p["mp"] for p in players), sum(p["gp"] for p in players), 1.0)
    for p in players:
        adj = div(avg_pace, p["_pace"], 1.0)
        p["_a"] = p["_u"] * adj
        p["ppg"] = round(p["_ppg"] * adj, 4)
        p["bpg"] = round(p["_bpg"] * adj, 4)
        p["def_ratio"] = round(p["_def"] * adj, 4) if p["_def"] is not None else None

    quals = [p for p in players if p["mp"] >= MIN_FGA]
    avg_q = (sum(p["_a"] for p in quals) / len(quals)) if quals else 1.0
    avg_q = avg_q or 1.0
    for p in players:
        p["qSNER"] = round(p["_a"] * (15 / avg_q), 4)
        p["qualified"] = p["mp"] >= MIN_FGA
        p["wr_pct"] = round(p["wr_pct"], 4)
    return players

def compute_improvement(rows, players):
    """Second-half minus first-half raw SNER per toss (games split at the median game number)."""
    order = []
    for row in rows:
        g = gnum_of(row)
        if g and g not in order:
            order.append(g)
    try:
        order.sort(key=lambda x: float(x))
    except ValueError:
        pass
    if len(order) < 2:
        return {}
    half = {g: (0 if i < len(order) / 2 else 1) for i, g in enumerate(order)}
    halves = {}
    for row in rows:
        name = str(row.get("Player", "")).strip()
        g = gnum_of(row)
        if not name or g not in half:
            continue
        halves.setdefault(name, [blank(), blank()])
        accumulate(halves[name][half[g]], row)
    out = {}
    for name, (a, b) in halves.items():
        if (a["on_table"] + a["off_table"] >= MIN_HALF_FGA and
                b["on_table"] + b["off_table"] >= MIN_HALF_FGA):
            out[name] = u_sner(b) - u_sner(a)
    return out


def norm_team(v):
    v = str(v).strip().lower()
    if v.startswith("cream"): return "Cream"
    if v.startswith("dumpl"): return "Dumplings"
    return ""

def row_team_totals(rows):
    """Team counting stats taken from each match row's own Team column (the team the
    player played for in that game), falling back to TEAM_MAP. Free agents who fill
    in for a team therefore count for that team, and referees/shotgunners are counted
    even if they have no toss rows."""
    T = {t: dict(beers=0, sinks=0, pts_def=0, ex_pts_def=0, shotguns=0, refs=0)
         for t in ("Cream", "Dumplings")}
    allt = dict(beers=0, sinks=0, shotguns=0, refs=0)
    pgt = {}
    for row in rows:
        n, g, t = str(row.get("Player", "")).strip(), gnum_of(row), norm_team(row.get("Team", ""))
        if n and g and t:
            pgt[(g, n)] = t
    seen_sg, seen_rf = set(), set()
    for row in rows:
        n, g = str(row.get("Player", "")).strip(), gnum_of(row)
        t = norm_team(row.get("Team", "")) or TEAM_MAP.get(n, "")
        allt["beers"] += safe_int(row.get("Total Beers", 0))
        allt["sinks"] += safe_int(row.get("Sink", 0))
        if t in T:
            T[t]["beers"]      += safe_int(row.get("Total Beers", 0))
            T[t]["sinks"]      += safe_int(row.get("Sink", 0))
            T[t]["pts_def"]    += safe_int(row.get("Points Defended", 0))
            T[t]["ex_pts_def"] += safe_int(row.get("Extreme Points Defended", 0))
        sg = str(row.get("Shotgun", "")).strip()
        if sg and g and (g, sg) not in seen_sg:
            seen_sg.add((g, sg)); allt["shotguns"] += 1
            st = norm_team(row.get("Team Shogun", "")) or pgt.get((g, sg)) or TEAM_MAP.get(sg, "")
            if st in T: T[st]["shotguns"] += 1
        rf = ref_of(row)
        if rf and g and (g, rf) not in seen_rf:
            seen_rf.add((g, rf)); allt["refs"] += 1
            rt = norm_team(row.get("Ref Team", "")) or pgt.get((g, rf)) or TEAM_MAP.get(rf, "")
            if rt in T: T[rt]["refs"] += 1
    T["all"] = allt
    return T

def debug_report(players, rows):
    T = ("Cream", "Dumplings")
    tot = row_team_totals(rows)
    nan = float("nan")
    print("\n=== DEBUG: script vs. your sheet ===")
    print("Columns found:", sorted({k for r in rows for k in r}))
    for col in ("Team", "Team Shogun", "Ref Team", "Team Win", "Shotgun", "Ref"):
        vals = sorted({str(r.get(col, "")).strip() for r in rows})
        print(f"  distinct '{col}' ({len(vals)}):", vals if len(vals) <= 40 else vals[:40] + ["…"])
    print("  rows:", len(rows), " games:", len({gnum_of(r) for r in rows if gnum_of(r)}))

    def by_map(key): return tuple(sum(p[key] for p in players if p["team"] == t) for t in T)
    def show(label, key, variants):
        sc = SHEET_CHECK.get(key, (nan, nan))
        print(f"\n{label:<16} SHEET: {sc[0]:g} / {sc[1]:g}")
        for name, (c, d) in variants.items():
            c = nan if c is None else c; d = nan if d is None else d
            ok = abs(c - sc[0]) < 0.011 and abs(d - sc[1]) < 0.011
            print(f"   {name:<40} {c:>9g} / {d:<9g} {'✓ MATCH' if ok else ''}")

    q = lambda t, lo, strict=False: [p for p in players if p["team"] == t and
                                       (p["mp"] > lo if strict else p["mp"] >= lo)]
    show("Qualifiers", "qualifiers", {
        f"FGA >= {MIN_FGA} (TEAM_MAP)": tuple(len(q(t, MIN_FGA)) for t in T),
        f"FGA >  {MIN_FGA} (TEAM_MAP)": tuple(len(q(t, MIN_FGA, True)) for t in T)})
    show("Shotguns", "shotguns", {
        "row Team Shogun/Team (deduped)": tuple(tot[t]["shotguns"] for t in T),
        "player-table via TEAM_MAP": by_map("shotguns")})
    show("Sinks", "sinks", {"row Team column": tuple(tot[t]["sinks"] for t in T),
                            "player-table via TEAM_MAP": by_map("sinks")})
    show("Pts Defended", "pts_def", {
        "Points Defended only": tuple(tot[t]["pts_def"] for t in T),
        "+ Extreme x1": tuple(tot[t]["pts_def"] + tot[t]["ex_pts_def"] for t in T),
        "+ Extreme x2 (current)": tuple(tot[t]["pts_def"] + 2 * tot[t]["ex_pts_def"] for t in T),
        "TEAM_MAP, Points Defended only": by_map("pts_def")})
    show("Beers", "beers", {"row Team column": tuple(tot[t]["beers"] for t in T),
                            "player-table via TEAM_MAP": by_map("beers")})
    show("Refs", "refs", {"row Ref Team / Ref name (deduped)": tuple(tot[t]["refs"] for t in T),
                          "player-table via TEAM_MAP": by_map("refs")})
    for key, lab in (("fg_pct", "FG %"), ("tfg_pct", "TFG %")):
        avg = tuple(100 * sum(p[key] for p in q(t, MIN_FGA)) / max(1, len(q(t, MIN_FGA))) for t in T)
        pooled = tuple(100 * sum(p[key] * p["mp"] for p in q(t, MIN_FGA)) /
                       max(1, sum(p["mp"] for p in q(t, MIN_FGA))) for t in T)
        show(lab, "fg" if key == "fg_pct" else "tfg",
             {"avg of qualifiers (current)": avg, "pooled (weighted by tosses)": pooled})
    avgq = lambda ps: (sum(p["qSNER"] for p in ps) / len(ps)) if ps else None
    show("Core SNER", "core", {f"avg qSNER, FGA >= {CORE_FGA}": tuple(avgq(q(t, CORE_FGA)) for t in T),
                                f"avg qSNER, FGA >  {CORE_FGA}": tuple(avgq(q(t, CORE_FGA, True)) for t in T)})
    show("Bench SNER", "bench", {
        f"avg qSNER, {MIN_FGA} <= FGA < {CORE_FGA}": tuple(avgq([p for p in q(t, MIN_FGA) if p["mp"] < CORE_FGA]) for t in T)})

    print("\nPlayers by team with FGA (compare to who your sheet counts as a qualifier):")
    for t in T:
        ps = sorted([p for p in players if p["team"] == t], key=lambda p: -p["mp"])
        print(f"  {t}: " + ", ".join(f'{p["name"]}:{p["mp"]}' for p in ps))
    un = sorted([p for p in players if p["team"] == "Free Agent" and p["mp"] >= 50], key=lambda p: -p["mp"])
    print("  Not in TEAM_MAP (FGA>=50): " + ", ".join(f'{p["name"]}:{p["mp"]}' for p in un))
    print("=== END DEBUG ===\n")

# ── TEAM STATS & SCORING ──────────────────────────────────────────────────────
def compute_team_stats(players, rows):
    T = ("Cream", "Dumplings")
    games = {g for g in (gnum_of(r) for r in rows) if g}

    # head-to-head record (one result per game)
    seen, rec = {}, {"Cream": 0, "Dumplings": 0}
    for row in rows:
        g, w = gnum_of(row), str(row.get("Team Win", "")).strip()
        if g and w and g not in seen:
            seen[g] = w
    for w in seen.values():
        if w in ("Cream", "Cream Team"): rec["Cream"] += 1
        elif w == "Dumplings": rec["Dumplings"] += 1

    tot = row_team_totals(rows)

    def tavg(team, key, lo, hi=None):
        ps = [p for p in players if p["team"] == team and p[key] is not None
              and p["mp"] >= lo and (hi is None or p["mp"] < hi)]
        return (sum(p[key] for p in ps) / len(ps)) if ps else None

    M = {t: dict(
        qualifiers=sum(1 for p in players if p["team"] == t and p["qualified"]),
        shotguns=tot[t]["shotguns"], sinks=tot[t]["sinks"], beers=tot[t]["beers"],
        refs=tot[t]["refs"], pts_def=tot[t]["pts_def"] + 2 * tot[t]["ex_pts_def"],
        fg=tavg(t, "fg_pct", MIN_FGA), tfg=tavg(t, "tfg_pct", MIN_FGA),
        core=tavg(t, "qSNER", CORE_FGA), bench=tavg(t, "qSNER", MIN_FGA, CORE_FGA),
    ) for t in T}

    def top(key, n=3, lo=0, hi=None, fmt=str, val=None):
        ps = [p for p in players if p["mp"] >= lo and (hi is None or p["mp"] < hi)
              and (val(p) if val else p[key]) is not None]
        ps.sort(key=lambda p: -(val(p) if val else p[key]))
        return [(p["name"], p["team"], fmt(val(p) if val else p[key])) for p in ps[:n]]

    pct = lambda v: f"{v*100:.1f}%"
    f2 = lambda v: f"{v:.2f}"
    cats = [
        ("Most Qualifiers", "qualifiers", str, []),
        ("Shotguns", "shotguns", str, top("shotguns")),
        ("FG %", "fg", pct, top("fg_pct", lo=MIN_FGA, fmt=pct)),
        ("TFG %", "tfg", pct, top("tfg_pct", lo=MIN_FGA, fmt=pct)),
        ("Sinks", "sinks", str, top("sinks")),
        ("Pts Defended (Extreme = 2)", "pts_def", str,
         top("", val=lambda p: p["pts_def"] + 2 * p["ex_pts_def"])),
        ("Beers", "beers", str, top("beers")),
        ("Refs", "refs", str, top("refs")),
        (f"Core SNER (>{CORE_FGA} tosses)", "core", f2, top("qSNER", lo=CORE_FGA, fmt=f2)),
        (f"Bench SNER ({MIN_FGA}–{CORE_FGA} tosses)", "bench", f2,
         top("qSNER", lo=MIN_FGA, hi=CORE_FGA, fmt=f2)),
    ]

    pts = {"Cream": 0, "Dumplings": 0}
    rows_out = []
    for label, key, fmt, tops in cats:
        c, d = M["Cream"][key], M["Dumplings"][key]
        winner = None
        if c is not None and d is not None and c != d:
            winner = "Cream" if c > d else "Dumplings"
        elif c is not None and d is None: winner = "Cream"
        elif d is not None and c is None: winner = "Dumplings"
        if winner: pts[winner] += CAT_POINTS
        rows_out.append((label, fmt(c) if c is not None else "—",
                         fmt(d) if d is not None else "—", winner, tops))

    # individual awards -> point goes to the winner's team
    imp = compute_improvement(rows, players)
    quals = [p for p in players if p["qualified"]]
    rook = sorted([p for p in quals if p["name"] in ROOKIES], key=lambda p: -p["qSNER"])
    wr = sorted([p for p in quals if p["gp"] >= 1], key=lambda p: (-p["wr_pct"], -p["gp"]))
    byname = {p["name"]: p for p in players}
    mi = sorted(imp.items(), key=lambda kv: -kv[1])
    awards = [
        ("Rookie of the Year", [(p["name"], p["team"], f'qSNER {p["qSNER"]:.2f}') for p in rook[:3]],
         "" if ROOKIES else "Set ROOKIES in build.py"),
        ("Most Improved Player", [(n, byname[n]["team"], f"{v:+.2f} SNER/toss") for n, v in mi[:3] if n in byname],
         "2nd half vs 1st half of games"),
        ("Highest Win Rate", [(p["name"], p["team"], pct(p["wr_pct"]) + f' ({p["gp"]} GP)') for p in wr[:3]],
         "Qualifiers only"),
    ]
    for _, lst, _n in awards:
        if lst and lst[0][1] in pts:
            pts[lst[0][1]] += CAT_POINTS

    h2h_winner = "Cream" if rec["Cream"] > rec["Dumplings"] else "Dumplings" if rec["Dumplings"] > rec["Cream"] else None
    if h2h_winner:
        pts[h2h_winner] += H2H_POINTS

    tiles = dict(
        games=len(games), beers=tot["all"]["beers"],
        shotguns=tot["all"]["shotguns"], sinks=tot["all"]["sinks"],
        pts=pts,
    )
    return tiles, rec, h2h_winner, rows_out, awards

# ── HTML ──────────────────────────────────────────────────────────────────────
esc = htmllib.escape

ICON = {"Cream": "🥛", "Dumplings": "🥟"}

def tops_html(tops):
    if not tops:
        return '<span class="dimtxt">—</span>'
    out = []
    for i, (n, t, v) in enumerate(tops, 1):
        m = {1: "g1", 2: "g2", 3: "g3"}.get(i, "gn")
        out.append(f'<div class="ti"><span class="medal sm {m}">{i}</span> {ICON.get(t, "🆓")} '
                   f'<span class="tn">{esc(n)}</span> <span class="dimtxt">{esc(v)}</span></div>')
    return "".join(out)

def team_tab(tiles, rec, h2h_winner, cats, awards):
    p = tiles["pts"]
    def hi(w, t): return " hi" if w == t else ""
    body = [f'<tr><td class="dim">Head-to-Head Record <span class="pt">({H2H_POINTS} pts)</span></td>'
            f'<td class="vc{hi(h2h_winner,"Cream")}">{rec["Cream"]} – {rec["Dumplings"]}</td>'
            f'<td class="vc{hi(h2h_winner,"Dumplings")}">{rec["Dumplings"]} – {rec["Cream"]}</td>'
            f'<td class="dim">Games won</td></tr>']
    for label, c, d, w, tops in cats:
        body.append(f'<tr><td class="dim">{esc(label)}</td><td class="vc{hi(w,"Cream")}">{c}</td>'
                    f'<td class="vc{hi(w,"Dumplings")}">{d}</td><td>{tops_html(tops)}</td></tr>')
    aw = []
    for label, lst, note in awards:
        aw.append(f'<div class="card"><div class="ct">{esc(label)}</div>'
                  f'{tops_html(lst) if lst else "<span class=dimtxt>No data</span>"}'
                  f'<div class="note">{esc(note)}</div></div>')
    return f"""
  <div class="bigtile">
    <div class="bt-label">Current Point Total</div>
    <div class="score">
      <div class="side cr"><span>🥛 Cream Team</span><b>{p['Cream']}</b></div>
      <div class="vs">vs</div>
      <div class="side du"><span>🥟 Dumplings</span><b>{p['Dumplings']}</b></div>
    </div>
    <div class="note">1 pt per category or award · {H2H_POINTS} pts for head-to-head · ties score no point</div>
  </div>
  <div class="tiles">
    <div class="tile"><div class="tv">{tiles['games']}</div><div class="tl">Games Played</div></div>
    <div class="tile"><div class="tv">{tiles['beers']}</div><div class="tl">Total Beers</div></div>
    <div class="tile"><div class="tv">{tiles['shotguns']}</div><div class="tl">Total Shotguns</div></div>
    <div class="tile"><div class="tv">{tiles['sinks']}</div><div class="tl">Total Sinks</div></div>
  </div>
  <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th style="min-width:150px">Category</th>
        <th class="th-cream">🥛 Cream Team</th>
        <th class="th-dump">🥟 Dumplings</th>
        <th class="th-top">Top Individuals</th>
      </tr></thead>
      <tbody>{"".join(body)}</tbody>
    </table>
  </div>
  <div class="sec-label">Individual Awards <span style="text-transform:none;letter-spacing:0">(point goes to the winner's team)</span></div>
  <div class="cards">{"".join(aw)}</div>"""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SNER 2026 Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;background:#fff;color:#111827;font-size:14px}
.hdr{padding:14px 16px 10px;border-bottom:1px solid #e5e7eb}
.hdr h1{font-size:16px;font-weight:600;color:#111827}
.hdr p{font-size:12px;color:#6b7280;margin-top:3px}
.tabs{display:flex;padding:8px 16px 0;border-bottom:1px solid #e5e7eb;gap:4px;overflow-x:auto}
.tabs::-webkit-scrollbar{display:none}
.tab{font-size:13px;padding:7px 16px;border-radius:6px 6px 0 0;border:1px solid transparent;color:#6b7280;background:none;cursor:pointer;white-space:nowrap;flex-shrink:0;-webkit-appearance:none}
.tab.active{color:#111827;border-color:#e5e7eb;border-bottom-color:#fff;background:#fff;font-weight:500}
.view{display:none;padding:14px 16px}
.view.active{display:block}
.banner{background:#E1F5EE;border:1px solid #9FE1CB;color:#085041;border-radius:8px;padding:10px 14px;margin-bottom:12px;font-size:13px;line-height:1.5}
.banner strong{font-weight:600}
.filter-row{display:flex;gap:6px;margin-bottom:10px;overflow-x:auto;align-items:center;padding-bottom:2px}
.filter-row::-webkit-scrollbar{display:none}
.filter-row input{font-size:13px;padding:6px 10px;border-radius:8px;border:1px solid #e5e7eb;background:#f9fafb;color:#111827;outline:none;min-width:140px;flex-shrink:0}
.chip{font-size:12px;padding:5px 12px;border-radius:20px;border:1px solid #e5e7eb;background:#f9fafb;color:#6b7280;cursor:pointer;white-space:nowrap;flex-shrink:0;-webkit-appearance:none}
.chip.on{border-color:#374151;color:#111827;background:#f3f4f6;font-weight:500}
.tbl-wrap{border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;margin-bottom:16px;overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;font-size:12px;width:100%}
thead tr{background:#f9fafb}
th{padding:9px 10px;text-align:left;font-size:10px;font-weight:600;color:#6b7280;border-bottom:1px solid #e5e7eb;white-space:nowrap;letter-spacing:.04em;cursor:pointer;user-select:none}
th.sortable:hover{color:#111827}
th.asc::after{content:' ↑';color:#6b7280}
th.desc::after{content:' ↓';color:#6b7280}
tbody tr{border-top:1px solid #e5e7eb}
tbody tr:first-child{border-top:none}
tbody tr:hover,tbody tr:active{background:#f9fafb}
td{padding:9px 10px;color:#111827;white-space:nowrap;vertical-align:middle}
td.name{font-weight:600}
td.dim{color:#6b7280;font-size:12px}
.dimtxt{color:#6b7280;font-size:12px}
.th-cream{background:#FAEEDA;color:#633806;font-weight:600;text-align:center;font-size:11px;padding:9px 10px;border-bottom:1px solid #FAC775;cursor:default}
.th-dump{background:#E1F5EE;color:#085041;font-weight:600;text-align:center;font-size:11px;padding:9px 10px;border-bottom:1px solid #9FE1CB;cursor:default}
.th-top{background:#EEEDFE;color:#3C3489;font-weight:600;font-size:11px;padding:9px 10px;border-bottom:1px solid #CECBF6;cursor:default}
td.vc{text-align:center;font-size:12px}
.badge{display:inline-block;font-size:10px;font-weight:600;padding:2px 8px;border-radius:20px;border:1px solid;white-space:nowrap}
.bc{background:#FAEEDA;color:#633806;border-color:#FAC775}
.bd{background:#E1F5EE;color:#085041;border-color:#9FE1CB}
.bf{background:#EEEDFE;color:#3C3489;border-color:#CECBF6}
.medal{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;font-size:11px;font-weight:700}
.medal.sm{width:18px;height:18px;font-size:10px}
.g1{background:#F5C842;color:#5a3e00}
.g2{background:#C0C0C0;color:#333}
.g3{background:#C87941;color:#fff}
.gn{background:#f3f4f6;color:#9ca3af}
.hi{color:#085041;font-weight:600}
/* team tab */
.bigtile{border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin-bottom:12px;text-align:center;background:linear-gradient(90deg,#FAEEDA 0%,#fff 50%,#E1F5EE 100%)}
.bt-label{font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.06em}
.score{display:flex;justify-content:center;align-items:center;gap:28px;margin:8px 0;flex-wrap:wrap}
.side{display:flex;flex-direction:column;align-items:center;font-size:14px;font-weight:600}
.side b{font-size:52px;line-height:1.1;font-weight:700}
.side.cr{color:#633806}.side.du{color:#085041}.vs{color:#9ca3af;font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-bottom:14px}
.tile{border:1px solid #e5e7eb;border-radius:10px;padding:12px;text-align:center;background:#f9fafb}
.tv{font-size:24px;font-weight:600}.tl{font-size:10px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;margin-top:2px}
.note{font-size:11px;color:#6b7280;margin-top:6px}.pt{color:#9ca3af;font-size:11px}
.sec-label{font-size:11px;font-weight:600;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em;margin:18px 0 8px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px}
.card{border:1px solid #e5e7eb;border-radius:10px;padding:12px}
.ct{font-size:12px;font-weight:600;margin-bottom:8px}
.ti{white-space:nowrap;margin-bottom:4px;font-size:12px}.tn{font-weight:600}
#teams td{vertical-align:top}
</style>
</head>
<body>

<div class="hdr">
  <h1>SNER 2026 Season — Stats Dashboard</h1>
  <p>Snappa League · 🥛 Cream Team vs 🥟 Dumplings · Updated __BUILT__</p>
</div>

<div class="tabs">
  <button class="tab active" id="tab-monthly" onclick="st('monthly')">Qualifiers</button>
  <button class="tab"        id="tab-teams"   onclick="st('teams')">Team Stats</button>
</div>

<!-- ── TAB 1 ── -->
<div id="monthly" class="view active">
  <div class="banner"><strong>Rankings by SNER</strong> — Qualifiers have at least __MIN__ tosses. Click any column header to re-sort.</div>
  <div class="filter-row">
    <input type="text" id="ms-search" placeholder="Search player…" oninput="renderMonthly()">
    <button class="chip on" id="sc-q"   onclick="setScope('q')">Qualifiers</button>
    <button class="chip"    id="sc-all" onclick="setScope('all')">All</button>
  </div>
  <div class="filter-row">
    <button class="chip on" id="fc-all"   onclick="setMF('all')">All Teams</button>
    <button class="chip"    id="fc-cream" onclick="setMF('Cream Team')">🥛 Cream</button>
    <button class="chip"    id="fc-dump"  onclick="setMF('Dumplings')">🥟 Dumplings</button>
    <button class="chip"    id="fc-fa"    onclick="setMF('Free Agents')">🆓 Free Agents</button>
    <span class="dimtxt" id="cnt" style="margin-left:6px"></span>
  </div>
  <div class="tbl-wrap">
    <table>
      <thead><tr>
        <th style="width:30px">#</th>
        <th class="sortable" onclick="msSort('name')"       id="mth-name">Player</th>
        <th class="sortable" onclick="msSort('team')"       id="mth-team">Team</th>
        <th class="sortable desc" onclick="msSort('qSNER')" id="mth-qSNER">SNER</th>
        <th class="sortable" onclick="msSort('fg_pct')"     id="mth-fg_pct">FG %</th>
        <th class="sortable" onclick="msSort('tfg_pct')"    id="mth-tfg_pct">TFG %</th>
        <th class="sortable" onclick="msSort('ppg')"        id="mth-ppg">PPG</th>
        <th class="sortable" onclick="msSort('def_ratio')"  id="mth-def_ratio">Def Ratio</th>
        <th class="sortable" onclick="msSort('bpg')"        id="mth-bpg">BPG</th>
        <th class="sortable" onclick="msSort('gp')"         id="mth-gp">GP</th>
        <th class="sortable" onclick="msSort('mp')"         id="mth-mp">Tosses</th>
        <th class="sortable" onclick="msSort('sinks')"      id="mth-sinks">Sinks</th>
        <th class="sortable" onclick="msSort('wr_pct')"     id="mth-wr_pct">Win %</th>
        <th class="sortable" onclick="msSort('shotguns')"   id="mth-shotguns">Shotguns</th>
        <th class="sortable" onclick="msSort('refs')"       id="mth-refs">Refs</th>
        <th class="sortable" onclick="msSort('pts_def')"    id="mth-pts_def">Pts Def</th>
        <th class="sortable" onclick="msSort('ex_pts_def')" id="mth-ex_pts_def">Ex Pts Def</th>
        <th class="sortable" onclick="msSort('beers')"      id="mth-beers">Beers</th>
      </tr></thead>
      <tbody id="monthly-body"></tbody>
    </table>
  </div>
</div>

<!-- ── TAB 2 ── -->
<div id="teams" class="view">__TEAM__</div>

<script>
var P=__PLAYERS__;

function f2(v){return (v===null||v===undefined)?null:v.toFixed(2);}
function fp(v){return (v===null||v===undefined)?null:((v*100).toFixed(2)+'%');}
var NA='<span style="color:#9ca3af">—</span>';
function fv(v,fn){return(v===null||v===undefined)?NA:(fn?fn(v):String(v));}

function badge(t){
  if(t==='Cream Team')return '<span class="badge bc">🥛 Cream</span>';
  if(t==='Dumplings') return '<span class="badge bd">🥟 Dumps</span>';
  return '<span class="badge bf">🆓 FA</span>';
}
function medal(r){
  var c=r===1?'g1':r===2?'g2':r===3?'g3':'gn';
  return '<span class="medal '+c+'">'+r+'</span>';
}
function dosort(arr,key,dir){
  return arr.slice().sort(function(a,b){
    var av=a[key],bv=b[key];
    if(av===null&&bv===null)return 0;
    if(av===null)return 1;
    if(bv===null)return -1;
    if(typeof av==='string')return av.localeCompare(bv)*dir;
    return(av>bv?1:av<bv?-1:0)*dir;
  });
}
function clearTh(prefix){
  var els=document.querySelectorAll('[id^="'+prefix+'"]');
  for(var i=0;i<els.length;i++)els[i].classList.remove('asc','desc');
}
function markTh(id,dir){
  var el=document.getElementById(id);
  if(el)el.classList.add(dir===-1?'desc':'asc');
}

var mScope='q',mF='all',mK='qSNER',mD=-1;
function setScope(s){
  mScope=s;
  document.getElementById('sc-q').classList.toggle('on',s==='q');
  document.getElementById('sc-all').classList.toggle('on',s==='all');
  renderMonthly();
}
function setMF(f){
  mF=f;
  var map={all:'all',cream:'Cream Team',dump:'Dumplings',fa:'Free Agents'};
  for(var k in map){
    var el=document.getElementById('fc-'+k);
    if(el)el.classList.toggle('on',map[k]===f);
  }
  renderMonthly();
}
function msSort(k){
  if(mK===k)mD*=-1;else{mK=k;mD=(k==='name'||k==='team')?1:-1;}
  clearTh('mth-');markTh('mth-'+k,mD);
  renderMonthly();
}
function renderMonthly(){
  var q=document.getElementById('ms-search').value.toLowerCase();
  var d=P.slice();
  if(mScope==='q')d=d.filter(function(p){return p.qualified;});
  if(mF!=='all')d=d.filter(function(p){return p.team===mF;});
  if(q)d=d.filter(function(p){return p.name.toLowerCase().indexOf(q)!==-1;});
  d=dosort(d,mK,mD);
  var rows='';
  for(var i=0;i<d.length;i++){
    var p=d[i];
    rows+='<tr>'+
      '<td>'+medal(i+1)+'</td>'+
      '<td class="name">'+p.name+'</td>'+
      '<td>'+badge(p.team)+'</td>'+
      '<td style="font-weight:600">'+fv(p.qSNER,f2)+'</td>'+
      '<td>'+fv(p.fg_pct,fp)+'</td>'+
      '<td>'+fv(p.tfg_pct,fp)+'</td>'+
      '<td>'+fv(p.ppg,f2)+'</td>'+
      '<td>'+fv(p.def_ratio,f2)+'</td>'+
      '<td>'+fv(p.bpg,f2)+'</td>'+
      '<td>'+p.gp+'</td>'+
      '<td>'+p.mp+'</td>'+
      '<td>'+p.sinks+'</td>'+
      '<td>'+fv(p.wr_pct,fp)+'</td>'+
      '<td>'+p.shotguns+'</td>'+
      '<td>'+p.refs+'</td>'+
      '<td>'+p.pts_def+'</td>'+
      '<td>'+p.ex_pts_def+'</td>'+
      '<td>'+p.beers+'</td>'+
    '</tr>';
  }
  document.getElementById('monthly-body').innerHTML=rows;
  document.getElementById('cnt').textContent=d.length+' players';
}

function st(id){
  var views=document.querySelectorAll('.view');
  for(var i=0;i<views.length;i++)views[i].classList.remove('active');
  var tabs=document.querySelectorAll('.tab');
  for(var i=0;i<tabs.length;i++)tabs[i].classList.remove('active');
  document.getElementById(id).classList.add('active');
  document.getElementById('tab-'+id).classList.add('active');
}
renderMonthly();
</script>
</body>
</html>"""

def build_html(players, tiles, rec, h2h_winner, cats, awards, built):
    keep = ["name", "team", "gp", "mp", "qSNER", "sinks", "wr_pct", "shotguns", "refs", "ppg",
            "def_ratio", "bpg", "fg_pct", "tfg_pct", "pts_def", "ex_pts_def", "beers", "qualified"]
    data = [{k: (TEAM_DISPLAY.get(p[k], p[k]) if k == "team" else p[k]) for k in keep} for p in players]
    return (TEMPLATE.replace("__PLAYERS__", json.dumps(data))
            .replace("__TEAM__", team_tab(tiles, rec, h2h_winner, cats, awards))
            .replace("__BUILT__", built).replace("__MIN__", str(MIN_FGA)))

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    rows = load_rows()
    print(f"Loaded {len(rows)} rows")
    players = compute_players(rows)
    print(f"{len(players)} players computed")
    debug_report(players, rows)
    tiles, rec, h2h_winner, cats, awards = compute_team_stats(players, rows)
    built = date.today().strftime("%-m/%-d/%Y")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(build_html(players, tiles, rec, h2h_winner, cats, awards, built))
    print(f"✅ Done! Built {built}")

if __name__ == "__main__":
    main()
