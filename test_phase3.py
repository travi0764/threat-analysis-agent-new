"""
Test script for Phase 3: Enrichment Layer
Tests enrichers, orchestration, and integration with ingestion.
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.config import get_settings
from app.logging_config import setup_logging, get_logger
from app.storage.db import init_database, get_database
from app.storage.repository import IndicatorRepository, EnrichmentRepository
from app.storage.models import Indicator, IndicatorType, SourceType
from app.enrichment.base import get_enricher_registry
from app.enrichment.mock_enrichers import (
    MockWhoisEnricher, 
    MockIPReputationEnricher, 
    MockHashEnricher
)
from app.enrichment.orchestrator import EnrichmentOrchestrator


def setup_test_environment():
    """Setup test environment."""
    settings = get_settings()
    database_url = f"sqlite:///{settings.database.path}"
    init_database(database_url, echo=False, recreate=True)
    
    setup_logging(log_level="INFO", log_format="text", log_file=None)
    
    return settings


def test_enricher_registration():
    """Test enricher registration."""
    print("\n" + "="*60)
    print("Testing Enricher Registration...")
    print("="*60)
    
    try:
        registry = get_enricher_registry()
        
        # Clear registry for test
        registry._enrichers.clear()
        
        # Register enrichers
        whois = MockWhoisEnricher()
        ip_rep = MockIPReputationEnricher()
        hash_lookup = MockHashEnricher()
        
        registry.register(whois)
        registry.register(ip_rep)
        registry.register(hash_lookup)
        
        # Check registration
        enrichers = registry.list_enrichers()
        print(f"✓ Registered {len(enrichers)} enrichers:")
        for enrichment_type, provider in enrichers:
            print(f"  - {enrichment_type}:{provider}")
        
        # Test type filtering
        domain_enrichers = registry.get_enrichers_for_type(IndicatorType.DOMAIN)
        ip_enrichers = registry.get_enrichers_for_type(IndicatorType.IP)
        hash_enrichers = registry.get_enrichers_for_type(IndicatorType.HASH)
        
        print(f"\n✓ Enrichers by type:")
        print(f"  - Domains: {len(domain_enrichers)}")
        print(f"  - IPs: {len(ip_enrichers)}")
        print(f"  - Hashes: {len(hash_enrichers)}")
        
        return len(enrichers) == 3
        
    except Exception as e:
        print(f"✗ Enricher registration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_individual_enrichers():
    """Test individual enrichers."""
    print("\n" + "="*60)
    print("Testing Individual Enrichers...")
    print("="*60)
    
    try:
        # Test WHOIS enricher
        whois = MockWhoisEnricher()
        print("\n🔍 Testing WHOIS enricher...")
        result = await whois.enrich("evil-domain.com", IndicatorType.DOMAIN)
        
        print(f"  Success: {result.success}")
        print(f"  Score: {result.score}")
        print(f"  Data keys: {list(result.data.keys())}")
        if result.data:
            print(f"  Registrar: {result.data.get('registrar')}")
            print(f"  Creation: {result.data.get('creation_date')}")
        
        # Test IP enricher
        ip_rep = MockIPReputationEnricher()
        print("\n🔍 Testing IP reputation enricher...")
        result = await ip_rep.enrich("192.0.2.1", IndicatorType.IP)
        
        print(f"  Success: {result.success}")
        print(f"  Score: {result.score}")
        print(f"  Abuse confidence: {result.data.get('abuse_confidence_score')}")
        print(f"  Total reports: {result.data.get('total_reports')}")
        
        # Test Hash enricher
        hash_lookup = MockHashEnricher()
        print("\n🔍 Testing hash enricher...")
        result = await hash_lookup.enrich("5d41402abc4b2a76b9719d911017c592", IndicatorType.HASH)
        
        print(f"  Success: {result.success}")
        print(f"  Score: {result.score}")
        print(f"  Detection ratio: {result.data.get('detection_ratio')}")
        print(f"  Is malware: {result.data.get('is_malware')}")
        
        return True
        
    except Exception as e:
        print(f"✗ Individual enricher test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_enrichment_orchestrator():
    """Test enrichment orchestrator."""
    print("\n" + "="*60)
    print("Testing Enrichment Orchestrator...")
    print("="*60)
    
    try:
        db = get_database()
        session = db.get_session()
        repo = IndicatorRepository(session)
        enrichment_repo = EnrichmentRepository(session)
        
        # Register enrichers
        registry = get_enricher_registry()
        registry._enrichers.clear()
        registry.register(MockWhoisEnricher())
        registry.register(MockIPReputationEnricher())
        registry.register(MockHashEnricher())
        
        # Create test indicators
        test_indicators = [
            Indicator(
                indicator_type=IndicatorType.DOMAIN,
                value="test-malware-site.com",
                source_type=SourceType.MANUAL,
                source_name="test"
            ),
            Indicator(
                indicator_type=IndicatorType.IP,
                value="10.0.0.1",
                source_type=SourceType.MANUAL,
                source_name="test"
            ),
            Indicator(
                indicator_type=IndicatorType.HASH,
                value="e99a18c428cb38d5f260853678922e03",
                source_type=SourceType.MANUAL,
                source_name="test"
            ),
        ]
        
        for indicator in test_indicators:
            session.add(indicator)
        session.commit()
        
        print(f"✓ Created {len(test_indicators)} test indicators")
        
        # Create orchestrator
        orchestrator = EnrichmentOrchestrator(session)
        
        # Enrich indicators
        print("\n📥 Enriching indicators...")
        results = await orchestrator.enrich_indicators_batch(test_indicators)
        
        # Check results
        for indicator in test_indicators:
            enrichments = enrichment_repo.get_by_indicator(indicator.id)
            summary = orchestrator.get_enrichment_summary(indicator.id)
            
            print(f"\n📊 {indicator.indicator_type.value}: {indicator.value}")
            print(f"  Enrichments: {summary['total_enrichments']}")
            print(f"  Successful: {summary['successful']}")
            print(f"  Failed: {summary['failed']}")
            print(f"  Avg score: {summary['average_score']:.2f}")
            print(f"  Max score: {summary['max_score']:.2f}")
            
            for enrichment in enrichments:
                print(f"  - {enrichment.enrichment_type}:{enrichment.provider} = {enrichment.score:.2f}")
        
        session.close()
        
        return all(len(result) > 0 for result in results.values())
        
    except Exception as e:
        print(f"✗ Orchestrator test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_enrichment_with_ingestion():
    """Test enrichment integration with ingestion."""
    print("\n" + "="*60)
    print("Testing Enrichment + Ingestion Integration...")
    print("="*60)
    
    try:
        db = get_database()
        session = db.get_session()
        repo = IndicatorRepository(session)
        
        # Register enrichers
        registry = get_enricher_registry()
        registry._enrichers.clear()
        registry.register(MockWhoisEnricher())
        registry.register(MockIPReputationEnricher())
        registry.register(MockHashEnricher())
        
        # Create an indicator (simulating ingestion)
        indicator = Indicator(
            indicator_type=IndicatorType.DOMAIN,
            value="phishing-site-test.com",
            source_type=SourceType.CSV_UPLOAD,
            source_name="integration_test.csv",
            tags=["phishing", "test"]
        )
        session.add(indicator)
        session.commit()
        session.refresh(indicator)
        
        print(f"✓ Created indicator: {indicator.value} (ID: {indicator.id})")
        
        # Enrich it
        orchestrator = EnrichmentOrchestrator(session)
        results = await orchestrator.enrich_indicator(indicator)
        
        print(f"✓ Performed {len(results)} enrichments")
        
        # Verify enrichments are stored
        enrichment_repo = EnrichmentRepository(session)
        stored_enrichments = enrichment_repo.get_by_indicator(indicator.id)
        
        print(f"✓ Stored {len(stored_enrichments)} enrichments in database")
        
        for enrichment in stored_enrichments:
            print(f"  - {enrichment.enrichment_type}: score={enrichment.score:.2f}, success={enrichment.success}")
        
        session.close()
        
        return len(stored_enrichments) > 0
        
    except Exception as e:
        print(f"✗ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all Phase 3 tests."""
    print("\n" + "="*60)
    print("🧪 PHASE 3: ENRICHMENT LAYER TEST")
    print("="*60)
    
    # Setup
    setup_test_environment()
    
    # Run tests
    results = {
        "Enricher Registration": test_enricher_registration(),
    }
    
    # Async tests
    loop = asyncio.get_event_loop()
    results["Individual Enrichers"] = loop.run_until_complete(test_individual_enrichers())
    results["Enrichment Orchestrator"] = loop.run_until_complete(test_enrichment_orchestrator())
    results["Ingestion Integration"] = loop.run_until_complete(test_enrichment_with_ingestion())
    
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name:30} {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL PHASE 3 TESTS PASSED!")
        print("="*60)
        print("\nEnrichment layer is working correctly!")
        print("\nNext steps:")
        print("1. Start the API: uvicorn app.main:app --reload")
        print("2. Upload CSV with enrichment: POST /api/ingest/upload-csv?enrich=true")
        print("3. View enriched indicators: GET /api/indicators")
        print("4. Manually enrich: POST /api/indicators/{id}/enrich")
    else:
        print("❌ SOME TESTS FAILED")
        print("="*60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
