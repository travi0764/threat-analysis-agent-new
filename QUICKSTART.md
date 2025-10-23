# 🚀 QUICKSTART GUIDE - Threat Analysis Agent

## Prerequisites

- Python 3.9+ 
- pip (Python package manager)
- OpenAI API key (required for Phase 4 - AI classification)

## Installation Steps

### 1. Extract the Project

```bash
# For .tar.gz
tar -xzf threat_agent_phase5_final.tar.gz
cd threat_agent

# For .zip
unzip threat_agent_phase5_final.zip
cd threat_agent
```

### 2. Set Up Environment

```bash
# Create .env file from example
cp .env.example .env

# Edit .env and add your OpenAI API key
# OPENAI_API_KEY=sk-your-actual-key-here
nano .env  # or use any text editor
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Expected packages:**
- fastapi
- uvicorn
- sqlalchemy
- pydantic
- pyyaml
- validators
- tldextract
- python-multipart
- httpx
- requests
- aiohttp
- aiofiles
- langchain
- langchain-openai
- langgraph

### 4. Initialize Database

```bash
# Run foundation test to create database
python test_foundation.py
```

**Expected output:**
```
🧪 FOUNDATION TEST
============================================================
✓ Config loaded successfully
✓ Database initialized
✓ Logging configured
✓ All models created
🎉 ALL TESTS PASSED!
```

## Running the Application

### Start the Server

```bash
uvicorn app.main:app --reload
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

### Access the Dashboard

Open your browser and go to:
```
http://localhost:8000
```

You should see the **Threat Analysis Agent Dashboard**!

## Quick Test

### Option 1: Use the Web Interface

1. Open `http://localhost:8000` in your browser
2. Drag and drop `sample_indicators.csv` to the upload area
3. Make sure "Auto-enrich" and "Auto-classify" are checked
4. Wait for processing (30-60 seconds)
5. View results in the table below

### Option 2: Use the API

```bash
# Upload CSV file
curl -X POST "http://localhost:8000/api/ingest/upload-csv?enrich=true&classify=true" \
  -F "file=@sample_indicators.csv"

# View indicators
curl "http://localhost:8000/api/indicators?limit=10"

# Get statistics
curl "http://localhost:8000/api/classify/stats"
```

### Option 3: Run Test Scripts

```bash
# Test Phase 2 (Ingestion)
python test_phase2.py

# Test Phase 3 (Enrichment)
python test_phase3.py

# Test Phase 4 (Classification) - Requires OpenAI API key
python test_phase4.py
```

## Verify Installation

### Check All Files Exist

Run this command to verify all critical files:

```bash
ls -R app/ | grep -E "\.(py|yaml|csv|html|css|js)$"
```

**You should see:**

```
app/__init__.py
app/config.py
app/logging_config.py
app/main.py

app/api:
__init__.py
classify.py
ingest.py
query.py

app/classification:
__init__.py
classifier.py

app/core:
__init__.py

app/enrichment:
__init__.py
base.py
mock_enrichers.py
orchestrator.py

app/ingestion:
__init__.py
csv_ingestor.py
ingestor.py

app/langchain_graph:
__init__.py
graph_builder.py

app/storage:
__init__.py
db.py
models.py
repository.py

app/utils:
__init__.py
exceptions.py
helpers.py

ui:
index.html
styles.css
app.js
```

## Troubleshooting

### Issue: "OPENAI_API_KEY not set"

**Solution:**
```bash
echo "OPENAI_API_KEY=sk-your-key-here" > .env
```

### Issue: "No module named 'fastapi'"

**Solution:**
```bash
pip install -r requirements.txt
```

### Issue: "Database file not found"

**Solution:**
```bash
python test_foundation.py
```

### Issue: "Port 8000 already in use"

**Solution:**
```bash
# Use a different port
uvicorn app.main:app --reload --port 8001
```

### Issue: Empty __init__.py files

**Don't worry!** Empty `__init__.py` files are normal. They just mark directories as Python packages.

### Issue: UI not loading

**Solution:**
1. Make sure server is running: `uvicorn app.main:app --reload`
2. Check that ui/ folder has: `index.html`, `styles.css`, `app.js`
3. Access via: `http://localhost:8000` (not `http://localhost:8000/ui/`)

## Testing Each Phase

### Phase 1: Foundation
```bash
python test_foundation.py
```
**Tests:** Config, Database, Logging

### Phase 2: Ingestion
```bash
python test_phase2.py
```
**Tests:** CSV parsing, Type detection, Database storage

### Phase 3: Enrichment
```bash
python test_phase3.py
```
**Tests:** Mock enrichers, Async orchestration, Risk scoring

### Phase 4: Classification (Requires OpenAI API Key)
```bash
python test_phase4.py
```
**Tests:** LangGraph agent, AI classification, Full pipeline

## Sample CSV Format

Create a file called `test.csv`:

```csv
value,indicator_type,source,tags,notes
evil-domain.com,domain,manual,phishing,Test domain
192.0.2.1,ip,feed,scanning,Test IP
5d41402abc4b2a76b9719d911017c592,hash,manual,malware,Test hash
http://malicious-site.com,url,feed,phishing,Test URL
```

Or simplified (auto-detect):

```csv
value,source,tags,notes
evil-domain.com,manual,phishing,Test domain
192.0.2.1,feed,scanning,Test IP
```

## API Documentation

Once the server is running, access:
```
http://localhost:8000/docs
```

This provides **interactive Swagger documentation** for all API endpoints.

## Project Structure

```
threat_agent/
├── app/
│   ├── api/              # API endpoints
│   ├── classification/   # AI classification
│   ├── core/            # Core utilities
│   ├── enrichment/      # Enrichment logic
│   ├── ingestion/       # CSV ingestion
│   ├── langchain_graph/ # LangGraph agent
│   ├── storage/         # Database models
│   └── utils/           # Helper functions
├── ui/                  # Web dashboard
├── config.yaml          # Configuration
├── .env.example         # Environment template
├── requirements.txt     # Python dependencies
├── sample_indicators.csv # Sample data
└── test_*.py           # Test scripts
```

## Next Steps

1. ✅ Start server: `uvicorn app.main:app --reload`
2. ✅ Open browser: `http://localhost:8000`
3. ✅ Upload `sample_indicators.csv`
4. ✅ Watch the magic happen!
5. ✅ Explore the API docs: `http://localhost:8000/docs`

## Need Help?

Check the documentation:
- `README.md` - Project overview
- `PHASE2_SUMMARY.md` - Ingestion details
- `PHASE3_SUMMARY.md` - Enrichment details
- `PHASE4_SUMMARY.md` - Classification details

## Common Commands

```bash
# Start server
uvicorn app.main:app --reload

# Start with custom port
uvicorn app.main:app --reload --port 8001

# Run tests
python test_phase2.py
python test_phase3.py
python test_phase4.py  # Requires OpenAI API key

# Check dependencies
pip list | grep -E "fastapi|langchain|openai"

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

---

**🎉 You're ready to go! Happy threat hunting!** 🔍
