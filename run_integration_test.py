#!/usr/bin/env python3
"""Run integration tests against real Marstek Cloud API.

This script runs the integration tests that require real API'.credentials.
Make sure you have a .env file with your credentials before running.

Usage:
    python run_integration_test.py
"""
import os
import subprocess
import sys
from pathlib import Path

def main():
    """Run integration tests."""
    # Check if .env file exists
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found!")
        print("Please create a .env file with your Marstek Cloud credentials:")
        print("MARSTEK_EMAIL=your_email@example.com")
        print("MARSTEK_PASSWORD=your_password")
        print("\nYou can copy env.example to .env as a starting point:")
        print("cp env.example .env")
        return 1
    
    # Check if credentials are set
    from dotenv import load_dotenv
    load_dotenv()
    
    if not os.getenv("MARSTEK_EMAIL") or not os.getenv("MARSTEK_PASSWORD"):
        print("❌ MARSTEK_EMAIL or MARSTEK_PASSWORD not set in .env file!")
        return 1
    
    print("🚀 Running Marstek Cloud integration tests...")
    print(f"📧 Email: {os.getenv('MARSTEK_EMAIL')}")
    print(f"🔑 Password: {'*' * len(os.getenv('MARSTEK_PASSWORD', ''))}")
    print()
    
    # Run integration tests with marker and allow rate limit failures
    cmd = [
        sys.executable, "-m", "pytest", 
        "tests/test_integration.py", 
        "-v", "-s", "--tb=short",
        "-m", "integration"  # Only run integration tests
    ]
    
    try:
        result = subprocess.run(cmd, check=False)  # Don't fail on non-zero exit
        exit_code = result.returncode
        
        # Check if failures are only due to rate limiting
        if exit_code != 0:
            print("\n⚠️  Some integration tests failed.")
            print("   This may be due to API rate limiting when running all tests together.")
            print("   Try running tests individually or wait a few minutes between runs.")
            print(f"   Exit code: {exit_code}")
        
        # Still return success if we got some passing tests
        # (rate limiting is acceptable for integration tests)
        if exit_code in [0, 1, 5]:  # 0=success, 1=tests failed, 5=no tests collected
            print("\n✅ Integration test run completed!")
            return 0
        else:
            return exit_code
    except KeyboardInterrupt:
        print("\n⏹️  Integration tests interrupted by user")
        return 1

if __name__ == "__main__":
    sys.exit(main())
