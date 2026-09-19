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
ROOKIES = ["Janet", "Grandpa Juan", "Trevor", "Matt", "Colin", "Manny", "Germaine", "Ashley", "Gloria", "Matt M", "Kevin", "Patrick", "Will H", "Jordan", "Joe", "Simon", "Oliver", "Danny M", "Sydney", "Danny", "Matt C", "Derek", "Brandon", "Sarah"]
# Most Improved: compares first half vs second half of the season's games.
# Each half needs at least this many tosses for a player to be eligible.
MIN_HALF_FGA = 40

# Column names used to find the referee in the match rows (first one found is used)
REF_COLS = ("Ref", "Referee")

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

    def tsum(team, key):
        return sum(p[key] for p in players if p["team"] == team)

    def tavg(team, key, lo, hi=None):
        ps = [p for p in players if p["team"] == team and p[key] is not None
              and p["mp"] >= lo and (hi is None or p["mp"] < hi)]
        return (sum(p[key] for p in ps) / len(ps)) if ps else None

    # refs fallback if no per-player referee column exists
    refs = {t: tsum(t, "refs") for t in T}
    if not any(refs.values()):
        seen_r = set()
        for row in rows:
            g, rt = gnum_of(row), str(row.get("Ref Team", "")).strip()
            if g and rt in T and g not in seen_r:
                seen_r.add(g); refs[rt] += 1

    M = {t: dict(
        qualifiers=sum(1 for p in players if p["team"] == t and p["qualified"]),
        shotguns=tsum(t, "shotguns"), sinks=tsum(t, "sinks"), beers=tsum(t, "beers"),
        refs=refs[t], pts_def=tsum(t, "pts_def") + 2 * tsum(t, "ex_pts_def"),
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
        games=len(games), beers=sum(p["beers"] for p in players),
        shotguns=sum(p["shotguns"] for p in players), sinks=sum(p["sinks"] for p in players),
        pts=pts,
    )
    return tiles, rec, h2h_winner, rows_out, awards

# ── HTML ──────────────────────────────────────────────────────────────────────
esc = htmllib.escape

def tops_html(tops):
    if not tops:
        return '<span class="dim">—</span>'
    out = []
    for i, (n, t, v) in enumerate(tops, 1):
        cls = {"Cream": "tc", "Dumplings": "td"}.get(t, "tf")
        out.append(f'<div class="ti"><span class="rk">{i}</span><span class="{cls}">{esc(n)}</span> <span class="dim">{esc(v)}</span></div>')
    return "".join(out)

def team_tab(tiles, rec, h2h_winner, cats, awards):
    p = tiles["pts"]
    def hi(w, t): return " hi" if w == t else ""
    body = [f'<tr><td class="dim">Head-to-Head Record <span class="pt">({H2H_POINTS} pts)</span></td>'
            f'<td class="vc{hi(h2h_winner,"Cream")}">{rec["Cream"]}</td>'
            f'<td class="vc{hi(h2h_winner,"Dumplings")}">{rec["Dumplings"]}</td>'
            f'<td class="dim">Games won</td></tr>']
    for label, c, d, w, tops in cats:
        body.append(f'<tr><td class="dim">{esc(label)}</td><td class="vc{hi(w,"Cream")}">{c}</td>'
                    f'<td class="vc{hi(w,"Dumplings")}">{d}</td><td>{tops_html(tops)}</td></tr>')
    aw = []
    for label, lst, note in awards:
        team = lst[0][1] if lst else None
        aw.append(f'<div class="card"><div class="ct">{esc(label)}</div>{tops_html(lst) if lst else "<span class=dim>No data</span>"}'
                  f'<div class="note">{esc(note)}</div></div>')
    return f"""
<div class="tiles">
  <div class="tile"><div class="tv">{tiles['games']}</div><div class="tl">Games Played</div></div>
  <div class="tile"><div class="tv">{tiles['beers']}</div><div class="tl">Total Beers</div></div>
  <div class="tile"><div class="tv">{tiles['shotguns']}</div><div class="tl">Total Shotguns</div></div>
  <div class="tile"><div class="tv">{tiles['sinks']}</div><div class="tl">Total Sinks</div></div>
</div>
<div class="tile big"><div class="tl">Current Point Total</div>
  <div class="score"><span class="tc">Cream Team <b>{p['Cream']}</b></span><span class="dim">vs</span><span class="td"><b>{p['Dumplings']}</b> Dumplings</span></div>
  <div class="note">1 pt per category / award, {H2H_POINTS} pts for head-to-head. Ties score no point.</div></div>
<div class="wrap"><table class="team"><thead><tr><th>Category</th><th class="vc tc">Cream Team</th><th class="vc td">Dumplings</th><th>Top Individuals</th></tr></thead>
<tbody>{"".join(body)}</tbody></table></div>
<h3>Individual Awards <span class="dim">(point goes to the winner's team)</span></h3>
<div class="cards">{"".join(aw)}</div>"""

TEMPLATE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SNER 2026</title>
<style>
:root{--bg:#12141a;--pn:#1b1e27;--bd:#2c3140;--tx:#e8eaf0;--dim:#8b92a5;--cr:#f2c94c;--du:#5aa9ff;--hi:#2ecc71}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.4 system-ui,sans-serif;padding:16px;max-width:1200px;margin:auto}
h1{margin:0 0 4px}h3{margin:24px 0 8px}.dim{color:var(--dim)}.sub{color:var(--dim);margin-bottom:14px}
.tabs{display:flex;gap:8px;margin-bottom:14px}.tabs button,.tog button{background:var(--pn);color:var(--tx);border:1px solid var(--bd);padding:8px 14px;border-radius:8px;cursor:pointer}
.tabs button.on,.tog button.on{background:var(--du);color:#08111f;border-color:var(--du);font-weight:600}
.tog{display:flex;gap:6px}.bar{display:flex;gap:10px;align-items:center;margin-bottom:10px;flex-wrap:wrap}
input{background:var(--pn);color:var(--tx);border:1px solid var(--bd);border-radius:8px;padding:8px 10px}
.wrap{overflow-x:auto;border:1px solid var(--bd);border-radius:10px}table{border-collapse:collapse;width:100%;background:var(--pn)}
th,td{padding:8px 10px;border-bottom:1px solid var(--bd);text-align:left;white-space:nowrap}th{cursor:pointer;color:var(--dim);position:sticky;top:0;background:var(--pn)}
td.n,th.n{text-align:right}.vc{text-align:center}.hi{color:var(--hi);font-weight:700}
.tc{color:var(--cr)}.td{color:var(--du)}.tf{color:var(--dim)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:10px}
.tile{background:var(--pn);border:1px solid var(--bd);border-radius:10px;padding:14px;text-align:center}
.tv{font-size:28px;font-weight:700}.tl{color:var(--dim);text-transform:uppercase;font-size:12px;letter-spacing:.05em}
.tile.big{margin-bottom:14px;padding:22px;border-color:var(--du)}.score{display:flex;justify-content:center;gap:28px;align-items:center;font-size:22px;margin:8px 0}.score b{font-size:48px;margin:0 6px}
.note{color:var(--dim);font-size:12px;margin-top:6px}.pt{color:var(--dim);font-size:12px}
.team td{vertical-align:top;white-space:normal}.ti{white-space:nowrap}.rk{display:inline-block;width:16px;color:var(--dim)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}.card{background:var(--pn);border:1px solid var(--bd);border-radius:10px;padding:14px}.ct{font-weight:700;margin-bottom:8px}
.hide{display:none}
</style></head><body>
<h1>SNER 2026</h1><div class="sub">Snappa League · Updated __BUILT__</div>
<div class="tabs"><button class="on" data-t="q">Qualifiers</button><button data-t="t">Team Stats</button></div>

<div id="q">
 <div class="bar"><div class="tog"><button id="bq" class="on">Qualifiers</button><button id="ba">All</button></div>
 <input id="s" placeholder="Search player…"><span class="dim" id="cnt"></span></div>
 <div class="wrap"><table><thead id="h"></thead><tbody id="b"></tbody></table></div>
 <div class="note">Qualifiers = at least __MIN__ tosses (FGA). Click a header to sort.</div>
</div>
<div id="t" class="hide">__TEAM__</div>

<script>
var P=__PLAYERS__;
var COLS=[["name","Player"],["team","Team"],["gp","GP"],["mp","FGA"],["qSNER","qSNER","f2"],["sinks","Sinks"],["wr_pct","Win %","p"],
["shotguns","Shotguns"],["refs","Refs"],["ppg","PPG","f2"],["def_ratio","Def Ratio","f2"],["bpg","BPG","f2"],
["fg_pct","FG %","p"],["tfg_pct","TFG %","p"],["pts_def","Pts Def"],["ex_pts_def","Ex Pts Def"],["beers","Beers"]];
var showAll=false,sk="qSNER",sd=-1;
function fmt(v,f){if(v===null||v===undefined)return"—";if(f==="p")return(v*100).toFixed(1)+"%";if(f==="f2")return v.toFixed(2);return v}
function render(){
 var q=document.getElementById("s").value.toLowerCase();
 var d=P.filter(function(p){return(showAll||p.qualified)&&p.name.toLowerCase().indexOf(q)>-1});
 d.sort(function(a,b){var x=a[sk],y=b[sk];if(x==null)return 1;if(y==null)return-1;
  return(typeof x==="string"?x.localeCompare(y):x-y)*sd});
 document.getElementById("h").innerHTML="<tr>"+COLS.map(function(c){return'<th class="'+(c[0]=="name"||c[0]=="team"?"":"n")+'" data-k="'+c[0]+'">'+c[1]+(sk==c[0]?(sd>0?" ▲":" ▼"):"")+"</th>"}).join("")+"</tr>";
 document.getElementById("b").innerHTML=d.map(function(p){
  var tc=p.team=="Cream Team"?"tc":p.team=="Dumplings"?"td":"tf";
  return"<tr>"+COLS.map(function(c){var k=c[0];return'<td class="'+(k=="name"||k=="team"?(k=="team"?tc:""):"n")+'">'+fmt(p[k],c[2])+"</td>"}).join("")+"</tr>"}).join("");
 document.getElementById("cnt").textContent=d.length+" players";
}
document.getElementById("h").onclick=function(e){var k=e.target.dataset.k;if(!k)return;
 if(sk==k)sd=-sd;else{sk=k;sd=(k=="name"||k=="team")?1:-1}render()};
document.getElementById("s").oninput=render;
document.getElementById("bq").onclick=function(){showAll=false;this.classList.add("on");document.getElementById("ba").classList.remove("on");render()};
document.getElementById("ba").onclick=function(){showAll=true;this.classList.add("on");document.getElementById("bq").classList.remove("on");render()};
document.querySelectorAll(".tabs button").forEach(function(b){b.onclick=function(){
 document.querySelectorAll(".tabs button").forEach(function(x){x.classList.remove("on")});b.classList.add("on");
 document.getElementById("q").classList.toggle("hide",b.dataset.t!="q");document.getElementById("t").classList.toggle("hide",b.dataset.t!="t")}});
render();
</script></body></html>"""

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
    tiles, rec, h2h_winner, cats, awards = compute_team_stats(players, rows)
    built = date.today().strftime("%-m/%-d/%Y")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(build_html(players, tiles, rec, h2h_winner, cats, awards, built))
    print(f"✅ Done! Built {built}")

if __name__ == "__main__":
    main()
