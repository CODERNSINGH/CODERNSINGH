#!/usr/bin/env python3
"""Build the CODERNSINGH profile: every SVG under assets/ and the auto-updated README blocks.

Standard library only. Needs a GitHub token in GITHUB_TOKEN (or GH_TOKEN); locally it falls
back to `gh auth token`. Run from the repo root:  python scripts/build_profile.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import subprocess
import urllib.request
from collections import defaultdict
from html import escape
from pathlib import Path

# ---------------------------------------------------------------- config
LOGIN = os.environ.get("PROFILE_LOGIN", "CODERNSINGH")
NAME = "Narendra Singh"
OWN_ORGS = {"raindeer-social-org"}           # team products I build: shown as flagship, not "upstream"
HIDE_UPSTREAM = {"somraj112/Tutorial", "nsinghop/Final-Backend-of-Codesingh"}
MAX_ROWS_PER_REPO = 3
UPSTREAM_ROWS = 10
RECENT_ROWS = 6

# Nicer one-liners for repos whose GitHub description is empty or vague.
DESCRIPTIONS = {
    "turbo-chat": "Forktrix-Chat: real-time chat rooms in your terminal over Socket.io, runs with npx",
    "AutoSteer": "AI Editorial Studio: researches AI news, renders carousels + Manim reels, publishes after you approve",
    "SpaceXtra---SIH26162": "AGNIDRISHTI: finds industrial fires in NASA FIRMS + satellite data (SIH 2026)",
    "nstbuddy-Sage": "macOS app for nstbuddy, the go-to helper for NST questions",
    "nstbuddy-version-3": "nstbuddy v3: the go-to tool for NST question solutions",
    "codix": "Learn coding and maths by answering simple questions",
    "airis": "Notes and resources from my AIRIS sessions",
    "airis-lecture-01": "AIRIS lecture 01: intro to AI and the toolkit",
    "splitScreen": "Chrome extension that tiles real browser windows side by side",
    "spindly": "Expense tracker built with Claude Code",
}

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "assets" / "generated"
CARDS = ROOT / "assets" / "cards"

SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"

# GitHub's own palette (Primer), dark and light.
THEMES = {
    "dark": dict(
        bg="#0d1117", panel="#161b22", panel2="#0d1117", border="#30363d", text="#e6edf3",
        muted="#7d8590", faint="#21262d", accent="#3fb950", strong="#56d364", fill="#2ea043",
        levels=["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"], empty="#21262d",
    ),
    "light": dict(
        bg="#ffffff", panel="#f6f8fa", panel2="#ffffff", border="#d0d7de", text="#1f2328",
        muted="#656d76", faint="#eaeef2", accent="#1a7f37", strong="#2da44e", fill="#2da44e",
        levels=["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"], empty="#ebedf0",
    ),
}
LEVEL = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


# ---------------------------------------------------------------- GitHub API
def token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


TOKEN = None


def gql(query: str, **variables) -> dict:
    global TOKEN
    TOKEN = TOKEN or token()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-builder"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]


USER_Q = """
query($login:String!){ user(login:$login){
  name bio company location followers{totalCount}
  all: repositories(ownerAffiliations:OWNER, privacy:PUBLIC){ totalCount }
  repos: repositories(ownerAffiliations:OWNER, privacy:PUBLIC, isFork:false, first:100,
                      orderBy:{field:PUSHED_AT, direction:DESC}){
    nodes{ name description url pushedAt stargazerCount
           primaryLanguage{ name color }
           languages(first:10, orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name color } } } } }
  contributionsCollection{
    totalCommitContributions totalIssueContributions totalPullRequestContributions
    totalPullRequestReviewContributions restrictedContributionsCount
    contributionCalendar{ totalContributions
      weeks{ contributionDays{ date contributionCount contributionLevel weekday } } } } } }
"""

PR_Q = """
query($q:String!, $after:String){ search(query:$q, type:ISSUE, first:100, after:$after){
  pageInfo{ hasNextPage endCursor }
  nodes{ ... on PullRequest{ title url state merged createdAt
         repository{ nameWithOwner stargazerCount owner{ login } } } } } }
"""


def fetch():
    user = gql(USER_Q, login=LOGIN)["user"]
    prs, after = [], None
    while True:
        s = gql(PR_Q, q=f"author:{LOGIN} is:pr is:public", after=after)["search"]
        prs += [n for n in s["nodes"] if n]
        if not s["pageInfo"]["hasNextPage"]:
            break
        after = s["pageInfo"]["endCursor"]
    return user, prs


# ---------------------------------------------------------------- helpers
def e(s) -> str:
    return escape(str(s), quote=True)


def kfmt(n: int) -> str:
    return f"{n/1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def ago(iso: str, today: dt.date) -> str:
    d = (today - dt.date.fromisoformat(iso[:10])).days
    if d <= 0:
        return "today"
    if d == 1:
        return "yesterday"
    if d < 14:
        return f"{d} days ago"
    if d < 60:
        return f"{d // 7} weeks ago"
    return f"{d // 30} months ago"


def svg(w: int, h: int, body: str, t: dict, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{e(title)}"><title>{e(title)}</title>'
        f'<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" fill="{t["accent"]}"/></marker></defs>'
        f"{body}</svg>\n"
    )


def text(x, y, s, t, size=14, color=None, weight=400, anchor="start", font=SANS, extra=""):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{font}" font-size="{size}" font-weight="{weight}" '
        f'fill="{color or t["text"]}" text-anchor="{anchor}" {extra}>{e(s)}</text>'
    )


def shade(hex_color: str, k: float) -> str:
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * k))) for c in (r, g, b))


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------- derived stats
def calendar_days(user):
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [d for w in weeks for d in w["contributionDays"]], weeks


def streaks(days, today: dt.date):
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] else 0
        longest = max(longest, run)
    current = 0
    for d in reversed(days):
        if dt.date.fromisoformat(d["date"]) >= today and not d["contributionCount"]:
            continue  # today isn't over yet
        if not d["contributionCount"]:
            break
        current += 1
    return current, longest


def activity_split(user):
    c = user["contributionsCollection"]
    parts = {
        "Commits": c["totalCommitContributions"],
        "Issues": c["totalIssueContributions"],
        "Pull requests": c["totalPullRequestContributions"],
        "Code review": c["totalPullRequestReviewContributions"],
    }
    total = sum(parts.values()) or 1
    return {k: (v, round(100 * v / total)) for k, v in parts.items()}


def language_mix(user, top=6):
    """Main language of each of my own repos. Counting bytes would let notebook outputs win."""
    count, color = defaultdict(int), {}
    for r in user["repos"]["nodes"]:
        lang = r["primaryLanguage"]
        if lang:
            count[lang["name"]] += 1
            color[lang["name"]] = lang["color"] or "#8b949e"
    total = sum(count.values()) or 1
    ranked = sorted(count.items(), key=lambda kv: -kv[1])
    out = [(n, c / total, color[n]) for n, c in ranked[:top]]
    rest = sum(c for _, c in ranked[top:]) / total
    if rest > 0:
        out.append(("Other", rest, "#8b949e"))
    return out


# ---------------------------------------------------------------- header
def header_svg(t, user, days, prs, today):
    W, H = 1200, 400
    b = [f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="16" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="2"/>']
    # left: identity
    b.append(text(56, 74, f"~/{LOGIN}", t, 16, t["accent"], 600, font=MONO))
    b.append(text(52, 140, NAME, t, 62, weight=700))
    b.append(text(56, 182, "AI engineer · agent pipelines · open source", t, 22, t["muted"]))
    b.append(text(56, 222, "Bangalore, India · building at Forktrix Labs", t, 17, t["muted"]))
    # right: terminal with my latest real pull requests
    tx, ty, tw, th = 660, 40, 500, 216
    b.append(f'<rect x="{tx}" y="{ty}" width="{tw}" height="{th}" rx="10" fill="{t["panel"]}" stroke="{t["border"]}"/>')
    for i, c in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        b.append(f'<circle cx="{tx+20+i*18}" cy="{ty+18}" r="5.5" fill="{c}"/>')
    b.append(text(tx + tw / 2, ty + 23, f"{LOGIN.lower()}@github: ~", t, 12, t["muted"], anchor="middle", font=MONO))
    b.append(f'<line x1="{tx}" y1="{ty+34}" x2="{tx+tw}" y2="{ty+34}" stroke="{t["border"]}"/>')
    lines = [("$ ", "gh pr list --author @me --limit 3", t["text"])]
    for pr in sorted(prs, key=lambda p: p["createdAt"], reverse=True)[:3]:
        mark = "✓" if pr["merged"] else ("●" if pr["state"] == "OPEN" else "×")
        repo = pr["repository"]["nameWithOwner"].split("/")[1]
        title = re.sub(r"^(\[[^\]]+\])+\s*", "", pr["title"])
        lines.append((f"{mark} ", trunc(f"{repo}: {title}", 48), t["muted"]))
    lines.append(("$ ", "make it_compile", t["text"]))
    lines.append(("✓ ", "trust me it compiles ;)", t["accent"]))
    y = ty + 60
    for prefix, body, col in lines:
        b.append(
            f'<text x="{tx+18}" y="{y}" font-family="{MONO}" font-size="13.5">'
            f'<tspan fill="{t["accent"]}" font-weight="700">{e(prefix)}</tspan><tspan fill="{col}">{e(body)}</tspan></text>'
        )
        y += 25
    cx = tx + 18 + 8.1 * (2 + len("trust me it compiles ;)")) + 4
    b.append(
        f'<rect x="{cx:.0f}" y="{y-25-13}" width="9" height="16" fill="{t["accent"]}">'
        f'<animate attributeName="opacity" values="1;1;0;0" dur="1.1s" repeatCount="indefinite"/></rect>'
    )
    # bottom: the real contribution grid of the last year
    cell, gap = 12, 3
    gx, gy = 56, 280
    col = 0
    for d in days:
        wd = d["weekday"]
        if wd == 0 and d is not days[0]:
            col += 1
        lv = LEVEL.get(d["contributionLevel"], 0)
        fill = t["empty"] if lv == 0 else t["levels"][lv]
        b.append(f'<rect x="{gx+col*(cell+gap)}" y="{gy+wd*(cell+gap) - 2}" width="{cell}" height="{cell}" rx="2.5" fill="{fill}"/>')
    total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    merged = sum(1 for p in prs if p["merged"])
    sx = gx + (col + 1) * (cell + gap) + 24
    b.append(text(sx, gy + 22, kfmt(total), t, 40, t["accent"], 700))
    b.append(text(sx, gy + 46, "contributions in the last year", t, 14, t["muted"]))
    b.append(text(sx, gy + 84, f"{merged} merged PRs · {user['all']['totalCount']} public repos", t, 14, t["muted"]))
    return svg(W, H, "".join(b), t, f"{NAME}: AI engineer, agent pipelines, open source")


# ---------------------------------------------------------------- activity overview (radar)
def activity_svg(t, split):
    W, H = 1200, 480
    cx, cy, R = 330, 270, 130
    b = [f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="16" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="2"/>']
    b.append(text(40, 52, "Activity overview", t, 22, weight=600))
    b.append(text(40, 78, "share of commits, issues, pull requests and code review · last 12 months", t, 14, t["muted"]))
    axes = {"Code review": (0, -1), "Issues": (1, 0), "Pull requests": (0, 1), "Commits": (-1, 0)}
    top = max(p for _, p in split.values()) or 1
    for name, (dx, dy) in axes.items():
        b.append(f'<line x1="{cx}" y1="{cy}" x2="{cx+dx*R}" y2="{cy+dy*R}" stroke="{t["accent"]}" stroke-width="2.5" stroke-linecap="round"/>')
    pts = []
    for name, (dx, dy) in axes.items():
        r = max(10, R * split[name][1] / top)
        pts.append((cx + dx * r, cy + dy * r))
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    b.append(f'<polygon points="{poly}" fill="{t["fill"]}" fill-opacity="0.55" stroke="{t["strong"]}" stroke-width="2.5" stroke-linejoin="round"/>')
    for x, y in pts:
        b.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{t["bg"]}" stroke="{t["strong"]}" stroke-width="3"/>')
    lab = {
        "Code review": (cx, cy - R - 34, "middle"),
        "Issues": (cx + R + 52, cy - 6, "middle"),
        "Pull requests": (cx, cy + R + 30, "middle"),
        "Commits": (cx - R - 56, cy - 6, "middle"),
    }
    for name, (x, y, a) in lab.items():
        b.append(text(x, y, f"{split[name][1]}%", t, 20, t["muted"], 500, a))
        b.append(text(x, y + 24, name, t, 18, t["muted"], 400, a))
    # right: the raw numbers as bars
    x0, y0, bw = 680, 168, 460
    for i, (name, (count, pct)) in enumerate(sorted(split.items(), key=lambda kv: -kv[1][0])):
        y = y0 + i * 74
        b.append(text(x0, y, name, t, 16, weight=600))
        b.append(text(x0 + bw, y, f"{count:,}  ·  {pct}%", t, 15, t["muted"], anchor="end", font=MONO))
        b.append(f'<rect x="{x0}" y="{y+12}" width="{bw}" height="12" rx="6" fill="{t["faint"]}"/>')
        b.append(f'<rect x="{x0}" y="{y+12}" width="{max(12, bw*pct/100):.1f}" height="12" rx="6" fill="{t["levels"][4 - min(i,3)]}"/>')
    return svg(W, H, "".join(b), t, "Activity overview: share of commits, issues, pull requests and code review")


# ---------------------------------------------------------------- ship log (weekly bars, streaks, languages)
def shiplog_svg(t, user, days, weeks, langs, today):
    W, H = 1200, 560
    b = [f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="16" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="2"/>']
    b.append(text(40, 52, "Ship log", t, 22, weight=600))
    b.append(text(40, 78, "every week of the last 12 months, drawn from my contribution calendar", t, 14, t["muted"]))
    cur, longest = streaks(days, today)
    busiest = max(days, key=lambda d: d["contributionCount"])
    active = sum(1 for d in days if d["contributionCount"])
    total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    tiles = [
        (f"{total:,}", "contributions"),
        (f"{active}", "active days"),
        (f"{cur} d", "current streak"),
        (f"{longest} d", "longest streak"),
        (f"{busiest['contributionCount']}", "busiest day · " + dt.date.fromisoformat(busiest["date"]).strftime("%d %b")),
    ]
    tw = (W - 80 - 4 * 16) / 5
    for i, (big, small) in enumerate(tiles):
        x = 40 + i * (tw + 16)
        b.append(f'<rect x="{x:.1f}" y="100" width="{tw:.1f}" height="86" rx="10" fill="{t["panel"]}" stroke="{t["border"]}"/>')
        b.append(text(x + 18, 146, big, t, 30, t["accent"], 700))
        b.append(text(x + 18, 172, small, t, 13, t["muted"]))
    # weekly bars
    sums = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]
    top = max(sums) or 1
    cx0, cy0, cw, ch = 70, 222, W - 110, 200
    for k in range(5):
        v = round(top * k / 4)
        y = cy0 + ch - ch * k / 4
        b.append(f'<line x1="{cx0}" y1="{y:.1f}" x2="{cx0+cw}" y2="{y:.1f}" stroke="{t["faint"]}"/>')
        b.append(text(cx0 - 10, y + 4, v, t, 11, t["muted"], anchor="end", font=MONO))
    step = cw / len(sums)
    seen = set()
    for i, (s, w) in enumerate(zip(sums, weeks)):
        h = max(2, ch * s / top)
        lv = 0 if s == 0 else 1 + min(3, int(4 * s / (top + 1)))
        x = cx0 + i * step + step * 0.15
        b.append(f'<rect x="{x:.1f}" y="{cy0+ch-h:.1f}" width="{step*0.7:.1f}" height="{h:.1f}" rx="2" fill="{t["levels"][lv] if lv else t["empty"]}"><title>week of {w["contributionDays"][0]["date"]}: {s}</title></rect>')
        first = dt.date.fromisoformat(w["contributionDays"][0]["date"])
        m = first.strftime("%b")
        if first.day <= 7 and m not in seen:
            seen.add(m)
            b.append(text(x, cy0 + ch + 20, m, t, 12, t["muted"]))
    # language mix
    ly = 480
    b.append(text(40, ly - 18, "Main language of each repository I own", t, 14, t["muted"]))
    x = 40.0
    lw = W - 80
    for name, frac, color in langs:
        w_ = lw * frac
        b.append(f'<rect x="{x:.1f}" y="{ly-6}" width="{max(w_-2,1):.1f}" height="12" fill="{color}"/>')
        x += w_
    lx = 40
    for name, frac, color in langs:
        label = f"{name} {frac*100:.1f}%"
        b.append(f'<circle cx="{lx+6}" cy="{ly+30}" r="6" fill="{color}"/>')
        b.append(text(lx + 18, ly + 35, label, t, 13, t["text"]))
        lx += 26 + len(label) * 7.6
    return svg(W, H, "".join(b), t, "Ship log: weekly contributions, streaks and language mix")


# ---------------------------------------------------------------- skyline
def skyline_svg(t, days, today):
    W, H = 1200, 540
    b = [f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="16" fill="{t["bg"]}" stroke="{t["border"]}" stroke-width="2"/>']
    wv, dv = (16.0, 4.0), (-9.0, 9.0)  # one week step, one day step
    top = max(d["contributionCount"] for d in days) or 1
    ox, oy = 210.0, 190.0
    cells = []
    col = 0
    for d in days:
        if d["weekday"] == 0 and d is not days[0]:
            col += 1
        cells.append((col, d["weekday"], d))
    ncol = col + 1

    def P(c, r, h=0.0):
        return (ox + c * wv[0] + r * dv[0], oy + c * wv[1] + r * dv[1] - h)

    def poly(pts, fill, extra=""):
        return f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="{fill}" {extra}/>'

    # base plate
    pad, depth = 1.2, 18
    a, bb, c, d = P(-pad, -pad), P(ncol + pad, -pad), P(ncol + pad, 7 + pad), P(-pad, 7 + pad)
    b.append(poly([a, bb, c, d], t["panel"], f'stroke="{t["border"]}"'))
    b.append(poly([d, c, (c[0], c[1] + depth), (d[0], d[1] + depth)], shade(t["panel"], 0.8) if t is THEMES["light"] else t["faint"], f'stroke="{t["border"]}"'))
    b.append(poly([bb, c, (c[0], c[1] + depth), (bb[0], bb[1] + depth)], t["faint"], f'stroke="{t["border"]}"'))
    # front-face label, skewed along the plate edge
    ang = math.degrees(math.atan2(wv[1], wv[0]))
    b.append(
        f'<text transform="translate({d[0]+40:.1f},{d[1]+13:.1f}) rotate({ang:.2f})" font-family="{MONO}" font-size="11" '
        f'fill="{t["muted"]}" letter-spacing="2">{e(LOGIN)} · {e(days[0]["date"][:7])} → {e(days[-1]["date"][:7])}</text>'
    )
    for c_, r_, day in sorted(cells, key=lambda x: (x[0] + x[1], x[1])):
        n = day["contributionCount"]
        lv = LEVEL.get(day["contributionLevel"], 0)
        h = 2 if n == 0 else 6 + 120 * math.sqrt(n / top)
        base = t["empty"] if lv == 0 else t["levels"][lv]
        s = 0.12  # small inset so towers read as separate blocks
        c0, c1, r0, r1 = c_ + s, c_ + 1 - s, r_ + s, r_ + 1 - s
        topf = [P(c0, r0, h), P(c1, r0, h), P(c1, r1, h), P(c0, r1, h)]
        front = [P(c0, r1, h), P(c1, r1, h), P(c1, r1), P(c0, r1)]
        right = [P(c1, r0, h), P(c1, r1, h), P(c1, r1), P(c1, r0)]
        b.append(poly(front, shade(base, 0.72)))
        b.append(poly(right, shade(base, 0.55)))
        b.append(poly(topf, base))
    b.append(text(40, 52, "Contribution skyline", t, 22, weight=600))
    b.append(text(40, 78, "one tower per day · height = contributions", t, 14, t["muted"]))
    return svg(W, H, "".join(b), t, "3D skyline of my contribution calendar")


# ---------------------------------------------------------------- project cards
OCTO_REPO = (
    "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.249.249 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z"
)


def node(t, x, y, w, h, title, sub="", hl=False, size=13):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{t["panel2"]}" stroke="{t["accent"] if hl else t["border"]}" stroke-width="{2 if hl else 1}"/>']
    if sub:
        out.append(text(x + w / 2, y + h / 2 - 2, title, t, size, weight=700, anchor="middle"))
        out.append(text(x + w / 2, y + h / 2 + 14, sub, t, 10.5, t["muted"], anchor="middle"))
    else:
        out.append(text(x + w / 2, y + h / 2 + 4.5, title, t, size, weight=600, anchor="middle"))
    return "".join(out)


def arrow(t, x1, y1, x2, y2, curve=False, dashed=False):
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    if curve:
        mx = (x1 + x2) / 2
        d = f"M{x1} {y1} C{mx} {y1} {mx} {y2} {x2} {y2}"
    else:
        d = f"M{x1} {y1} L{x2} {y2}"
    return f'<path d="{d}" fill="none" stroke="{t["accent"]}" stroke-width="1.6"{dash} marker-end="url(#arr)"/>'


def card(t, owner, repo, badge, caption, body, title):
    W, H = 600, 300
    b = [f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="12" fill="{t["panel"]}" stroke="{t["border"]}" stroke-width="2"/>']
    b.append(f'<g transform="translate(22 19)"><path d="{OCTO_REPO}" fill="{t["muted"]}"/></g>')
    b.append(
        f'<text x="46" y="32" font-family="{SANS}" font-size="16"><tspan fill="{t["muted"]}">{e(owner)} / </tspan>'
        f'<tspan fill="{t["accent"]}" font-weight="700">{e(repo)}</tspan></text>'
    )
    bw = 18 + len(badge) * 7
    b.append(f'<rect x="{W-22-bw}" y="15" width="{bw}" height="24" rx="12" fill="none" stroke="{t["accent"]}"/>')
    b.append(text(W - 22 - bw / 2, 31.5, badge, t, 12, t["accent"], 600, "middle"))
    b.append(f'<line x1="0" y1="54" x2="{W}" y2="54" stroke="{t["border"]}"/>')
    b.append(body)
    b.append(text(W / 2, H - 18, caption, t, 12.5, t["muted"], anchor="middle", font=MONO))
    return svg(W, H, "".join(b), t, title)


def card_raindeer(t, merged):
    agents = [("Aarav", "onboarding"), ("Ved", "research"), ("Keshav", "creative"), ("Kavi", "generation"), ("Neer", "review")]
    w, gap, x0, y = 96, 18, 24, 72
    out = []
    for i, (n, role) in enumerate(agents):
        x = x0 + i * (w + gap)
        out.append(node(t, x, y, w, 54, n, role, hl=i == 4, size=14))
        if i:
            out.append(arrow(t, x - gap + 1, y + 27, x - 2, y + 27))
    nx = x0 + 4 * (w + gap) + w / 2
    out.append(arrow(t, nx, y + 56, nx, 150))
    out.append(f'<rect x="24" y="152" width="552" height="34" rx="8" fill="{t["panel2"]}" stroke="{t["accent"]}" stroke-dasharray="5 4"/>')
    out.append(text(300, 174, "human review queue · approve · edit · regenerate", t, 13, weight=600, anchor="middle"))
    out.append(arrow(t, 300, 188, 300, 208))
    chips = ["LinkedIn", "X", "Instagram", "Threads", "Facebook"]
    cw = (552 - 4 * 10) / 5
    for i, c in enumerate(chips):
        x = 24 + i * (cw + 10)
        out.append(f'<rect x="{x:.1f}" y="212" width="{cw:.1f}" height="30" rx="15" fill="{t["levels"][2 if t is THEMES["dark"] else 1]}"/>')
        out.append(text(x + cw / 2, 232, c, t, 12.5, t["text"] if t is THEMES["dark"] else "#0d1117", 600, "middle"))
    return card(t, "raindeer-social-org", "raindeer-social", f"{merged} merged PRs",
                "FastAPI · LangGraph · Postgres+pgvector · Celery · Next.js", "".join(out),
                "Raindeer Social: five LangGraph agents from brand research to a published post")


def card_hireflow(t, merged):
    cx, cy, rx, ry = 300, 156, 214, 76
    steps = ["Discover", "Score", "Confirm", "Tailor", "Apply", "Report"]
    out = [
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="{t["accent"]}" stroke-width="2" stroke-dasharray="7 6">'
        f'<animate attributeName="stroke-dashoffset" from="0" to="-26" dur="1.2s" repeatCount="indefinite"/></ellipse>'
    ]
    out.append(text(cx, cy - 4, "weekly cycle", t, 17, t["accent"], 700, "middle"))
    out.append(text(cx, cy + 16, "nothing is sent without your OK", t, 12, t["muted"], anchor="middle"))
    for i, s in enumerate(steps):
        a = math.radians(-90 + i * 60)
        x, y = cx + rx * math.cos(a), cy + ry * math.sin(a)
        out.append(node(t, round(x - 46), round(y - 16), 92, 32, s, hl=s == "Confirm", size=13))
    return card(t, "newton-school-ai", "hireflow-ai", f"{merged} merged PRs",
                "Python · scraping agents · Docker · CI", "".join(out),
                "HireFlow AI: discover, score, confirm, tailor, apply and report every week")


def card_studio(t):
    out = [
        node(t, 20, 128, 96, 50, "Research", "AI news + tools"),
        node(t, 146, 80, 112, 50, "Carousel", "Instagram slides"),
        node(t, 146, 176, 112, 50, "Reel", "Manim animation"),
        node(t, 288, 128, 92, 50, "Quality", "score gate"),
        node(t, 404, 128, 92, 50, "You", "approve", hl=True),
        node(t, 516, 128, 64, 50, "Post", "Graph API"),
        arrow(t, 117, 153, 144, 105, curve=True), arrow(t, 117, 153, 144, 201, curve=True),
        arrow(t, 259, 105, 286, 153, curve=True), arrow(t, 259, 201, 286, 153, curve=True),
        arrow(t, 381, 153, 402, 153), arrow(t, 497, 153, 514, 153),
        f'<path d="M334 180 C334 246 202 246 202 230" fill="none" stroke="{t["muted"]}" stroke-width="1.3" stroke-dasharray="4 4" marker-end="url(#arr)"/>',
        text(268, 252, "below threshold → rebuild", t, 11, t["muted"], anchor="middle"),
    ]
    return card(t, LOGIN, "AutoSteer", "local-first",
                "FastAPI · React · Manim · SQLite · pytest", "".join(out),
                "AI Editorial Studio: research, carousel and reel, quality gate, approval, publish")


def card_agni(t):
    out = []
    srcs = [("NASA FIRMS", "live hotspots"), ("OpenStreetMap", "industrial sites"), ("Satellite", "imagery")]
    for i, (a, s) in enumerate(srcs):
        y = 70 + i * 60
        out.append(node(t, 20, y, 150, 46, a, s))
        out.append(arrow(t, 171, y + 23, 228, 155, curve=True))
    out.append(node(t, 230, 124, 140, 62, "Classifier", "scikit-learn", hl=True, size=15))
    outs = [("Industrial fire", 92), ("Persistent thermal", 176)]
    for label, y in outs:
        out.append(arrow(t, 371, 155, 418, y + 22, curve=True))
        out.append(f'<rect x="420" y="{y}" width="160" height="44" rx="8" fill="{t["panel2"]}" stroke="{t["border"]}"/>')
        out.append(
            f'<circle cx="440" cy="{y+22}" r="6" fill="#f85149"><animate attributeName="r" values="4;8;4" dur="1.6s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="1;.35;1" dur="1.6s" repeatCount="indefinite"/></circle>'
        )
        out.append(text(456, y + 27, label, t, 13, weight=600))
    out.append(text(500, 248, "runs with zero API keys", t, 11, t["muted"], anchor="middle"))
    return card(t, LOGIN, "AGNIDRISHTI", "SIH 2026",
                "FastAPI · scikit-learn · NASA FIRMS · OSM", "".join(out),
                "AGNIDRISHTI: NASA FIRMS, OpenStreetMap and satellite data into a fire classifier")


# ---------------------------------------------------------------- README blocks
def replace_block(readme: str, tag: str, content: str) -> str:
    pat = re.compile(rf"(<!--{tag}:START-->\n).*?(<!--{tag}:END-->)", re.S)
    if not pat.search(readme):
        raise SystemExit(f"README is missing the {tag} markers")
    return pat.sub(lambda m: m.group(1) + content + "\n" + m.group(2), readme)


def upstream_block(prs):
    ups = [
        p for p in prs
        if p["repository"]["owner"]["login"] != LOGIN
        and p["repository"]["owner"]["login"] not in OWN_ORGS
        and p["repository"]["nameWithOwner"] not in HIDE_UPSTREAM
        and (p["merged"] or p["state"] == "OPEN")
    ]
    merged = sum(1 for p in ups if p["merged"])
    review = sum(1 for p in ups if p["state"] == "OPEN")
    repos = {p["repository"]["nameWithOwner"] for p in ups}
    rows, per = [], defaultdict(int)
    for p in sorted(ups, key=lambda p: p["createdAt"], reverse=True):
        r = p["repository"]
        if per[r["nameWithOwner"]] >= MAX_ROWS_PER_REPO:
            continue
        per[r["nameWithOwner"]] += 1
        owner = r["owner"]["login"]
        status = "🟣&nbsp;merged" if p["merged"] else "🟢&nbsp;in&nbsp;review"
        when = dt.date.fromisoformat(p["createdAt"][:10]).strftime("%b %Y")
        title = trunc(p["title"], 90).replace("|", "\\|")
        stars = f' <sub>★ {kfmt(r["stargazerCount"])}</sub>' if r["stargazerCount"] else ""
        rows.append(
            f'| <img src="https://github.com/{owner}.png?size=40" width="20" height="20" alt="{owner}"> '
            f'| [{r["nameWithOwner"]}](https://github.com/{r["nameWithOwner"]}){stars} '
            f"| [{title}]({p['url']}) | {status} | {when} |"
        )
        if len(rows) >= UPSTREAM_ROWS:
            break
    head = (
        f"**{merged} merged · {review} in review · {len(repos)} repositories** <sub>(auto-updated daily)</sub>\n\n"
        "| | project | pull request | status | opened |\n|:-:|:--|:--|:--|:--|"
    )
    return head + "\n" + "\n".join(rows)


def recent_block(user, today):
    rows = []
    for r in user["repos"]["nodes"]:
        if r["name"] == LOGIN:
            continue
        desc = DESCRIPTIONS.get(r["name"]) or (r["description"] or "").strip()
        if not desc:
            continue
        lang = (r["primaryLanguage"] or {}).get("name", "—")
        rows.append(
            f"| [**{r['name']}**]({r['url']}) | {trunc(desc, 95).replace('|', '/')} | `{lang}` | {ago(r['pushedAt'], today)} |"
        )
        if len(rows) >= RECENT_ROWS:
            break
    return "| repo | what | lang | pushed |\n|:--|:--|:--|:--|\n" + "\n".join(rows)


def card_block(user, prs, days, langs, today):
    cur, longest = streaks(days, today)
    c = user["contributionsCollection"]
    upstream = sorted(
        {p["repository"]["nameWithOwner"] for p in prs
         if p["repository"]["owner"]["login"] not in OWN_ORGS | {LOGIN}
         and p["repository"]["nameWithOwner"] not in HIDE_UPSTREAM and (p["merged"] or p["state"] == "OPEN")},
        key=lambda n: n.lower(),
    )
    data = {
        "login": LOGIN,
        "name": NAME,
        "bio": user["bio"],
        "company": user["company"],
        "location": user["location"],
        "building": ["Raindeer Social", "HireFlow AI", "AI Editorial Studio", "AGNIDRISHTI"],
        "contributes_to": upstream,
        "languages": [n for n, _, _ in langs if n != "Other"],
        "stats": {
            "public_repos": user["all"]["totalCount"],
            "contributions_last_12mo": c["contributionCalendar"]["totalContributions"],
            "pull_requests_merged": sum(1 for p in prs if p["merged"]),
            "current_streak_days": cur,
            "longest_streak_days": longest,
            "followers": user["followers"]["totalCount"],
        },
        "open_to": ["agent pipelines", "open-source bugs", "pairing on an issue"],
        "updated_at": today.isoformat(),
    }
    return "```json\n" + json.dumps(data, indent=2, ensure_ascii=False) + "\n```"


# ---------------------------------------------------------------- main
def main():
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()
    user, prs = fetch()
    days, weeks = calendar_days(user)
    split = activity_split(user)
    langs = language_mix(user)

    merged_by = defaultdict(int)
    for p in prs:
        if p["merged"]:
            r = p["repository"]
            key = r["owner"]["login"] if r["owner"]["login"] in OWN_ORGS else r["nameWithOwner"]
            merged_by[key] += 1

    for mode, t in THEMES.items():
        write(ROOT / "assets" / f"header-{mode}.svg", header_svg(t, user, days, prs, today))
        write(GEN / f"activity-{mode}.svg", activity_svg(t, split))
        write(GEN / f"shiplog-{mode}.svg", shiplog_svg(t, user, days, weeks, langs, today))
        write(GEN / f"skyline-{mode}.svg", skyline_svg(t, days, today))
        write(CARDS / f"raindeer-{mode}.svg", card_raindeer(t, merged_by["raindeer-social-org"]))
        write(CARDS / f"hireflow-{mode}.svg", card_hireflow(t, merged_by["newton-school-ai/hireflow-ai_1"]))
        write(CARDS / f"studio-{mode}.svg", card_studio(t))
        write(CARDS / f"agnidrishti-{mode}.svg", card_agni(t))

    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    readme = replace_block(readme, "UPSTREAM", upstream_block(prs))
    readme = replace_block(readme, "RECENT", recent_block(user, today))
    readme = replace_block(readme, "CARD", card_block(user, prs, days, langs, today))
    readme_path.write_text(readme, encoding="utf-8")
    print(f"built profile for {LOGIN}: {len(prs)} PRs, {len(days)} days, activity {split}")


if __name__ == "__main__":
    main()
