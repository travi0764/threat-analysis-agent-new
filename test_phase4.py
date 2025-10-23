"""
Test script for Phase 4: LangGraph Agent & Classification
Tests the agent workflow, classification, and integration.
"""

import sys
import asyncio
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.config import get_settings
from app.logging_config import setup_logging, get_logger
from app.storage.db import init_database, get_database
from app.storage.repository import IndicatorRepository, EnrichmentRepository, ClassificationRepository
from app.storage.models import Indicator, IndicatorType, SourceType
from app.enrichment.base import get_enricher_registry
from app.enrichment.mock_enrichers import MockWhoisEnricher, MockIPReputationEnricher, MockHashEnricher
from app.enrichment.orchestrator import EnrichmentOrchestrator
from app.classification.classifier import ThreatClassifier
from app.langchain_graph.graph_builder import ThreatAnalysisAgent


def setup_test_environment():
    """Setup test environment."""
    settings = get_settings()
    
    # Check for OpenAI API key
    if not settings.openai_api_key:
        print("\n❌ ERROR: OPENAI_API_KEY not set!")
        print("Please set your OpenAI API key in .env file")
        print("Example: OPENAI_API_KEY=sk-...")
        return False
    
    database_url = f"sqlite:///{settings.database.path}"
    init_database(database_url, echo=False, recreate=True)
    
    setup_logging(log_level="INFO", log_format="text", log_file=None)
    
    # Register enrichers
    registry = get_enricher_registry()
    registry._enrichers.clear()
    registry.register(MockWhoisEnricher())
    registry.register(MockIPReputationEnricher())
    registry.register(MockHashEnricher())
    
    return True


async def test_agent_workflow():
    """Test the LangGraph agent workflow."""
    print("\n" + "="*60)
    print("Testing LangGraph Agent Workflow...")
    print("="*60)
    
    try:
        settings = get_settings()
        
        # Create agent
        agent = ThreatAnalysisAgent()
        print(f"✓ Agent initialized with model: {agent.model_name}")
        
        # Create test indicator
        db = get_database()
        session = db.get_session()
        
        indicator = Indicator(
            indicator_type=IndicatorType.DOMAIN,
            value="evil-malware-site.com",
            source_type=SourceType.MANUAL,
            source_name="test",
            tags=["phishing", "malware"]
        )
        session.add(indicator)
        session.commit()
        session.refresh(indicator)
        
        print(f"✓ Created test indicator: {indicator.value}")
        
        # Enrich it
        orchestrator = EnrichmentOrchestrator(session)
        await orchestrator.enrich_indicator(indicator)
        print(f"✓ Enriched indicator")
        
        # Get enrichments
        enrichment_repo = EnrichmentRepository(session)
        enrichments = enrichment_repo.get_by_indicator(indicator.id)
        
        enrichment_data = [
            {
                "enrichment_type": e.enrichment_type,
                "provider": e.provider,
                "score": e.score,
                "success": e.success,
                "data": e.data,
            }
            for e in enrichments
        ]
        
        print(f"✓ Retrieved {len(enrichment_data)} enrichments")
        
        # Run agent
        print("\n🤖 Running agent workflow...")
        classification = await agent.classify_indicator(indicator, enrichment_data)
        
        if classification:
            print(f"\n📊 Classification Result:")
            print(f"  Risk Level: {classification['risk_level'].upper()}")
            print(f"  Risk Score: {classification['risk_score']:.2f}/10.0")
            print(f"  Confidence: {classification['confidence']:.2f}")
            print(f"  Model: {classification['model']}")
            print(f"\n  Reasoning:")
            print(f"  {classification['reasoning'][:200]}...")
            print(f"\n  Key Factors:")
            for factor in classification['key_factors'][:3]:
                print(f"    - {factor}")
        else:
            print("✗ Classification failed")
            return False
        
        session.close()
        return True
        
    except Exception as e:
        print(f"✗ Agent workflow test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_classifier():
    """Test the ThreatClassifier."""
    print("\n" + "="*60)
    print("Testing ThreatClassifier...")
    print("="*60)
    
    try:
        db = get_database()
        session = db.get_session()
        
        # Create test indicators
        test_cases = [
            ("suspicious-phishing.com", IndicatorType.DOMAIN, ["phishing"]),
            ("10.0.0.1", IndicatorType.IP, ["scanning"]),
            ("a" * 32, IndicatorType.HASH, ["malware"]),  # MD5-like hash
        ]
        
        indicators = []
        for value, itype, tags in test_cases:
            indicator = Indicator(
                indicator_type=itype,
                value=value,
                source_type=SourceType.MANUAL,
                source_name="classifier_test",
                tags=tags
            )
            session.add(indicator)
            indicators.append(indicator)
        
        session.commit()
        
        print(f"✓ Created {len(indicators)} test indicators")
        
        # Enrich them
        orchestrator = EnrichmentOrchestrator(session)
        await orchestrator.enrich_indicators_batch(indicators)
        print(f"✓ Enriched all indicators")
        
        # Classify them
        print("\n🎯 Classifying indicators...")
        classifier = ThreatClassifier(session)
        results = await classifier.classify_batch(indicators, store=True)
        
        successful = sum(1 for c in results.values() if c is not None)
        print(f"✓ Classified {successful}/{len(indicators)} indicators")
        
        # Show results
        classification_repo = ClassificationRepository(session)
        for indicator in indicators:
            classification = classification_repo.get_by_indicator(indicator.id)
            if classification:
                print(f"\n  {indicator.indicator_type.value}: {indicator.value}")
                print(f"    Risk: {classification.risk_level.value.upper()} ({classification.risk_score:.1f}/10)")
                print(f"    Confidence: {classification.confidence:.2f}")
        
        session.close()
        return successful == len(indicators)
        
    except Exception as e:
        print(f"✗ Classifier test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_full_pipeline():
    """Test the complete ingestion → enrichment → classification pipeline."""
    print("\n" + "="*60)
    print("Testing Full Pipeline Integration...")
    print("="*60)
    
    try:
        db = get_database()
        session = db.get_session()
        
        # 1. Ingest
        print("\n1️⃣  Ingestion")
        indicator = Indicator(
            indicator_type=IndicatorType.DOMAIN,
            value="complete-pipeline-test.com",
            source_type=SourceType.CSV_UPLOAD,
            source_name="pipeline_test.csv",
            tags=["test", "pipeline"]
        )
        session.add(indicator)
        session.commit()
        session.refresh(indicator)
        print(f"   ✓ Ingested: {indicator.value}")
        
        # 2. Enrich
        print("\n2️⃣  Enrichment")
        orchestrator = EnrichmentOrchestrator(session)
        enrichments = await orchestrator.enrich_indicator(indicator)
        print(f"   ✓ Enriched with {len(enrichments)} sources")
        
        # 3. Classify
        print("\n3️⃣  Classification")
        classifier = ThreatClassifier(session)
        classification = await classifier.classify_indicator(indicator, store=True)
        
        if classification:
            print(f"   ✓ Classified as: {classification.risk_level.value.upper()}")
            print(f"   ✓ Risk score: {classification.risk_score:.2f}/10")
            print(f"   ✓ Confidence: {classification.confidence:.2f}")
        else:
            print("   ✗ Classification failed")
            return False
        
        # 4. Verify storage
        print("\n4️⃣  Storage Verification")
        enrichment_repo = EnrichmentRepository(session)
        classification_repo = ClassificationRepository(session)
        
        stored_enrichments = enrichment_repo.get_by_indicator(indicator.id)
        stored_classification = classification_repo.get_by_indicator(indicator.id)
        
        print(f"   ✓ Enrichments in DB: {len(stored_enrichments)}")
        print(f"   ✓ Classification in DB: {stored_classification is not None}")
        
        session.close()
        return True
        
    except Exception as e:
        print(f"✗ Full pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_classification_stats():
    """Test classification statistics."""
    print("\n" + "="*60)
    print("Testing Classification Statistics...")
    print("="*60)
    
    try:
        db = get_database()
        session = db.get_session()
        
        classification_repo = ClassificationRepository(session)
        
        # Get stats
        stats = classification_repo.count_by_risk()
        total = sum(stats.values())
        
        print(f"\n📊 Classification Statistics:")
        print(f"  Total: {total}")
        for risk_level, count in stats.items():
            percentage = (count / total * 100) if total > 0 else 0
            print(f"  {risk_level.capitalize():8}: {count:3} ({percentage:5.1f}%)")
        
        session.close()
        return True
        
    except Exception as e:
        print(f"✗ Stats test failed: {e}")
        return False


def main():
    """Run all Phase 4 tests."""
    print("\n" + "="*60)
    print("🧪 PHASE 4: LANGGRAPH AGENT & CLASSIFICATION TEST")
    print("="*60)
    
    # Setup
    if not setup_test_environment():
        return 1
    
    print("\n✓ Environment setup complete")
    print("✓ OpenAI API key configured")
    print("✓ Mock enrichers registered")
    
    # Run tests
    loop = asyncio.get_event_loop()
    
    results = {
        "Agent Workflow": loop.run_until_complete(test_agent_workflow()),
        "Threat Classifier": loop.run_until_complete(test_classifier()),
        "Full Pipeline": loop.run_until_complete(test_full_pipeline()),
        "Classification Stats": loop.run_until_complete(test_classification_stats()),
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
        print("🎉 ALL PHASE 4 TESTS PASSED!")
        print("="*60)
        print("\nLangGraph agent and classification are working!")
        print("\nNext steps:")
        print("1. Start API: uvicorn app.main:app --reload")
        print("2. Upload CSV with full pipeline: POST /api/ingest/upload-csv?enrich=true&classify=true")
        print("3. Classify indicator: POST /api/classify/{id}")
        print("4. View stats: GET /api/classify/stats")
        print("5. Filter by risk: GET /api/classify/risk/high")
    else:
        print("❌ SOME TESTS FAILED")
        print("="*60)
        print("\nTroubleshooting:")
        print("1. Make sure OPENAI_API_KEY is set in .env")
        print("2. Check logs for detailed error messages")
        print("3. Verify internet connection for OpenAI API")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
