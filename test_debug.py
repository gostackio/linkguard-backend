#!/usr/bin/env python
"""Quick debug script to run one test and capture output"""
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_integration.py::test_get_links", "-xvs", "--tb=short"],
    cwd="d:/Projects/linkguard/backend"
)
sys.exit(result.returncode)
