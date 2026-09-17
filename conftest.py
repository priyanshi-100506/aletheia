import sys
import pathlib

# Add all scenario directories to PYTHONPATH for tests
base_dir = pathlib.Path(__file__).parent / "portfolio_scenarios"
if base_dir.exists():
    for child in base_dir.iterdir():
        if child.is_dir():
            sys.path.append(str(child))
