"""Test script for CLI"""

import sys
from orbit.cli import main

if __name__ == "__main__":
    # Test various commands
    test_cases = [
        ["orbit", "--help"],
        ["orbit", "--version"],
        ["orbit", "gateway", "--help"],
        ["orbit", "gateway", "status"],
        ["orbit", "gateway", "call", "health"],
        ["orbit", "gateway", "discover"],
    ]
    
    if len(sys.argv) > 1:
        # Run specific test
        test_num = int(sys.argv[1])
        if 0 <= test_num < len(test_cases):
            main(test_cases[test_num])
    else:
        # Run all tests
        print("Running CLI tests...")
        for i, test_case in enumerate(test_cases):
            print(f"\n=== Test {i}: {' '.join(test_case)} ===")
            try:
                main(test_case)
            except SystemExit:
                pass  # Expected for some commands
