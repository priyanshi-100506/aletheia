import sys
import pathlib

import pytest

# Add all scenario directories to PYTHONPATH for tests
base_dir = pathlib.Path(__file__).parent / "portfolio_scenarios"
if base_dir.exists():
    for child in base_dir.iterdir():
        if child.is_dir():
            sys.path.append(str(child))


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Classify tests without suppressing collection of intentional fixtures."""
    repo_root = pathlib.Path(__file__).parent.resolve()
    for item in items:
        path = pathlib.Path(str(item.fspath)).resolve()
        relative = path.relative_to(repo_root)
        if relative.parts[0] == "tests":
            item.add_marker(pytest.mark.aletheia)
        elif relative.parts[0] == "portfolio_scenarios":
            item.add_marker(pytest.mark.portfolio)
        elif relative.parts[0] == "aletheia-demo-bugs":
            item.add_marker(pytest.mark.controlled_demo)
