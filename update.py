#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import sys

import requests
from github import GithubException

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate as gen

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
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
        gen.validate_text_constraints(data)
        p = gen.THEMES["dark"]
        all_parts = [
            gen.hero_parts(data, p),
            gen.contact_parts(data, p),
            gen.shipping_parts(data, p),
            gen.stack_parts(data, p),
            gen.stats_parts(data, p),
        ]
        svgs = gen.build_card_svgs(all_parts, p)
        svgs["profile.svg"] = gen.render_bento(all_parts, p, gen.BENTO_TITLE)
        for name, svg in svgs.items():
            gen.validate_svg(name, svg)
        out = root / "assets"
        for name, svg in svgs.items():
            gen.write_text(out / name, svg)
        gen.update_readme(root / "README.md", gen.render_readme(data))
        gen.save_cache(cache_path, cache)
        api = data.get("api") or {}
        logger.info(
            "[ok] update: hero + contact + shipping + stack + stats + bento "
            "(%.1f KiB) api: %d fetched / %d cached",
            sum(len(s.encode()) for s in svgs.values()) / 1024,
            api.get("fetched", 0),
            api.get("cached", 0),
        )
        return 0
    except ValueError as exc:
        logger.error("[error] profile validation failed: %s", exc)
        return 1
    except (RuntimeError, GithubException, requests.RequestException, OSError) as exc:
        if os.environ.get("PROFILE_STRICT") == "1":
            logger.error("[error] profile update failed: %s", exc)
            return 1
        logger.warning("[skip] profile update skipped: %s", exc)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
