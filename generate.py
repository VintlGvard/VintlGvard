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
          "MySQL", "SQLite", "Nginx", "Electron", "Lua")
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
    units = 0.0
    for ch in text:
        u = char_units(ch)
        if len(out) + 1 > max_chars - 1 or units + u > max_units - 1.0:
            break
        out.append(ch)
        units += u
    return "".join(out).rstrip() + "…"


def format_num(val) -> str:
    try:
        val = int(val)
    except (TypeError, ValueError):
        return "0"
    return f"{val:,}".replace(",", " ")


def metric(val) -> str:
    if val is None:
        return "--"
    try:
        n = int(val)
    except (TypeError, ValueError):
        return str(val)
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def relative_age(iso_date: str) -> str:
    if not iso_date:
        return "dormant"
    clean = re.sub(r"[+-]\d{2}:\d{2}$|Z$", "", iso_date)
    try:
        pushed = date.fromisoformat(clean.split("T")[0])
    except ValueError:
        return "dormant"
    days = (date.today() - pushed).days
    if days < 0:
        days = 0
    if days == 0:
        return "active today"
    if days == 1:
        return "active yesterday"
    if days < 30:
        return f"active {days}d ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    years = days // 365
    return f"{years}y ago"


def load_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_cache(path: Path, cache: dict) -> None:
    try:
        path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    except OSError as exc:
        print(f"[warn] cache write failed: {exc}", file=sys.stderr)


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
        "user": {"login": USER, "public_repos": None, "followers": None},
        "repos": [], "stars": None, "shipping": [], "languages": [],
        "languages_source": "offline", "offline": True, "reason": reason,
    }


def primary_counts(repos: list) -> dict:
    tally = defaultdict(int)
    for r in repos:
        if r.get("fork") or r.get("archived") or r.get("name") == USER:
            continue
        lang = r.get("language")
        if lang:
            tally[str(lang)] += 1
    return tally


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


def choose_shipping(repos: list) -> list:
    active = [r for r in repos if not r.get("fork") and not r.get("archived")
              and r.get("name") != USER]

    def score(r):
        s = 0
        if r.get("name") in SHOWCASE:
            s += SHOWCASE_BOOST
        s += int(r.get("stargazers_count") or 0) * STAR_WEIGHT
        age = relative_age(str(r.get("pushed_at") or ""))
        if "today" in age or "yesterday" in age or (
            "d ago" in age and int(re.findall(r"\d+", age)[0]) <= FRESH_WINDOW_DAYS
        ):
            s += 10
        return s

    active.sort(key=score, reverse=True)
    return active[:3]


COMMON_STYLES = (
    ".sans{font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}"
    ".mono{font-family:'JetBrains Mono','Cascadia Code',Consolas,monospace}"
    ".text{fill:#E8EEF4}.muted{fill:#8B95A5}.dim{fill:#5B6472}.accent{fill:#00E5CC}"
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
    ".rise,.fadeup,.pulse,.flow,.blink,.floaty,.spin,.stageglow,.breathe{animation:none!important}"
    ".motion-dot{display:none}}"
)


def common_defs(p: dict[str, str], extra: str = "",
                extra_styles: str = "") -> str:
    return f'''<defs>
<style>{COMMON_STYLES}{extra_styles}</style>
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
{extra}
</defs>'''


def shell(height: int, title: str, label: str, body: str,
          p: dict[str, str], extra_defs: str = "",
          clip_id: str = "card-inner", extra_styles: str = "") -> str:
    defs = common_defs(
        p,
        f'''
<clipPath id="clip-outer"><rect width="900" height="{height}" rx="24"/></clipPath>
<clipPath id="clip-{clip_id}"><rect x="12" y="8" width="876" height="{height - 8}" rx="20"/></clipPath>{extra_defs}''',
        extra_styles=extra_styles,
    )
    return f'''<svg width="900" height="{height}" viewBox="0 0 900 {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
{defs}
<rect width="900" height="{height}" rx="24" fill="{p['bg']}"/>
<g clip-path="url(#clip-outer)">
<rect width="900" height="{height}" rx="24" fill="url(#grid)"/>
<ellipse cx="128" cy="8" rx="280" ry="112" fill="{p['accent']}" opacity=".09"/>
<ellipse cx="820" cy="{height - 8}" rx="264" ry="120" fill="{p['accent2']}" opacity=".07"/>
</g>
<rect x=".5" y=".5" width="899" height="{height - 1}" rx="24" fill="none" stroke="{p['sheet']}" stroke-opacity=".12"/>
<g class="rise">
  <rect x="12" y="8" width="876" height="{height - 8}" rx="20" fill="url(#cardGrad)" stroke="{p['sheet']}" stroke-opacity=".12"/>
  <path d="M12 28a20 20 0 0 1 20-20h836a20 20 0 0 1 20 20v20H12z" fill="url(#headGrad)"/>
  <circle cx="36" cy="28" r="4" fill="#FF5F56"/>
  <circle cx="52" cy="28" r="4" fill="#FFBD2E"/>
  <circle class="pulse" cx="68" cy="28" r="4" fill="#27C93F"/>
  <text class="mono muted" x="450" y="32" font-size="10" text-anchor="middle"><tspan fill="{p['accent']}">//</tspan> {esc(label)}</text>
  <g clip-path="url(#clip-{clip_id})">
  {body}
  </g>
</g>
</svg>'''


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def validate_svg(name: str, svg: str) -> None:
    if not svg.startswith("<svg") or not svg.endswith("</svg>"):
        raise ValueError(f"{name}: invalid SVG root")
    for tag in ("text", "rect", "circle", "g", "defs", "style", "path", "mask",
                "clipPath", "linearGradient", "pattern"):
        opens = len(re.findall(rf"<{tag}(?:\s|>)", svg))
        closes = len(re.findall(rf"</{tag}>", svg))
        self_closing = len(re.findall(rf"<{tag}[^>]*?/>", svg))
        if opens != closes + self_closing:
            raise ValueError(
                f"{name}: unbalanced <{tag}> "
                f"({opens} open, {closes} close, {self_closing} self-closing)"
            )


def hero_parts(data: dict, p: dict[str, str]) -> tuple[str, str, int, str, str]:
    user = data["user"]
    repos = data.get("repos") or []
    stars = data.get("stars")
    live_count = len([r for r in repos if not r.get("archived") and not r.get("fork")
                      and r.get("name") != USER]) if repos else None
    role_chips = [
        ("Fullstack product engineer", True),
        ("Go · TypeScript · Python", False),
    ]
    parts: list[str] = [
        f'<text class="fadeup sans text" style="animation-delay:.08s" x="48" y="98" font-size="28" font-weight="800" fill="url(#nameGrad)">{esc(USER)}</text>',
        f'<text class="fadeup mono" style="animation-delay:.16s" x="48" y="124" font-size="10.5" fill="{p["accent"]}"><tspan fill="{p["muted"]}">const</tspan> focus <tspan fill="{p["muted"]}">=</tspan> <tspan fill="{p["text"]}">["compilers/tui", "web-systems", "tools"]</tspan></text>',
        f'<text class="fadeup sans muted" style="animation-delay:.22s" x="48" y="148" font-size="11.5">Building solid product foundations · terminal tools · clean architectures</text>',
        f'<line class="fadeup" style="animation-delay:.26s" x1="48" y1="168" x2="180" y2="168" stroke="{p["accent"]}" stroke-width="1.2" stroke-opacity=".6"/>',
        f'<rect class="blink" x="184" y="159" width="7" height="15" rx="1" fill="{p["accent"]}"/>',
    ]
    chip_x = 48
    pill_parts: list[str] = []
    for label, is_primary in role_chips:
        w = max(52, int(round(char_units(label) * 6.5 + 24)))
        fill = p["accent"] if is_primary else p["sheet"]
        stroke = p["accent"] if is_primary else p["sheet"]
        text_fill = p["accent"] if is_primary else p["text"]
        pill_parts.append(
            f'<rect x="{chip_x}" y="190" width="{w}" height="24" rx="12" '
            f'fill="{fill}" fill-opacity="{"0.14" if is_primary else "0.05"}" '
            f'stroke="{stroke}" stroke-opacity="{"0.55" if is_primary else "0.15"}"/>'
            f'<text class="sans" x="{chip_x + 12}" y="206" font-size="10" '
            f'font-weight="{"600" if is_primary else "400"}" fill="{text_fill}">{esc(label)}</text>'
        )
        chip_x += w + 8

    stat_tokens = [
        (f"{live_count} REPOS" if live_count is not None else "-- REPOS", p["accent"]),
        (f"★ {stars}" if stars is not None else "★ --", p["text"]),
        (f"{metric(user.get('followers'))} FOLLOWERS", p["muted"]),
    ]
    right_pill_w = 408
    right_pill_x = 48
    parts.append(f'''
<g class="fadeup" style="animation-delay:.28s">
  <rect x="{right_pill_x}" y="190" width="{right_pill_w}" height="32" rx="16" fill="{p['sheet']}" fill-opacity=".06" stroke="{p['sheet']}" stroke-opacity=".12"/>
  <text class="mono" x="{right_pill_x + 16}" y="210" font-size="10" fill="{stat_tokens[0][1]}">{esc(stat_tokens[0][0])}</text>
  <line x1="{right_pill_x + 88}" y1="198" x2="{right_pill_x + 88}" y2="214" stroke="{p['sheet']}" stroke-opacity=".14"/>
  <text class="mono text" x="{right_pill_x + 104}" y="210" font-size="10">{esc(stat_tokens[1][0])}</text>
  <line x1="{right_pill_x + 156}" y1="198" x2="{right_pill_x + 156}" y2="214" stroke="{p['sheet']}" stroke-opacity=".14"/>
  <text class="mono muted" x="{right_pill_x + 172}" y="210" font-size="10">{esc(stat_tokens[2][0])}</text>
  <circle class="pulse" cx="{right_pill_x + right_pill_w - 20}" cy="206" r="3.5" fill="{p['green']}"/>
</g>''')
    body = "".join(parts)
    return ("hero", "mission control / identity", 244, body, "")


ICONS = {
    "plane": '<path d="m1.5 6 9.5-4.5-4 9.5-1.8-3.6zM5.2 7.4l4-4"/>',
    "globe": '<circle cx="6" cy="6" r="4.8"/>'
             '<path d="M1.2 6h9.6M6 1.2a7.5 7.5 0 0 0 0 9.6M6 1.2a7.5 7.5 0 0 1 0 9.6"/>',
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
    age = relative_age(newest)
    if "today" in age or "yesterday" in age:
        return 92
    if "d ago" in age:
        try:
            d = int(re.findall(r"\d+", age)[0])
            return max(35, 90 - d * 2)
        except (IndexError, ValueError):
            return 60
    return 35


def shipping_parts(data: dict, p: dict[str, str]) -> tuple[str, str, int, str, str]:
    shipping = data.get("shipping") or []
    stages = [
        ("IDEA", "01", "research &amp; spec", .10),
        ("ARCH", "02", "system design", .18),
        ("BUILD", "03", "implementation", .26),
        ("PROVE", "04", "tests &amp; metrics", .34),
        ("RUN", "05", "prod &amp; telemetry", .42),
    ]
    parts: list[str] = []
    tile_w, tile_h, gap, x0 = 160, 68, 16, 48
    bar_w = 4 * (tile_w + gap)
    progress_pct = _progress(data)
    parts.append(f'''
<g class="fadeup" style="animation-delay:.08s">
  <line x1="{x0 + 40}" y1="84" x2="{x0 + bar_w}" y2="84" stroke="{p['sheet']}" stroke-opacity=".12" stroke-width="2"/>
  <line class="flow" x1="{x0 + 40}" y1="84" x2="{x0 + bar_w}" y2="84" stroke="{p['accent']}" stroke-width="2" stroke-opacity=".7"/>
  <circle class="stageglow" cx="{x0 + 40 + int((bar_w - 40) * progress_pct / 100)}" cy="84" r="5" fill="{p['accent']}"/>
</g>''')
    for i, (name, num, desc, delay) in enumerate(stages):
        x = x0 + i * (tile_w + gap)
        active = i <= 2
        bg = p["card1"] if active else p["bg"]
        accent = p["accent"] if active else p["dim"]
        parts.append(f'''
<g class="fadeup" style="animation-delay:{delay:.2f}s">
  <rect x="{x}" y="100" width="{tile_w}" height="{tile_h}" rx="14" fill="{bg}" stroke="{p['sheet']}" stroke-opacity="{'0.14' if active else '0.06'}"/>
  <text class="mono" x="{x + 14}" y="122" font-size="9" fill="{accent}">{num}</text>
  <text class="mono text" x="{x + 36}" y="122" font-size="11" font-weight="700">{name}</text>
  <text class="sans muted" x="{x + 14}" y="148" font-size="10">{desc}</text>
</g>''')
    y_feed = 186
    parts.append(
        f'<text class="fadeup mono muted" style="animation-delay:.48s" '
        f'x="48" y="{y_feed}" font-size="9.5"><tspan fill="{p["accent"]}">'
        f'RECENT DEPLOYS</tspan> // tracked via git activity</text>'
    )
    for i, repo in enumerate(shipping[:3]):
        y = y_feed + 12 + i * 44
        name = repo.get("name", "repo")
        lang = repo.get("language") or "code"
        stars = repo.get("stargazers_count") or 0
        desc = truncate(repo.get("description") or "No description", 58, 52)
        age = relative_age(str(repo.get("pushed_at") or ""))
        parts.append(f'''
<g class="fadeup" style="animation-delay:{.52 + i * .08:.2f}s">
  <rect x="48" y="{y}" width="804" height="36" rx="10" fill="{p['sheet']}" fill-opacity=".04" stroke="{p['sheet']}" stroke-opacity=".08"/>
  <circle cx="64" cy="{y + 18}" r="3" fill="{p['accent']}"/>
  <text class="mono text" x="78" y="{y + 22}" font-size="11" font-weight="700">{esc(name)}</text>
  <text class="sans muted" x="240" y="{y + 22}" font-size="10.5">{esc(desc)}</text>
  <text class="mono" x="690" y="{y + 22}" font-size="9.5" fill="{p['accent']}">{esc(lang)}</text>
  <text class="mono text" x="760" y="{y + 22}" font-size="9.5">★ {stars}</text>
  <text class="mono muted" x="840" y="{y + 22}" font-size="9" text-anchor="end">{esc(age)}</text>
</g>''')
    last_y = y_feed + 12 + max(len(shipping[:3]), 1) * 44
    return ("shipping", "pipeline / idea to run", last_y + 14, "".join(parts), "")


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


def render_bento(cards: list[tuple[str, str, int, str, str]],
                 p: dict[str, str], title: str) -> str:
    y_cursor = 8
    g_elements: list[str] = []
    card_clips: list[str] = []
    for slug, label, h, body, defs in cards:
        card_y = y_cursor
        clip_id = f"bento-{slug}"
        card_clips.append(
            f'<clipPath id="clip-{clip_id}"><rect x="12" y="{card_y}" width="876" height="{h}" rx="20"/></clipPath>'
        )
        if defs:
            card_clips.append(defs)
        header = f'''
  <path d="M12 {card_y + 20}a20 20 0 0 1 20-20h836a20 20 0 0 1 20 20v20H12z" fill="url(#headGrad)"/>
  <circle cx="36" cy="{card_y + 20}" r="4" fill="#FF5F56"/>
  <circle cx="52" cy="{card_y + 20}" r="4" fill="#FFBD2E"/>
  <circle class="pulse" cx="68" cy="{card_y + 20}" r="4" fill="#27C93F"/>
  <text class="mono muted" x="450" y="{card_y + 24}" font-size="10" text-anchor="middle"><tspan fill="{p['accent']}">//</tspan> {esc(label)}</text>'''
        g_elements.append(f'''
<g class="rise">
  <rect x="12" y="{card_y}" width="876" height="{h}" rx="20" fill="url(#cardGrad)" stroke="{p['sheet']}" stroke-opacity=".12"/>
  {header}
  <g clip-path="url(#clip-{clip_id})" transform="translate(0 {card_y - 8})">
  {body}
  </g>
</g>''')
        y_cursor += h + 16
    total_height = y_cursor - 16 + 8
    defs = common_defs(
        p,
        f'''
<clipPath id="clip-outer"><rect width="900" height="{total_height}" rx="24"/></clipPath>
{''.join(card_clips)}''',
    )
    return f'''<svg width="900" height="{total_height}" viewBox="0 0 900 {total_height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
{defs}
<rect width="900" height="{total_height}" rx="24" fill="{p['bg']}"/>
<g clip-path="url(#clip-outer)">
<rect width="900" height="{total_height}" rx="24" fill="url(#grid)"/>
<ellipse cx="128" cy="8" rx="280" ry="112" fill="{p['accent']}" opacity=".09"/>
<ellipse cx="820" cy="{total_height - 8}" rx="264" ry="120" fill="{p['accent2']}" opacity=".07"/>
</g>
<rect x=".5" y=".5" width="899" height="{total_height - 1}" rx="24" fill="none" stroke="{p['sheet']}" stroke-opacity=".12"/>
{''.join(g_elements)}
</svg>'''


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
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture")
    parser.add_argument("--preview")
    parser.add_argument("--root")
    args = parser.parse_args()

    root = resolve_root(args.root)
    cache_path = root / ".lang-cache.json"
    cache = load_cache(cache_path)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    data = get_data(token, args.fixture, cache)
    p = THEMES["dark"]
    all_parts = [hero_parts(data, p), contact_parts(data, p),
                 shipping_parts(data, p), stack_parts(data, p),
                 stats_parts(data, p)]
    by_slug = {s[0]: s for s in all_parts}

    svgs = {}
    for slug in ("hero", "contact", "shipping", "stack", "stats"):
        _, label, h, body, defs = by_slug[slug]
        svgs[f"{slug}.svg"] = shell(h, TITLES[slug], label, body, p, defs, slug)
    svgs["profile.svg"] = render_bento(all_parts, p, BENTO_TITLE)

    for name, svg in svgs.items():
        validate_svg(name, svg)

    out = root / "assets"
    out.mkdir(parents=True, exist_ok=True)
    for name, svg in svgs.items():
        write_text(out / name, svg)
    save_cache(cache_path, cache)

    api = data.get("api") or {}
    print(f"[ok] generated: {', '.join(svgs.keys())} "
          f"({sum(len(s.encode()) for s in svgs.values()) / 1024:.1f} KiB) "
          f"api: {api.get('fetched', 0)} fetched / {api.get('cached', 0)} cached")


if __name__ == "__main__":
    main()
