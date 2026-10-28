import os
import re
from pathlib import Path

import pytest

ENV_FILE = Path(__file__).resolve().parent.parent / ".env.sh"


def _load_env_sh():
    """Read `export NAME="value"` lines from .env.sh without echoing them."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        m = re.match(r'\s*export\s+(\w+)=["\']?([^"\']*)["\']?\s*$', line)
        if m and m.group(1) not in os.environ:
            os.environ[m.group(1)] = m.group(2)


_load_env_sh()

# pytest must never submit paid QpiAI platform jobs (see schedule/platform_guard.py).
os.environ["QSHIELD_FORBID_PLATFORM"] = "1"


@pytest.fixture(scope="session")
def opt_client():
    if not os.environ.get("QPIAI_OPT_API_KEY"):
        pytest.skip("QPIAI_OPT_API_KEY not set; QpiAI Opt solver tests skipped")
    from qpiai_opt.opt_solvers import Client

    return Client(api_key=os.environ["QPIAI_OPT_API_KEY"])
