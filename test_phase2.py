"""
Test script for Phase 2: Data Ingestion
Tests CSV ingestion, validation, and database operations.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.config import get_settings
from app.logging_config import setup_logging, get_logger
from app.storage.db import init_database, get_database
from app.storage.repository import IndicatorRepository
from app.ingestion.csv_ingestor import CSVIngestor
from app.storage.models import IndicatorType, SourceType


def test_csv_ingestion():
    """Test CSV file ingestion."""
    print("\n" + "="*60)
    print("Testing CSV Ingestion...")
    print("="*60)
    
    try:
        # Setup
        settings = get_settings()
        database_url = f"sqlite:///{settings.database.path}"
        init_database(database_url, echo=False, recreate=True)
        
        db = get_database()
        session = db.get_session()
        
        # Test with sample CSV file
        csv_file = project_root / "sample_indicators.csv"
        
        if not csv_file.exists():
            print(f"✗ Sample CSV file not found: {csv_file}")
            return False
        
        print(f"📄 Reading CSV file: {csv_file.name}")
        
        with open(csv_file, 'r') as f:
            content = f.read()
        
        # Create ingestor
        ingestor = CSVIngestor(
            source_name="test_csv",
            auto_detect_type=True,
            skip_duplicates=True
        )
        
        # Validate CSV
        print("✓ Validating CSV format...")
        if not ingestor.validate(content):
            print("✗ CSV validation failed")
            return False
        
        print("✓ CSV format is valid")
        
        # Ingest data
        print("📥 Ingesting indicators...")
        result = ingestor.ingest(content, session)
        
        # Display results
        print(f"\n📊 Ingestion Results:")
        print(f"  Success: {result.success}")
        print(f"  Processed: {result.indicators_processed}")
        print(f"  Created: {result.indicators_created}")
        print(f"  Updated: {result.indicators_updated}")
        print(f"  Failed: {result.indicators_failed}")
        
        if result.errors:
            print(f"\n❌ Errors ({len(result.errors)}):")
            for error in result.errors[:5]:  # Show first 5 errors
                print(f"    Row {error['row']}: {error['error']}")
        
        # Verify indicators in database
        repo = IndicatorRepository(session)
        all_indicators = repo.get_all(limit=100)
        
        print(f"\n📋 Indicators in Database: {len(all_indicators)}")
        for indicator in all_indicators[:5]:  # Show first 5
            print(f"  - {indicator.indicator_type.value:8} | {indicator.value:40} | {indicator.source_name}")
        
        if len(all_indicators) > 5:
            print(f"  ... and {len(all_indicators) - 5} more")
        
        session.close()
        
        return result.success and result.indicators_created > 0
        
    except Exception as e:
        print(f"✗ CSV ingestion test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_simplified_csv():
    """Test simplified CSV with auto-detection."""
    print("\n" + "="*60)
    print("Testing Simplified CSV (Auto-detect)...")
    print("="*60)
    
    try:
        db = get_database()
        session = db.get_session()
        
        csv_file = project_root / "sample_simple.csv"
        
        if not csv_file.exists():
            print(f"✗ Simplified CSV file not found: {csv_file}")
            return False
        
        print(f"📄 Reading CSV file: {csv_file.name}")
        
        with open(csv_file, 'r') as f:
            content = f.read()
        
        ingestor = CSVIngestor(
            source_name="test_simple",
            auto_detect_type=True,
            skip_duplicates=True
        )
        
        result = ingestor.ingest(content, session)
        
        print(f"\n📊 Results:")
        print(f"  Created: {result.indicators_created}")
        print(f"  Failed: {result.indicators_failed}")
        
        session.close()
        
        return result.success
        
    except Exception as e:
        print(f"✗ Simplified CSV test failed: {e}")
        return False


def test_repository_operations():
    """Test repository CRUD operations."""
    print("\n" + "="*60)
    print("Testing Repository Operations...")
    print("="*60)
    
    try:
        db = get_database()
        session = db.get_session()
        repo = IndicatorRepository(session)
        
        # Test search
        print("\n🔍 Testing search...")
        results = repo.search("evil", limit=5)
        print(f"  Found {len(results)} indicators matching 'evil'")
        
        # Test filtering by type
        print("\n🔍 Testing filter by type...")
        domains = repo.get_all(indicator_type=IndicatorType.DOMAIN, limit=10)
        ips = repo.get_all(indicator_type=IndicatorType.IP, limit=10)
        hashes = repo.get_all(indicator_type=IndicatorType.HASH, limit=10)
        
        print(f"  Domains: {len(domains)}")
        print(f"  IPs: {len(ips)}")
        print(f"  Hashes: {len(hashes)}")
        
        # Test count
        print("\n📊 Testing count...")
        total = repo.count()
        domain_count = repo.count(indicator_type=IndicatorType.DOMAIN)
        print(f"  Total indicators: {total}")
        print(f"  Domain indicators: {domain_count}")
        
        session.close()
        
        return True
        
    except Exception as e:
        print(f"✗ Repository operations test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all Phase 2 tests."""
    print("\n" + "="*60)
    print("🧪 PHASE 2: DATA INGESTION TEST")
    print("="*60)
    
    # Setup logging
    settings = get_settings()
    setup_logging(
        log_level="INFO",
        log_format="text",
        log_file=None,  # Console only for tests
    )
    
    results = {
        "CSV Ingestion": test_csv_ingestion(),
        "Simplified CSV": test_simplified_csv(),
        "Repository Operations": test_repository_operations(),
    }
    
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name:30} {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL PHASE 2 TESTS PASSED!")
        print("="*60)
        print("\nData ingestion is working correctly!")
        print("\nNext steps:")
        print("1. Start the API: uvicorn app.main:app --reload")
        print("2. Test CSV upload via Swagger UI: http://localhost:8000/docs")
        print("3. Upload sample_indicators.csv using the /api/ingest/upload-csv endpoint")
    else:
        print("❌ SOME TESTS FAILED")
        print("="*60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
