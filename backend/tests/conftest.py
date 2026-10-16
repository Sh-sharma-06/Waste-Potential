"""
pytest configuration for Waste-Potential backend tests.
Adds the backend source directory to sys.path so all `app.*` imports resolve.
"""
import sys
import os

# Insert backend/ directory so `from app.decision.*` works without installation
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
