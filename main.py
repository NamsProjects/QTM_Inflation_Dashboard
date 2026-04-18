"""
main.py
-------
Entry point for the QTM Inflation Dashboard.

Usage:
    python main.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from gui import run

if __name__ == "__main__":
    run()