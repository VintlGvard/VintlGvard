#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate as gen


def main() -> None:
    root = gen.resolve_root(os.environ.get("PROFILE_ROOT"))
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    cache_path = root / ".lang-cache.json"
    try:
        cache = gen.load_cache(cache_path)
        data = gen.get_data(token, None, cache)
        if data.get("offline"):
            raise RuntimeError(data.get("reason") or "offline")
        if data.get("languages_source") != "exact":
            raise RuntimeError(f"languages {data.get('languages_source')}, need exact")
        p = gen.THEMES["dark"]
        all_parts = [gen.hero_parts(data, p), gen.contact_parts(data, p),
                     gen.shipping_parts(data, p), gen.stack_parts(data, p),
                     gen.stats_parts(data, p)]
        by_slug = {s[0]: s for s in all_parts}
        svgs = {}
        for slug in ("shipping", "stack", "stats"):
            _, label, h, body, defs = by_slug[slug]
            svgs[f"{slug}.svg"] = gen.shell(
                h, gen.TITLES[slug], label, body, p, defs, slug)
        svgs["profile.svg"] = gen.render_bento(all_parts, p, gen.BENTO_TITLE)
        for name, svg in svgs.items():
            gen.validate_svg(name, svg)
        out = root / "assets"
        out.mkdir(parents=True, exist_ok=True)
        for name, svg in svgs.items():
            gen.write_text(out / name, svg)
        gen.save_cache(cache_path, cache)
        api = data.get("api") or {}
        print(f"[ok] update: shipping + stack + stats + bento "
              f"({sum(len(s.encode()) for s in svgs.values()) / 1024:.1f} KiB) "
              f"api: {api.get('fetched', 0)} fetched / "
              f"{api.get('cached', 0)} cached")
    except Exception as exc:
        print(f"[skip] profile update skipped: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
