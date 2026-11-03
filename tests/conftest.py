"""The pure-Python parts (hpcrypto, parse) are tested on their own: put the integration's folder on the path."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "custom_components" / "wardyn"))   # last: its event.py etc. must not hide the standard library
