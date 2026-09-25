import shutil
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent
_BROWSER: bool | None = None


def chromium_ok() -> bool:
    global _BROWSER
    if _BROWSER is None:
        try:
            from guidekit.render import browser

            with browser():
                _BROWSER = True
        except Exception:
            _BROWSER = False
    return _BROWSER


@pytest.fixture
def need_browser():
    if not chromium_ok():
        pytest.skip("Playwright Chromium not available (run `playwright install chromium` or set GUIDEKIT_CHROMIUM)")


def copy_fixture(name: str, tmp_path: Path) -> Path:
    dst = tmp_path / name
    shutil.copytree(FIX / name, dst, ignore=shutil.ignore_patterns("out"))
    return dst


@pytest.fixture
def showcase(tmp_path) -> Path:
    return copy_fixture("showcase", tmp_path)


@pytest.fixture
def minimal(tmp_path) -> Path:
    return copy_fixture("minimal", tmp_path)
