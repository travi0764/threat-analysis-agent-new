#!/usr/bin/env python3
"""
File verification script for Threat Analysis Agent.
Checks that all required files exist and have content.
"""

import os
import sys
from pathlib import Path

# Required files with minimum line counts (0 = any size is ok)
REQUIRED_FILES = {
    # Root files
    "README.md": 10,
    "QUICKSTART.md": 10,
    "config.yaml": 10,
    "requirements.txt": 10,
    ".env.example": 5,
    "sample_indicators.csv": 5,
    
    # App core
    "app/__init__.py": 0,
    "app/main.py": 50,
    "app/config.py": 50,
    "app/logging_config.py": 50,
    
    # API
    "app/api/__init__.py": 0,
    "app/api/ingest.py": 50,
    "app/api/query.py": 50,
    "app/api/classify.py": 50,
    
    # Storage
    "app/storage/__init__.py": 0,
    "app/storage/db.py": 50,
    "app/storage/models.py": 50,
    "app/storage/repository.py": 50,
    
    # Ingestion
    "app/ingestion/__init__.py": 0,
    "app/ingestion/ingestor.py": 50,
    "app/ingestion/csv_ingestor.py": 50,
    
    # Enrichment
    "app/enrichment/__init__.py": 0,
    "app/enrichment/base.py": 50,
    "app/enrichment/mock_enrichers.py": 50,
    "app/enrichment/orchestrator.py": 50,
    
    # Classification
    "app/classification/__init__.py": 0,
    "app/classification/classifier.py": 50,
    
    # LangChain
    "app/langchain_graph/__init__.py": 0,
    "app/langchain_graph/graph_builder.py": 50,
    
    # Utils
    "app/utils/__init__.py": 0,
    "app/utils/helpers.py": 50,
    "app/utils/exceptions.py": 10,
    
    # Core
    "app/core/__init__.py": 0,
    
    # UI
    "ui/index.html": 50,
    "ui/styles.css": 100,
    "ui/app.js": 100,
    
    # Tests
    "test_foundation.py": 50,
    "test_phase2.py": 50,
    "test_phase3.py": 50,
    "test_phase4.py": 50,
}


def count_lines(filepath):
    """Count non-empty lines in a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return sum(1 for line in f if line.strip())
    except:
        return 0


def verify_files():
    """Verify all required files exist and have content."""
    project_root = Path(__file__).parent
    
    print("🔍 Verifying Threat Analysis Agent Installation")
    print("=" * 60)
    print(f"Project root: {project_root}")
    print()
    
    missing_files = []
    empty_files = []
    ok_files = []
    
    for filepath, min_lines in REQUIRED_FILES.items():
        full_path = project_root / filepath
        
        if not full_path.exists():
            missing_files.append(filepath)
            print(f"❌ MISSING: {filepath}")
        else:
            line_count = count_lines(full_path)
            
            if min_lines > 0 and line_count < min_lines:
                empty_files.append((filepath, line_count, min_lines))
                print(f"⚠️  TOO SMALL: {filepath} ({line_count} lines, expected {min_lines}+)")
            else:
                ok_files.append(filepath)
                if line_count > 0:
                    print(f"✅ OK: {filepath} ({line_count} lines)")
                else:
                    print(f"✅ OK: {filepath} (empty __init__.py)")
    
    print()
    print("=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"✅ OK: {len(ok_files)} files")
    print(f"⚠️  Too small: {len(empty_files)} files")
    print(f"❌ Missing: {len(missing_files)} files")
    
    if missing_files:
        print("\n❌ MISSING FILES:")
        for f in missing_files:
            print(f"   - {f}")
    
    if empty_files:
        print("\n⚠️  FILES TOO SMALL (might be incomplete):")
        for f, actual, expected in empty_files:
            print(f"   - {f}: {actual} lines (expected {expected}+)")
    
    print()
    
    if missing_files or empty_files:
        print("❌ VERIFICATION FAILED!")
        print("\nSome files are missing or incomplete.")
        print("Please re-download the complete archive or contact support.")
        return False
    else:
        print("🎉 VERIFICATION PASSED!")
        print("\nAll required files are present and have content.")
        print("\nNext steps:")
        print("1. Set up .env file: cp .env.example .env")
        print("2. Add OpenAI API key to .env")
        print("3. Install dependencies: pip install -r requirements.txt")
        print("4. Run tests: python test_foundation.py")
        print("5. Start server: uvicorn app.main:app --reload")
        print("6. Open browser: http://localhost:8000")
        return True


if __name__ == "__main__":
    success = verify_files()
    sys.exit(0 if success else 1)
