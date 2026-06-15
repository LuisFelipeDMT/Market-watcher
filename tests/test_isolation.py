"""Phase 4: prove the analysis zone has no path to brokerage credentials.

Two guarantees:
1. Importing the remote collector clients does NOT pull in the secrets module or
   the credential-bearing producer (checked in a clean subprocess).
2. The analysis engine packages contain no reference to credential material
   (static source scan — catches accidental future imports).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]

# Packages that make up the internet-facing analysis zone (zone B).
_ANALYSIS_PACKAGES = [
    "app/tracker",
    "app/analysis",
    "app/equities",
    "app/market",
    "app/alerts",
    "app/api",
    "app/mobile",
]

# Strings that would indicate a path to credentials leaking into zone B.
_FORBIDDEN = [
    "app.collector.secrets",
    "app.collector.sources",
    "app.collector.session",
    "load_broker_credentials",
    "BrokerCredentials",
    "XPCollector",
    "xp_password",
]


def test_remote_clients_do_not_import_credentials():
    code = (
        "import sys; import app.collector.remote;"
        "bad=[m for m in ('app.collector.secrets',"
        "'app.collector.sources.xp_scraper','app.collector.session')"
        " if m in sys.modules];"
        "print('LOADED:'+','.join(bad)); sys.exit(1 if bad else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=_REPO, capture_output=True, text=True
    )
    assert result.returncode == 0, f"credential modules leaked: {result.stdout}"


@pytest.mark.parametrize("package", _ANALYSIS_PACKAGES)
def test_analysis_packages_have_no_credential_references(package):
    offenders: list[str] = []
    for path in (_REPO / package).rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN:
            if token in text:
                offenders.append(f"{path.relative_to(_REPO)}: {token}")
    assert not offenders, "credential references in analysis zone: " + "; ".join(
        offenders
    )
