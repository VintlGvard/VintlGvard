from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate as gen
import update


def make_repo(
    name: str,
    *,
    language: str = "TypeScript",
    stars: int = 0,
    pushed_at: str = "2026-11-10",
    description: str = "Sample project description",
    archived: bool = False,
    fork: bool = False,
    size: int = 120,
    languages: dict[str, int] | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.name = name
    repo.language = language
    repo.stargazers_count = stars
    repo.pushed_at = datetime.fromisoformat(f"{pushed_at}T12:00:00+00:00")
    repo.description = description
    repo.archived = archived
    repo.fork = fork
    repo.size = size
    repo.get_languages.return_value = languages or {language: 1000}
    return repo


class ProfileGeneratorTests(unittest.TestCase):
    def test_update_regenerates_all_six_svgs_including_hero_and_contact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_repo = make_repo(
                "LugoTUI",
                language="Go",
                stars=5,
                pushed_at=date.today().isoformat(),
                languages={"Go": 8000, "TypeScript": 2000},
            )
            fake_user = MagicMock(login="VintlGvard", public_repos=15, followers=3)
            fake_user.get_repos.return_value = [fake_repo]
            fake_gh = MagicMock()
            fake_gh.get_user.return_value = fake_user

            with (
                patch.object(gen, "connect", return_value=fake_gh),
                patch.dict("os.environ", {"PROFILE_ROOT": str(root), "GH_TOKEN": "tok"}),
            ):
                exit_code = update.main()

            self.assertEqual(exit_code, 0)
            assets_dir = root / "assets"
            expected_files = {
                "hero.svg",
                "contact.svg",
                "shipping.svg",
                "stack.svg",
                "stats.svg",
                "profile.svg",
            }
            self.assertEqual({p.name for p in assets_dir.glob("*.svg")}, expected_files)
            hero_svg = (assets_dir / "hero.svg").read_text(encoding="utf-8")
            contact_svg = (assets_dir / "contact.svg").read_text(encoding="utf-8")
            self.assertIn("15 REPOS", hero_svg)
            self.assertIn("★ 5", hero_svg)
            self.assertIn("3 FOLLOWERS", hero_svg)
            self.assertIn("Lua", contact_svg)

    def test_update_fails_loudly_on_validation_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample_data = {
                "user": {"login": "VintlGvard", "public_repos": 15, "followers": 1},
                "repos": [],
                "stars": 10,
                "shipping": [],
                "languages": [("Go", 100.0)],
                "languages_source": "exact",
                "offline": False,
                "api": {"fetched": 0, "cached": 1},
            }
            with (
                patch.object(gen, "get_data", return_value=sample_data),
                patch.object(gen, "validate_text_constraints", side_effect=ValueError("overflow")),
                patch.dict("os.environ", {"PROFILE_ROOT": str(root)}),
            ):
                exit_code = update.main()

            self.assertNotEqual(exit_code, 0)
            self.assertFalse((root / "assets" / "profile.svg").exists())

    def test_update_calls_validate_text_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample_data = {
                "user": {"login": "VintlGvard", "public_repos": 1, "followers": 1},
                "repos": [],
                "stars": 1,
                "shipping": [
                    {
                        "name": "demo",
                        "description": "Demo repo",
                        "language": "Go",
                        "stargazers_count": 1,
                        "pushed_at": "2026-11-14",
                    }
                ],
                "languages": [("Go", 100.0)],
                "languages_source": "exact",
                "offline": False,
                "api": {"fetched": 1, "cached": 0},
            }
            with (
                patch.object(gen, "get_data", return_value=sample_data),
                patch.object(gen, "validate_text_constraints", wraps=gen.validate_text_constraints) as spy,
                patch.dict("os.environ", {"PROFILE_ROOT": str(root)}),
            ):
                exit_code = update.main()

            self.assertEqual(exit_code, 0)
            spy.assert_called_once_with(sample_data)

    def test_get_data_reuses_repository_objects_without_extra_get_repo_calls(self) -> None:
        fake_repo = make_repo("LugoTUI", language="Go", stars=2, pushed_at="2026-11-14")
        fake_user = MagicMock(login="VintlGvard", public_repos=1, followers=1)
        fake_user.get_repos.return_value = [fake_repo]
        fake_gh = MagicMock()
        fake_gh.get_user.return_value = fake_user

        cache: dict = {}
        with patch.object(gen, "connect", return_value=fake_gh):
            data = gen.get_data("tok", None, cache)

        self.assertEqual(data["languages_source"], "exact")
        fake_repo.get_languages.assert_called_once()
        fake_gh.get_repo.assert_not_called()

        with patch.object(gen, "connect", return_value=fake_gh):
            cached_data = gen.get_data("tok", None, cache)

        self.assertEqual(cached_data["api"], {"fetched": 0, "cached": 1})
        fake_repo.get_languages.assert_called_once()

    def test_atomic_writes_leave_no_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "assets" / "sample.svg"
            cache_file = root / ".lang-cache.json"
            gen.write_text(target, "<svg>ok</svg>")
            gen.save_cache(cache_file, {"repo": {"pushed": "2026-11-14", "langs": {"Go": 10}}})

            self.assertEqual(target.read_text(encoding="utf-8"), "<svg>ok</svg>")
            self.assertEqual(
                json.loads(cache_file.read_text(encoding="utf-8")),
                {"repo": {"pushed": "2026-11-14", "langs": {"Go": 10}}},
            )
            self.assertEqual(list(target.parent.glob("*.tmp")), [])
            self.assertEqual(list(cache_file.parent.glob("*.tmp")), [])

    def test_choose_shipping_filters_archived_forks_and_profile_repo(self) -> None:
        today = date(2026, 11, 14)
        repos = [
            {"name": "VintlGvard", "stargazers_count": 100, "pushed_at": "2026-11-14", "archived": False, "fork": False},
            {"name": "archived-proj", "stargazers_count": 50, "pushed_at": "2026-11-14", "archived": True, "fork": False},
            {"name": "forked-proj", "stargazers_count": 50, "pushed_at": "2026-11-14", "archived": False, "fork": True},
            {"name": "LugoTUI", "stargazers_count": 2, "pushed_at": "2026-11-14", "archived": False, "fork": False},
        ]
        chosen = gen.choose_shipping(repos, now=today)
        self.assertEqual([r["name"] for r in chosen], ["LugoTUI"])

    def test_validate_svg_rejects_unsafe_markup(self) -> None:
        base_ok = (
            '<svg width="900" height="100" viewBox="0 0 900 100" xmlns="http://www.w3.org/2000/svg">'
            "<style>@media (prefers-reduced-motion:reduce){.a{animation:none!important}}</style>"
            "</svg>"
        )
        gen.validate_svg("ok.svg", base_ok)
        for bad in (
            base_ok.replace("</svg>", '<image href="x.png"/></svg>'),
            base_ok.replace("</svg>", '<a href="https://evil.example"></a></svg>'),
            base_ok.replace('viewBox="0 0 900 100"', 'viewBox="0 0 500 100"'),
            base_ok.replace("animation:none!important", ""),
        ):
            with self.assertRaises(ValueError):
                gen.validate_svg("bad.svg", bad)


if __name__ == "__main__":
    unittest.main()
