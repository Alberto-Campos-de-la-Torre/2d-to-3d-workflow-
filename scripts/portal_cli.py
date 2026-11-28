"""CLI usable also with isolated/embedded Python distributions."""
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portal.__main__ import main

if __name__=='__main__':main()
