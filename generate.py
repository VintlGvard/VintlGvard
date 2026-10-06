#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from github import Auth, Github
from github.GithubRetry import GithubRetry


USER = "VintlGvard"
SHOWCASE = ("portfolio-v3", "Steam_PricePerHour", "breweryx-recipe-gen")


SKILLS = ("JavaScript", "Python", "Go",
          "TypeScript", "React", "Node.js", "Django", "Tailwind", "FastAPI",
          "Webpack", "PostgreSQL", "Docker", "Linux", "Bash", "Git",
          "MySQL", "SQLite", "Nginx", "Electron")
SKILLS_CORE = ("JavaScript", "Python", "Go")
CONTACTS = (
    ("plane", "@VintlGvard", "telegram"),
    ("globe", "vintlgvard.com", "website"),
    ("mail", "me@vintlgvard.com", "email"),
    ("git", "github.com/VintlGvard", "github"),
)
REPLY_NOTE = "reply < 24h"
DIVIDER_X = 450
CHIP_LIMIT = 434
SHOWCASE_BOOST = 40
STAR_WEIGHT = 3
FRESH_WINDOW_DAYS = 30
WIDTH = 900

TITLES = {
    "hero": "VintlGvard — Fullstack product engineer",
    "contact": "VintlGvard contact",
    "shipping": "VintlGvard shipping — IDEA to RUN",
    "stack": "VintlGvard languages",
    "stats": "VintlGvard GitHub stats",
}
BENTO_TITLE = "VintlGvard — mission control profile"

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#07090D", "card0": "#121925", "card1": "#0B1017",
        "head0": "#18212E", "head1": "#111720",
        "text": "#E8EEF4", "muted": "#8B95A5", "dim": "#5B6472",
        "accent": "#00E5CC", "accent2": "#7C5CFF", "green": "#38D996",
        "sheet": "#FFFFFF", "grid": "#FFFFFF", "track": "#FFFFFF",
    },
}

SCRIPT_DIR = Path(__file__).resolve().parent


def resolve_root(cli_root: str | None) -> Path:
    raw = cli_root or os.environ.get("PROFILE_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    return SCRIPT_DIR


def esc(value) -> str:
    return (str(value if value is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def char_units(text: str) -> float:
    units = 0.0
    for ch in text:
        if ch.isspace():
            units += 0.48
        elif ord(ch) > 127:
            units += 1.22
        elif ch in "MW@#%&":
            units += 1.18
        elif ch in "ilI.,:;!'|`":
            units += 0.44
        elif ch.isupper():
            units += 0.94
        else:
            units += 0.82
    return units


def truncate(value, max_chars: int, max_units: float | None = None) -> str:
    text = " ".join(str(value or "").split())
    if max_units is None:
        max_units = float(max_chars)
    if len(text) <= max_chars and char_units(text) <= max_units:
        return text
    out: list[str] = []
    for ch in text:
        candidate = "".join(out) + ch + "…"
        if len(candidate) > max_chars or char_units(candidate) > max_units:
            break
        out.append(ch)
    return ("".join(out).rstrip() + "…") if out else "…"


def fmt_date(iso) -> str:
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d %b %Y")
    except ValueError:
        return "—"







def repo_score(repo: dict, now: date) -> float:
    stars = int(repo.get("stargazers_count") or 0)
    try:
        pushed = date.fromisoformat(str(repo.get("pushed_at") or "")[:10])
        fresh = max(0, FRESH_WINDOW_DAYS - (now - pushed).days)
    except ValueError:
        fresh = 0
    boost = SHOWCASE_BOOST if repo.get("name") in SHOWCASE else 0
    return stars * STAR_WEIGHT + fresh + boost


def choose_shipping(
    repos: list, now: date | None = None
) -> list:
    day = now or date.today()
    candidates = [
        r for r in repos
        if not r.get("archived") and not r.get("fork") and r.get("name") != USER
    ]
    candidates.sort(key=lambda r: repo_score(r, day), reverse=True)
    return candidates[:3]


def primary_counts(repos: list) -> dict:
    counter = defaultdict(int)
    for repo in repos:
        if repo.get("fork") or repo.get("archived") or repo.get("name") == USER:
            continue
        if repo.get("language"):
            counter[str(repo["language"])] += 1
    return counter


def load_cache(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(path: Path, cache: dict) -> None:
    try:
        path.write_text(json.dumps(cache, separators=(",", ":")),
                        encoding="utf-8")
    except OSError as exc:
        print(f"[warn] language cache write failed: {exc}", file=sys.stderr)


def aggregate_languages(
    repos: list, gh: Github, cache: dict
) -> tuple[list[tuple[str, float]], str, int, int]:
    bytes_by_lang = defaultdict(int)
    fetched = reused = failed = 0
    for repo in repos:
        if repo.get("fork") or repo.get("archived") or repo.get("name") == USER:
            continue
        name = repo.get("name")
        if not name or not repo.get("size"):
            continue
        stamp = str(repo.get("pushed_at") or "")
        hit = cache.get(name)
        if isinstance(hit, dict) and hit.get("pushed") == stamp and hit.get("langs"):
            payload, reused = hit["langs"], reused + 1
        else:
            try:
                payload = gh.get_repo(f"{USER}/{name}").get_languages()
                cache[name] = {"pushed": stamp, "langs": payload}
                fetched += 1
            except Exception as exc:
                failed += 1
                print(f"[warn] languages/{name}: {exc}", file=sys.stderr)
                continue
        for key, value in payload.items():
            if isinstance(value, int) and value > 0:
                bytes_by_lang[str(key)] += value
    if bytes_by_lang:
        source = "exact" if not failed else "partial"
        return top_langs(bytes_by_lang), source, fetched, reused
    return top_langs(primary_counts(list(repos))), "primary", fetched, reused


def top_langs(counter) -> list:
    total = sum(counter.values()) or 1
    ranked = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:6]
    return [(k, round(v * 100.0 / total, 1)) for k, v in ranked]


def offline_payload(reason: str) -> dict:
    return {
        "user": {"public_repos": None, "followers": None},
        "repos": [], "stars": None, "shipping": [], "languages": [],
        "languages_source": "none", "offline": True,
        "reason": truncate(reason, 84, 72),
    }


def repo_dict(repo) -> dict:
    return {
        "name": repo.name,
        "language": repo.language,
        "stargazers_count": repo.stargazers_count,
        "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else "",
        "description": repo.description,
        "archived": bool(repo.archived),
        "fork": bool(repo.fork),
        "size": repo.size or 0,
    }


def get_data(token: str | None, fixture: str | None,
             cache: dict | None = None) -> dict:
    if fixture:
        payload = json.loads(Path(fixture).read_text(encoding="utf-8"))
        user, repos = payload["user"], payload["repos"]
        raw = payload.get("languages")
        if raw:
            langs = [(str(k), float(v)) for k, v in raw]
            source = "exact" if payload.get("languages_exact", True) else "partial"
        else:
            langs = top_langs(primary_counts(repos))
            source = "primary"
        return {
            "user": user, "repos": repos,
            "stars": sum(int(r.get("stargazers_count") or 0) for r in repos),
            "shipping": choose_shipping(repos), "languages": langs,
            "languages_source": source, "offline": False, "reason": "fixture",
        }
    cache = cache if cache is not None else {}
    try:
        gh = connect(token)
        profile = gh.get_user(USER)
        repos = [repo_dict(r) for r in profile.get_repos()]
        langs, source, fetched, reused = aggregate_languages(repos, gh, cache)
        return {
            "user": {"login": profile.login,
                     "public_repos": profile.public_repos,
                     "followers": profile.followers},
            "repos": repos,
            "stars": sum(int(r.get("stargazers_count") or 0) for r in repos),
            "shipping": choose_shipping(repos), "languages": langs,
            "languages_source": source, "offline": False,
            "reason": "live" if token else "live (anonymous)",
            "api": {"fetched": fetched, "cached": reused},
        }
    except Exception as exc:
        if os.environ.get("PROFILE_STRICT") == "1":
            raise
        print(f"[warn] GitHub unavailable: {exc}", file=sys.stderr)
        return offline_payload(str(exc))


def css_for(p: dict[str, str]) -> str:
    return (
        ".sans{font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}"
        ".mono{font-family:'JetBrains Mono','Cascadia Code',Consolas,monospace}"
        f".text{{fill:{p['text']}}}.muted{{fill:{p['muted']}}}"
        f".dim{{fill:{p['dim']}}}.accent{{fill:{p['accent']}}}"
        ".rise{opacity:1;animation:rise .72s cubic-bezier(.22,.9,.3,1.05) both}"
        ".fadeup{opacity:1;animation:fadeup .58s cubic-bezier(.22,.9,.3,1.05) both}"
        ".pulse{opacity:1;animation:pulse 2.2s ease-in-out infinite}"
        ".flow{stroke-dasharray:7 9;animation:flow 1.35s linear infinite}"
        ".blink{opacity:1;animation:blink 1s step-end infinite}"
        ".floaty{animation:floaty 4.8s ease-in-out infinite alternate}"
        ".spin{transform-box:fill-box;transform-origin:center;animation:spin 12s linear infinite}"
        ".stageglow{opacity:1;animation:stageglow 2.6s ease-in-out infinite}"
        ".breathe{animation:breathe 3.4s ease-in-out infinite}"
        "@keyframes rise{from{opacity:.01;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}"
        "@keyframes fadeup{from{opacity:.01;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}"
        "@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}"
        "@keyframes flow{to{stroke-dashoffset:-32}}"
        "@keyframes blink{0%,47%{opacity:1}48%,100%{opacity:.08}}"
        "@keyframes floaty{from{transform:translateY(0)}to{transform:translateY(-4px)}}"
        "@keyframes spin{to{transform:rotate(360deg)}}"
        "@keyframes stageglow{0%,100%{opacity:.42}50%{opacity:1}}"
        "@keyframes breathe{0%,100%{opacity:.55}50%{opacity:1}}"
        "@media (prefers-reduced-motion:reduce){"
        ".rise,.fadeup,.pulse,.flow,.blink,.floaty,.spin,.stageglow,.breathe"
        "{animation:none!important}.motion-dot{display:none}}"
    )


def shared_defs(p: dict[str, str], extra: str = "") -> str:
    return f'''<style>{css_for(p)}</style>
<linearGradient id="cardGrad" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{p['card0']}"/><stop offset="1" stop-color="{p['card1']}"/>
</linearGradient>
<linearGradient id="headGrad" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{p['head0']}"/><stop offset="1" stop-color="{p['head1']}"/>
</linearGradient>
<linearGradient id="accentGrad" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{p['accent']}"/><stop offset="1" stop-color="{p['accent2']}"/>
</linearGradient>
<linearGradient id="nameGrad" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{p['text']}"/><stop offset="1" stop-color="{p['accent']}" stop-opacity=".75"/>
</linearGradient>
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
  <path d="M40 0H0V40" fill="none" stroke="{p['grid']}" stroke-opacity=".03"/>
</pattern>
{extra}'''


def outer_clip(height: int) -> str:
    return f'<clipPath id="clip-outer"><rect width="900" height="{height}" rx="24"/></clipPath>'


def card_clip(slug: str, height: int) -> str:
    inner_h = height - 8
    return (f'<clipPath id="clip-{slug}"><rect x="12" y="8" width="876" '
            f'height="{inner_h}" rx="20"/></clipPath>')


def outer_panel(height: int, p: dict[str, str]) -> str:
    return f'''<rect width="900" height="{height}" rx="24" fill="{p['bg']}"/>
<g clip-path="url(#clip-outer)">
<rect width="900" height="{height}" rx="24" fill="url(#grid)"/>
<ellipse cx="128" cy="8" rx="280" ry="112" fill="{p['accent']}" opacity=".09"/>
<ellipse cx="820" cy="{height - 8}" rx="264" ry="120" fill="{p['accent2']}" opacity=".07"/>
</g>
<rect x=".5" y=".5" width="899" height="{height - 1}" rx="24" fill="none" stroke="{p['sheet']}" stroke-opacity=".12"/>'''


def card_group(slug: str, label: str, height: int, body: str,
               p: dict[str, str]) -> str:
    inner_h = height - 8
    return f'''<g class="rise">
  <rect x="12" y="8" width="876" height="{inner_h}" rx="20" fill="url(#cardGrad)" stroke="{p['sheet']}" stroke-opacity=".12"/>
  <path d="M12 28a20 20 0 0 1 20-20h836a20 20 0 0 1 20 20v20H12z" fill="url(#headGrad)"/>
  <circle cx="36" cy="28" r="4" fill="#FF5F56"/>
  <circle cx="52" cy="28" r="4" fill="#FFBD2E"/>
  <circle class="pulse" cx="68" cy="28" r="4" fill="#27C93F"/>
  <text class="mono muted" x="450" y="32" font-size="10" text-anchor="middle"><tspan fill="{p['accent']}">//</tspan> {esc(label)}</text>
  <g clip-path="url(#clip-{slug})">
  {body}
  </g>
</g>'''


def shell(
    height: int, title: str, label: str, body: str,
    p: dict[str, str], extra_defs: str = "", slug: str = "card",
) -> str:
    inner_defs = extra_defs + "\n" + outer_clip(height) + "\n" + card_clip(slug, height)
    return f'''<svg width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
<defs>
{shared_defs(p, inner_defs)}
</defs>
{outer_panel(height, p)}
{card_group(slug, label, height, body, p)}
</svg>'''


def render_bento(sections: list[tuple[str, str, int, str, str]],
                 p: dict[str, str],
                 title: str = "VintlGvard — mission control profile") -> str:
    GAP, PAD = 6, 12
    y = PAD
    groups: list[str] = []
    clips: list[str] = []
    extras: list[str] = []
    for slug, _label, h, bd, extra in sections:
        clips.append(card_clip(slug, h))
        extras.append(extra)
        groups.append(f'<g transform="translate(0 {y})">\n'
                      f'{card_group(slug, _label, h, bd, p)}\n</g>')
        y += h + GAP
    total = y - GAP + PAD
    defs = (shared_defs(p, "\n".join(extras)) + "\n"
            + outer_clip(total) + "\n" + "\n".join(clips))
    return (f'<svg width="{WIDTH}" height="{total}" viewBox="0 0 {WIDTH} {total}" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(title)}">\n'
            f'<title>{esc(title)}</title>\n<defs>\n{defs}\n</defs>\n'
            f'{outer_panel(total, p)}\n' + "\n".join(groups) + '\n</svg>')


def metric(value) -> str:
    return "—" if value is None else str(value)


def hero_parts(data: dict, p: dict[str, str]) -> tuple[str, str, int, str, str]:
    user = data["user"]
    repos = metric(user.get("public_repos"))
    stars = metric(data.get("stars"))
    followers = metric(user.get("followers"))
    pill = "TypeScript + Go"
    typed = "❯ whoami → Vitaliy"

    cursor_x = 48 + len(typed) * 7.22 + 6
    defs = '''
<clipPath id="typeClip"><rect x="48" y="151" width="0" height="24">
<animate attributeName="width" from="0" to="248" dur="1.4s" begin="0.45s" fill="freeze"/>
</rect></clipPath>
<clipPath id="bioClip"><rect x="48" y="126" width="560" height="20"/></clipPath>
'''
    body = f'''
<g class="fadeup" style="animation-delay:.08s">
  <text class="sans" x="48" y="104" font-size="34" font-weight="800" letter-spacing="-.8" fill="url(#nameGrad)">VintlGvard</text>
  <rect x="48" y="116" width="8" height="3" rx="1.5" fill="url(#accentGrad)">
    <animate attributeName="width" from="8" to="232" dur="0.9s" begin="0.18s" fill="freeze"/>
  </rect>
</g>
<g clip-path="url(#bioClip)">
  <text class="sans muted fadeup" x="48" y="142" font-size="12.5" style="animation-delay:.16s">Fullstack product engineer • TypeScript + Go • shipping ideas to production</text>
</g>
<g clip-path="url(#typeClip)">
  <text class="mono text" x="48" y="172" font-size="12">{typed}</text>
</g>
<rect class="blink" x="{cursor_x:.0f}" y="159" width="7" height="15" rx="1" fill="{p['accent']}"/>
<g class="fadeup" style="animation-delay:.28s">
  <rect x="48" y="190" width="408" height="32" rx="16" fill="{p['sheet']}" fill-opacity=".06" stroke="{p['sheet']}" stroke-opacity=".12"/>
  <text class="mono" x="64" y="210" font-size="10" fill="{p['accent']}">{repos} REPOS</text>
  <line x1="136" y1="198" x2="136" y2="214" stroke="{p['sheet']}" stroke-opacity=".14"/>
  <text class="mono text" x="152" y="210" font-size="10">★ {stars}</text>
  <line x1="204" y1="198" x2="204" y2="214" stroke="{p['sheet']}" stroke-opacity=".14"/>
  <text class="mono text" x="220" y="210" font-size="10">{followers} FOLLOWERS</text>
  <line x1="312" y1="198" x2="312" y2="214" stroke="{p['sheet']}" stroke-opacity=".14"/>
  <text class="mono muted" x="328" y="210" font-size="9.5">{pill}</text>
</g>
<g class="fadeup" style="animation-delay:.2s">
  <circle cx="808" cy="110" r="30" fill="{p['card1']}" stroke="{p['sheet']}" stroke-opacity=".1"/>
  <circle class="spin" cx="808" cy="110" r="25" fill="none" stroke="url(#accentGrad)" stroke-width="1.6" stroke-dasharray="11 8" opacity=".78"/>
  <text class="mono" x="808" y="117" font-size="18" font-weight="700" text-anchor="middle" fill="{p['accent']}">❯</text>
  <circle class="pulse" cx="680" cy="110" r="5" fill="{p['green']}"/>
  <text class="mono" x="692" y="114" font-size="9.5" fill="{p['text']}">OPEN TO WORK</text>
  <text class="mono muted" x="680" y="134" font-size="9">reply &lt; 24h</text>
</g>
<g class="floaty fadeup" style="animation-delay:.32s">
  <rect x="680" y="166" width="172" height="40" rx="20" fill="url(#accentGrad)"/>
  <text class="mono" x="766" y="191" font-size="11" font-weight="800" text-anchor="middle" fill="#041916">vintlgvard.com</text>
</g>
'''
    return ("hero", "identity / mission control", 238, body, defs)


ICONS = {

    "plane": '<path d="M11.6 1.2 1.1 5.1c-.8.3-.8.8-.1 1l2.6.8 1 3.1c.1.4.2.5.5.5.2 0 .4-.1.5-.3l1.4-1.3 2.7 2c.5.3.8.1 1-.4l1.6-7.9c.1-.7-.3-1-.8-.9zM4.6 6.9l6-3.8c.3-.2.5-.1.3.1l-5 4.5-.2 2-1.1-2.8z"/>',
    "globe": '<circle cx="6" cy="6" r="5"/>'
             '<path d="M1 6h10M6 1a8 8 0 0 1 0 10A8 8 0 0 1 6 1"/>',
    "git": '<circle cx="4" cy="3.5" r="1.6"/>'
           '<circle cx="4" cy="9.5" r="1.6"/>'
           '<circle cx="9.5" cy="4.6" r="1.6"/>'
           '<path d="M4 5.1v2.8M9.5 6.1c0 2.4-4.2 1.5-5.5 2.9"/>',
    "mail": '<rect x="1" y="2.5" width="10" height="7.5" rx="1.5"/>'
            '<path d="M1.6 3.4 6 6.8 10.4 3.4"/>',
}


def skill_chips(p: dict[str, str], delay_base: float = .10) -> tuple[str, int]:
    x, row_y, parts = 48, 76, []
    for i, name in enumerate(SKILLS):
        core = name in SKILLS_CORE
        w = max(52, int(round(char_units(name) * 7.1 + 28)))
        if x + w > CHIP_LIMIT:
            x, row_y = 48, row_y + 36
        color = p["accent"] if core else p["dim"]
        parts.append(f'''
<g class="fadeup" style="animation-delay:{delay_base + i * .06:.2f}s">
  <rect x="{x}" y="{row_y}" width="{w}" height="28" rx="14" fill="{color}" fill-opacity="{'0.12' if core else '0.08'}" stroke="{color}" stroke-opacity=".45"/>
  <text class="sans" x="{x + 13}" y="{row_y + 19}" font-size="11" fill="{color}">{esc(name)}</text>
</g>''')
        x += w + 8
    return "".join(parts), row_y


def contact_parts(data: dict, p: dict[str, str]) -> tuple[str, str, int, str, str]:
    chips_svg, chips_last_y = skill_chips(p)
    rows: list[str] = []
    y = 76
    for i, (icon, value, label) in enumerate(CONTACTS):
        path = ICONS.get(icon, ICONS["globe"])
        rows.append(f'''
<g class="fadeup" style="animation-delay:{.14 + i * .09:.2f}s">
  <circle class="pulse" style="animation-delay:{.5 + i * .25:.2f}s" cx="{DIVIDER_X + 34}" cy="{y}" r="12" fill="{p['sheet']}" fill-opacity=".05"/>
  <g transform="translate({DIVIDER_X + 28} {y - 6})" fill="none" stroke="{p['accent']}"
     stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" opacity=".9">{path}</g>
  <text class="sans text" x="{DIVIDER_X + 58}" y="{y + 4}" font-size="11.5">{esc(value)}</text>
  <text class="mono muted" x="852" y="{y + 4}" font-size="9" text-anchor="end">{esc(label)}</text>
</g>''')
        y += 34
    rows.append(f'''
<g class="fadeup" style="animation-delay:{.14 + len(CONTACTS) * .09:.2f}s">
  <circle class="pulse" cx="{DIVIDER_X + 34}" cy="{y + 2}" r="4" fill="{p['green']}"/>
  <circle cx="{DIVIDER_X + 34}" cy="{y + 2}" r="4" fill="none" stroke="{p['green']}" stroke-width="1">
    <animate attributeName="r" values="4;9" dur="1.8s" repeatCount="indefinite"/>
    <animate attributeName="opacity" values=".6;0" dur="1.8s" repeatCount="indefinite"/>
  </circle>
  <text class="sans muted" x="{DIVIDER_X + 58}" y="{y + 6}" font-size="11">{esc(REPLY_NOTE)}</text>
</g>''')
    body = f'''<line x1="{DIVIDER_X}" y1="60" x2="{DIVIDER_X}" y2="{max(y + 22, chips_last_y + 46)}" stroke="{p['sheet']}" stroke-opacity=".1"/>
{chips_svg}
{"".join(rows)}'''
    height = max(y + 34, chips_last_y + 58)
    return ("contact", "skills / contact", height, body, "")


def _progress(data: dict) -> int:
    newest = ""
    for repo in data.get("shipping") or []:
        pushed = str(repo.get("pushed_at") or "")
        if pushed > newest:
            newest = pushed
    try:
        age = (date.today()
               - date.fromisoformat(newest[:10])).days
    except ValueError:
        return 2
    return 4 if age <= 14 else (3 if age <= FRESH_WINDOW_DAYS else 2)


def stage(x: int, label: str, index: int, lit: bool, p: dict[str, str]) -> str:
    color = p["accent"] if lit else p["dim"]
    opacity = ".16" if lit else ".08"
    return f'''
<g class="fadeup" style="animation-delay:{.08 + index * .08:.2f}s">
  <circle class="stageglow" style="animation-delay:{index * .45:.2f}s" cx="{x}" cy="96" r="18" fill="{color}" opacity="{opacity}"/>
  <circle cx="{x}" cy="96" r="7" fill="{p['bg']}" stroke="{color}" stroke-width="2"/>
  <circle cx="{x}" cy="96" r="2.5" fill="{color}"/>
  <text class="mono" x="{x}" y="130" font-size="10" text-anchor="middle" fill="{p['text']}">{label}</text>
  <text class="mono muted" x="{x}" y="144" font-size="9.5" text-anchor="middle">0{index + 1}</text>
</g>'''


def shipping_parts(data: dict, p: dict[str, str]) -> tuple[str, str, int, str, str]:
    progress = _progress(data)
    stage_x = (150, 350, 550, 750)
    stages = "".join(
        stage(x, label, i, lit=(i < progress), p=p)
        for i, (x, label) in enumerate(zip(stage_x, ("IDEA", "BUILD", "SHIP", "RUN")))
    )
    line = f'''
<path d="M150 96H750" fill="none" stroke="{p['sheet']}" stroke-opacity=".1" stroke-width="8" stroke-linecap="round"/>
<path d="M150 96H750" fill="none" stroke="url(#accentGrad)" stroke-opacity=".58" stroke-width="2" stroke-linecap="round"/>
<path class="flow" d="M150 96H750" fill="none" stroke="{p['text']}" stroke-opacity=".22" stroke-width="1"/>
<circle class="motion-dot" r="4" fill="{p['accent']}"><animateMotion dur="9s" repeatCount="indefinite" path="M150 96H750"/></circle>
{stages}
'''
    defs: list[str] = []
    cards: list[str] = []
    if data.get("shipping"):
        for i, repo in enumerate(data["shipping"]):
            y = 160 + i * 72
            name = truncate(repo.get("name") or "untitled", 34, 29)
            desc = truncate(repo.get("description") or "No description in GitHub API", 54, 51)
            lang = truncate(repo.get("language") or "—", 18, 16)
            stars = int(repo.get("stargazers_count") or 0)
            pushed = fmt_date(repo.get("pushed_at"))
            clip_id = f"shipCard{i}"
            defs.append(
                f'<clipPath id="{clip_id}"><rect x="48" y="{y}" width="804" height="56" rx="14"/></clipPath>'
            )
            cards.append(f'''
<g class="fadeup" style="animation-delay:{.36 + i * .10:.2f}s">
  <rect x="48" y="{y}" width="804" height="56" rx="14" fill="{p['sheet']}" fill-opacity=".05" stroke="{p['sheet']}" stroke-opacity=".12"/>
  <g clip-path="url(#{clip_id})">
  <rect class="breathe" style="animation-delay:{i * .35:.2f}s" x="48" y="{y}" width="3" height="56" fill="url(#accentGrad)"/>
  <circle class="pulse" style="animation-delay:{.6 + i * .3:.2f}s" cx="72" cy="{y + 28}" r="5" fill="{p['accent']}" opacity=".9"/>
  <text class="sans text" x="88" y="{y + 23}" font-size="12.5" font-weight="700">{esc(name)}</text>
  <text class="sans muted" x="88" y="{y + 41}" font-size="10.5">{esc(desc)}</text>
  <text class="mono text" x="828" y="{y + 22}" font-size="10" text-anchor="end">★ {stars}</text>
  <text class="mono muted" x="828" y="{y + 41}" font-size="9.5" text-anchor="end">{esc(lang)} · {esc(pushed)}</text>
  </g>
</g>''')
    else:
        reason = truncate(data.get("reason") or "GitHub API unavailable", 68, 62)
        cards.append(f'''
<g class="fadeup" style="animation-delay:.32s">
  <rect x="48" y="168" width="804" height="128" rx="16" fill="{p['sheet']}" fill-opacity=".04" stroke="{p['sheet']}" stroke-opacity=".12"/>
  <text class="mono" x="72" y="208" font-size="11" fill="{p['muted']}">LIVE DATA UNAVAILABLE</text>
  <text class="sans text" x="72" y="236" font-size="14" font-weight="700">No project metadata was fabricated.</text>
  <text class="mono muted" x="72" y="264" font-size="9.5">{esc(reason)}</text>
</g>''')
    return ("shipping", "now shipping / live from GitHub API", 384,
            line + "".join(cards), "\n".join(defs))


def stack_parts(data: dict, p: dict[str, str]) -> tuple[str, str, int, str, str]:
    langs = data.get("languages") or []
    top = langs[:5]
    bars_y = 76
    bar_parts: list[str] = []
    if top:
        for i, (name, pct) in enumerate(top):
            y = bars_y + i * 30
            pct = max(0.0, min(float(pct), 100.0))
            width = max(5, round(512 * pct / 100.0))
            primary = name in {"TypeScript", "Go"}
            fill = "url(#accentGrad)" if primary else p["dim"]
            label_fill = p["text"] if primary else p["muted"]
            bar_parts.append(f'''
<g class="fadeup" style="animation-delay:{.20 + i * .07:.2f}s">
  <text class="sans" x="48" y="{y + 11}" font-size="11" fill="{label_fill}">{esc(truncate(name, 22, 18))}</text>
  <rect class="breathe" style="animation-delay:{i * .3:.2f}s" x="200" y="{y + 2}" width="512" height="10" rx="5" fill="{p['track']}" fill-opacity=".1"/>
  <rect x="5" y="{y + 2}" width="5" height="10" rx="5" fill="{fill}" transform="translate(195 0)">
    <animate attributeName="width" from="5" to="{width}" dur="0.8s" begin="{.3 + i * .07:.2f}s" fill="freeze"/>
  </rect>
  <text class="mono muted" x="852" y="{y + 11}" font-size="9.5" text-anchor="end">{pct:.1f}%</text>
</g>''')
        last_bottom = bars_y + (len(top) - 1) * 30 + 12
    else:
        bar_parts.append(f'''
<rect x="48" y="{bars_y}" width="804" height="56" rx="14" fill="{p['sheet']}" fill-opacity=".04" stroke="{p['sheet']}" stroke-opacity=".12"/>
<text class="mono muted" x="72" y="{bars_y + 34}" font-size="10">Language bars appear when GitHub API is reachable.</text>''')
        last_bottom = bars_y + 56
    height = last_bottom + 24
    return ("stack", "languages / most used", height, "".join(bar_parts), "")


def stats_parts(data: dict, p: dict[str, str]) -> tuple[str, str, int, str, str]:
    user = data["user"]
    repos = data.get("repos") or []
    live_count = (len([r for r in repos if not r.get("archived")
                       and not r.get("fork") and r.get("name") != USER])
                  if repos else None)
    values = (
        ("REPOS", metric(user.get("public_repos")), "public"),
        ("STARS", metric(data.get("stars")), "total"),
        ("FOLLOWERS", metric(user.get("followers")), "github"),
        ("LIVE", metric(live_count), "non-archived"),
        ("REPLY", "<24h", "open to work"),
    )
    parts: list[str] = []
    tile_w, gap, x0 = 148, 12, 48
    for i, (label, value, sub) in enumerate(values):
        x = x0 + i * (tile_w + gap)
        bar = "url(#accentGrad)" if i < 4 else p["green"]
        parts.append(f'''
<g class="floaty fadeup" style="animation-delay:{.08 + i * .09:.2f}s">
  <rect x="{x}" y="76" width="{tile_w}" height="80" rx="16" fill="{p['sheet']}" fill-opacity=".05" stroke="{p['sheet']}" stroke-opacity=".12"/>
  <text class="sans text" x="{x + 16}" y="106" font-size="23" font-weight="800">{esc(value)}</text>
  <rect class="breathe" style="animation-delay:{.5 + i * .2:.2f}s" x="{x + 16}" y="114" width="5" height="2" rx="1" fill="{bar}">
    <animate attributeName="width" from="5" to="52" dur=".7s" begin="{.18 + i * .09:.2f}s" fill="freeze"/>
  </rect>
  <text class="mono" x="{x + 16}" y="134" font-size="9" fill="{p['accent']}">{label}</text>
  <text class="mono muted" x="{x + 16}" y="147" font-size="9">{esc(sub)}</text>
</g>''')
    body = "".join(parts)
    return ("stats", "telemetry / five signals", 176, body, "")


def validate_svg(name: str, svg: str) -> None:
    if not svg.lstrip().startswith("<svg"):
        raise ValueError(f"{name}: root is not <svg>")
    if re.search(r"<image[\s>/]", svg):
        raise ValueError(f"{name}: external <image> element is forbidden")
    if len(re.findall(r"<filter[\s>]", svg)) > 2:
        raise ValueError(f"{name}: too many filters (perf budget)")
    if "feturbulence" in svg.lower():
        raise ValueError(f"{name}: heavy noise filter detected")
    if "@media (prefers-reduced-motion:reduce)" not in svg:
        raise ValueError(f"{name}: missing reduced-motion fallback")
    if "animation:none!important" not in svg:
        raise ValueError(f"{name}: reduced-motion does not disable CSS animations")
    body = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")


    if re.search(r'''(?:href|xlink:href|src)\s*=\s*["']https?://''', body):
        raise ValueError(f"{name}: external URL attribute inside SVG")
    if 'viewBox="0 0 900 ' not in svg:
        raise ValueError(f"{name}: missing scalable viewBox")


def validate_text_constraints(data: dict) -> None:
    bio = "Fullstack product engineer • TypeScript + Go • shipping ideas to production"
    if char_units(bio) > 92:
        raise ValueError("hero bio exceeds clipped width")
    for repo in data.get("shipping") or []:
        name = truncate(repo.get("name") or "untitled", 34, 29)
        desc = truncate(repo.get("description") or "No description", 54, 51)
        if len(desc) > 54 or char_units(name) > 29.1 or char_units(desc) > 51.1:
            raise ValueError(f"shipping card overflow: {name}")
    for value in (metric(data.get("stars")),
                  metric(data["user"].get("public_repos")),
                  metric(data["user"].get("followers"))):
        if len(value) > 10:
            raise ValueError(f"stat tile overflow: {value}")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")



def connect(token):
    auth = Auth.Token(token) if token else None
    try:
        return Github(auth=auth, retry=GithubRetry(max_rate_limit_wait=0))
    except TypeError:
        return Github(auth=auth) if token else Github()


def fetch_identity(token):
    gh = connect(token)
    profile = gh.get_user(USER)
    user = {"login": profile.login, "public_repos": profile.public_repos,
            "followers": profile.followers}
    return user, [repo_dict(r) for r in profile.get_repos()]


def main() -> None:
    root = resolve_root(None)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    try:
        user, repos = fetch_identity(token)
    except Exception as exc:
        raise SystemExit(f"generate: GitHub unavailable: {exc}")
    stars = sum(int(r.get("stargazers_count") or 0) for r in repos)
    data = {"user": user, "repos": repos, "stars": stars, "shipping": [],
            "languages": [], "languages_source": "none", "offline": False,
            "reason": "static"}
    p = THEMES["dark"]
    svgs = {}
    for fn in (hero_parts, contact_parts):
        slug, label, h, body, defs = fn(data, p)
        svgs[f"{slug}.svg"] = shell(h, TITLES[slug], label, body, p, defs, slug)
    validate_text_constraints(data)
    for name, svg in svgs.items():
        validate_svg(name, svg)
    out = root / "assets"
    out.mkdir(parents=True, exist_ok=True)
    for name, svg in svgs.items():
        write_text(out / name, svg)
    total_kib = sum(len(s.encode()) for s in svgs.values()) / 1024
    print(f"[ok] static hero.svg + contact.svg ({total_kib:.1f} KiB) "
          f"stars={stars}")


if __name__ == "__main__":
    main()
