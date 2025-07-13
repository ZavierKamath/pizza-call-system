"""
Test runner for validation engine test suite.
Runs comprehensive tests for all validation components and generates coverage reports.
"""

import sys
import os
import subprocess
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_validation_tests():
    """Run all validation-related tests with coverage reporting."""
    
    test_files = [
        "tests/test_validation_engines.py",
        "tests/test_agent_validation_integration.py",
        "tests/test_voice_integration.py"  # Include voice integration tests
    ]
    
    logger.info("Starting validation test suite...")
    
    # Base pytest command with coverage
    base_cmd = [
        "python", "-m", "pytest",
        "--verbose",
        "--tb=short",
        "--durations=10",
        "--cov=validation",
        "--cov=agents",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
    ]
    
    # Add test files that exist
    existing_test_files = []
    for test_file in test_files:
        if os.path.exists(test_file):
            existing_test_files.append(test_file)
            logger.info(f"Including test file: {test_file}")
        else:
            logger.warning(f"Test file not found: {test_file}")
    
    if not existing_test_files:
        logger.error("No test files found!")
        return False
    
    # Run tests
    cmd = base_cmd + existing_test_files
    
    try:
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=project_root)
        
        # Print output
        print("=" * 80)
        print("TEST OUTPUT")
        print("=" * 80)
        print(result.stdout)
        
        if result.stderr:
            print("=" * 80)
            print("ERRORS/WARNINGS")
            print("=" * 80)
            print(result.stderr)
        
        # Check if tests passed
        if result.returncode == 0:
            logger.info("✅ All tests passed!")
            print("\n" + "=" * 80)
            print("✅ VALIDATION TEST SUITE COMPLETED SUCCESSFULLY")
            print("=" * 80)
            
            # Print coverage summary
            if os.path.exists("htmlcov/index.html"):
                print("📊 Coverage report generated at: htmlcov/index.html")
            
            return True
        else:
            logger.error(f"❌ Tests failed with return code: {result.returncode}")
            print("\n" + "=" * 80)
            print("❌ VALIDATION TEST SUITE FAILED")
            print("=" * 80)
            return False
            
    except FileNotFoundError:
        logger.error("pytest not found. Please install pytest and pytest-cov:")
        print("pip install pytest pytest-cov pytest-asyncio")
        return False
    except Exception as e:
        logger.error(f"Error running tests: {e}")
        return False


def run_specific_test_category(category: str):
    """Run tests for a specific category."""
    
    category_map = {
        "address": ["tests/test_validation_engines.py::TestAddressValidator"],
        "order": ["tests/test_validation_engines.py::TestOrderValidator"], 
        "payment": ["tests/test_validation_engines.py::TestPaymentValidator"],
        "formatting": ["tests/test_validation_engines.py::TestValidationErrorFormatter"],
        "integration": ["tests/test_agent_validation_integration.py"],
        "voice": ["tests/test_voice_integration.py"]
    }
    
    if category not in category_map:
        logger.error(f"Unknown test category: {category}")
        logger.info(f"Available categories: {', '.join(category_map.keys())}")
        return False
    
    test_targets = category_map[category]
    
    cmd = [
        "python", "-m", "pytest",
        "--verbose",
        "--tb=short"
    ] + test_targets
    
    try:
        logger.info(f"Running {category} tests...")
        result = subprocess.run(cmd, cwd=project_root)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error running {category} tests: {e}")
        return False


def main():
    """Main test runner entry point."""
    
    if len(sys.argv) > 1:
        category = sys.argv[1]
        success = run_specific_test_category(category)
    else:
        success = run_validation_tests()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()