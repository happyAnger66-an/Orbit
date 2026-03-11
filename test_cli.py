"""Test script for CLI"""

import sys
from mw4agent.cli import main

if __name__ == "__main__":
    # Test various commands
    test_cases = [
        ["mw4agent", "--help"],
        ["mw4agent", "--version"],
        ["mw4agent", "gateway", "--help"],
        ["mw4agent", "gateway", "status"],
        ["mw4agent", "gateway", "call", "health"],
        ["mw4agent", "gateway", "discover"],
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
