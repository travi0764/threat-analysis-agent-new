"""
Test script to verify the foundation setup.
Run this to ensure configuration, logging, and database are working.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.config import get_settings
from app.logging_config import setup_logging, get_logger
from app.storage.db import init_database, get_database
from app.storage.models import Indicator, IndicatorType, SourceType
from app.utils.helpers import detect_indicator_type, normalize_indicator


def test_configuration():
    """Test configuration loading."""
    print("\n" + "="*60)
    print("Testing Configuration...")
    print("="*60)
    
    try:
        settings = get_settings()
        print(f"✓ Configuration loaded successfully")
        print(f"  App Name: {settings.app.name}")
        print(f"  Version: {settings.app.version}")
        print(f"  Database: {settings.database.path}")
        print(f"  OpenAI Model: {settings.openai.model}")
        return True
    except Exception as e:
        print(f"✗ Configuration failed: {e}")
        return False


def test_logging():
    """Test logging setup."""
    print("\n" + "="*60)
    print("Testing Logging...")
    print("="*60)
    
    try:
        settings = get_settings()
        setup_logging(
            log_level=settings.logging.level,
            log_format=settings.logging.format,
            log_file=settings.logging.file,
        )
        
        logger = get_logger(__name__)
        logger.info("Test log message - INFO level")
        logger.warning("Test log message - WARNING level")
        logger.debug("Test log message - DEBUG level")
        
        print(f"✓ Logging configured successfully")
        print(f"  Level: {settings.logging.level}")
        print(f"  Format: {settings.logging.format}")
        print(f"  File: {settings.logging.file}")
        return True
    except Exception as e:
        print(f"✗ Logging failed: {e}")
        return False


def test_database():
    """Test database setup."""
    print("\n" + "="*60)
    print("Testing Database...")
    print("="*60)
    
    try:
        settings = get_settings()
        database_url = f"sqlite:///{settings.database.path}"
        
        # Initialize database
        init_database(database_url, echo=False, recreate=True)
        print(f"✓ Database initialized: {settings.database.path}")
        
        # Test database operations
        db = get_database()
        session = db.get_session()
        
        # Create a test indicator
        test_indicator = Indicator(
            indicator_type=IndicatorType.DOMAIN,
            value="test-domain.com",
            source_type=SourceType.MANUAL,
            source_name="test",
        )
        session.add(test_indicator)
        session.commit()
        
        # Query it back
        retrieved = session.query(Indicator).filter_by(value="test-domain.com").first()
        if retrieved:
            print(f"✓ Database operations working")
            print(f"  Created indicator: {retrieved.value} ({retrieved.indicator_type.value})")
        else:
            print(f"✗ Could not retrieve test indicator")
            return False
        
        # Clean up
        session.delete(retrieved)
        session.commit()
        session.close()
        
        return True
    except Exception as e:
        print(f"✗ Database failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_helpers():
    """Test helper utilities."""
    print("\n" + "="*60)
    print("Testing Helper Utilities...")
    print("="*60)
    
    try:
        test_cases = [
            ("evil-domain.com", IndicatorType.DOMAIN),
            ("192.168.1.1", IndicatorType.IP),
            ("5d41402abc4b2a76b9719d911017c592", IndicatorType.HASH),
            ("http://example.com/malware", IndicatorType.URL),
            ("evil@example.com", IndicatorType.EMAIL),
        ]
        
        all_passed = True
        for value, expected_type in test_cases:
            detected_type = detect_indicator_type(value)
            normalized = normalize_indicator(value, detected_type)
            
            if detected_type == expected_type:
                print(f"✓ {value:40} -> {detected_type.value:10} (normalized: {normalized})")
            else:
                print(f"✗ {value:40} -> Expected {expected_type.value}, got {detected_type.value}")
                all_passed = False
        
        return all_passed
    except Exception as e:
        print(f"✗ Helpers failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("🧪 THREAT ANALYSIS AGENT - FOUNDATION TEST")
    print("="*60)
    
    results = {
        "Configuration": test_configuration(),
        "Logging": test_logging(),
        "Database": test_database(),
        "Helpers": test_helpers(),
    }
    
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name:20} {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Foundation is ready.")
        print("="*60)
        print("\nNext steps:")
        print("1. Set your OPENAI_API_KEY in .env file")
        print("2. Run: uvicorn app.main:app --reload")
        print("3. Visit: http://localhost:8000/docs")
    else:
        print("❌ SOME TESTS FAILED. Please fix the issues above.")
        print("="*60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
