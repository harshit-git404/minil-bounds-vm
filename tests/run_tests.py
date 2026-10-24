#!/usr/bin/env python3
"""
Test runner for MiniL.
Discovers and runs all unit tests and integration tests.
"""
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import unittest

def run_all_tests():
    test_dir = os.path.dirname(os.path.abspath(__file__))
    suite = unittest.defaultTestLoader.discover(start_dir=test_dir, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if result.wasSuccessful():
        print("\nAll MiniL Stage 1 tests passed successfully!")
        sys.exit(0)
    else:
        print(f"\nTests failed: {len(result.failures)} failures, {len(result.errors)} errors")
        sys.exit(1)

if __name__ == "__main__":
    run_all_tests()
