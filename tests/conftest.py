import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/demo_project"))

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demo.settings")

from .fixtures.types import *  # noqa
from .fixtures.simple_app import *  # noqa
import django  # noqa

django.setup()


def pytest_generate_tests(metafunc):
    os.environ["NINJA_SKIP_REGISTRY"] = "yes"
