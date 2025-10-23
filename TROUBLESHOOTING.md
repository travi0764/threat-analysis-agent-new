# 🚨 Installation Troubleshooting Guide

## Problem: Missing Files After Extraction

### Step 1: Verify Archive Downloaded Completely

Check file sizes:
- `threat_agent_COMPLETE_VERIFIED.tar.gz` should be **~61 KB**
- `threat_agent_COMPLETE_VERIFIED.zip` should be **~85 KB**

If smaller, re-download the file.

---

### Step 2: Extract to New Directory

```bash
# Create a fresh directory
mkdir threat_agent_project
cd threat_agent_project

# Extract archive
tar -xzf ../threat_agent_COMPLETE_VERIFIED.tar.gz
# OR
unzip ../threat_agent_COMPLETE_VERIFIED.zip

# Navigate into the folder
cd threat_agent_verified
```

---

### Step 3: Run Verification Script

```bash
python verify_installation.py
```

**Expected output:**
```
🔍 Verifying Threat Analysis Agent Installation
============================================================
✅ OK: README.md (165 lines)
✅ OK: QUICKSTART.md (267 lines)
...
🎉 VERIFICATION PASSED!
```

---

## Problem: Empty __init__.py Files

**This is NORMAL!**

Python packages use empty `__init__.py` files. These should exist but be empty:
- `app/__init__.py`
- `app/api/__init__.py`
- `app/core/__init__.py`
- `app/storage/__init__.py`
- `app/ingestion/__init__.py`
- `app/enrichment/__init__.py`
- `app/classification/__init__.py`
- `app/langchain_graph/__init__.py`
- `app/utils/__init__.py`

---

## Problem: "No module named 'app'"

**Solution:**

```bash
# Make sure you're in the right directory
pwd
# Should show: .../threat_agent_verified

# Check Python can find modules
python -c "import sys; print(sys.path)"

# Run from project root
uvicorn app.main:app --reload
```

---

## Problem: "OPENAI_API_KEY not set"

**Solution:**

```bash
# Create .env file
cp .env.example .env

# Edit .env and add your key
echo "OPENAI_API_KEY=sk-your-actual-key-here" >> .env

# Or edit manually
nano .env
```

---

## Problem: Import Errors

**Solution:**

```bash
# Reinstall dependencies
pip install -r requirements.txt

# Or install individually
pip install fastapi uvicorn sqlalchemy pydantic pyyaml validators
pip install tldextract python-multipart httpx requests aiohttp
pip install langchain langchain-openai langgraph
```

---

## Problem: Database Errors

**Solution:**

```bash
# Initialize database
python test_foundation.py

# This creates: threat_intelligence.db
# Check it exists:
ls -lh threat_intelligence.db
```

---

## Problem: UI Not Loading

**Solution:**

1. Check server is running:
```bash
uvicorn app.main:app --reload
```

2. Check UI files exist:
```bash
ls -l ui/
# Should show: index.html, styles.css, app.js
```

3. Access correct URL:
```
http://localhost:8000
# NOT http://localhost:8000/ui/
```

---

## Problem: Port Already in Use

**Solution:**

```bash
# Use different port
uvicorn app.main:app --reload --port 8001

# Then access:
http://localhost:8001
```

---

## Quick Checklist

Run these commands to verify everything:

```bash
# 1. Check you're in project directory
ls README.md QUICKSTART.md
# Should not error

# 2. Check Python version
python --version
# Should be 3.9 or higher

# 3. Check dependencies installed
pip list | grep fastapi
pip list | grep langchain

# 4. Verify files
python verify_installation.py
# Should show: VERIFICATION PASSED

# 5. Test foundation
python test_foundation.py
# Should show: ALL TESTS PASSED

# 6. Start server
uvicorn app.main:app --reload
# Should start without errors
```

---

## Still Having Issues?

### Get Detailed File List

```bash
# List all Python files
find app -name "*.py" -type f | sort

# Count files
find app -name "*.py" -type f | wc -l
# Should output: 30

# Check specific file
cat app/main.py | head -20
```

### Manual File Verification

Check these critical files exist and have content:

```bash
wc -l app/main.py              # Should be ~141 lines
wc -l app/api/ingest.py        # Should be ~243 lines
wc -l app/storage/models.py    # Should be ~167 lines
wc -l ui/index.html            # Should be ~170 lines
wc -l ui/app.js                # Should be ~339 lines
```

---

## Need Help?

1. **Check FILE_LIST.md** for complete file inventory
2. **Read QUICKSTART.md** for step-by-step setup
3. **Run verify_installation.py** to check all files
4. **Check logs** in the logs/ directory (if it exists)

---

## Fresh Start

If all else fails, start completely fresh:

```bash
# Remove old installation
rm -rf threat_agent_verified

# Re-extract
tar -xzf threat_agent_COMPLETE_VERIFIED.tar.gz
cd threat_agent_verified

# Verify
python verify_installation.py

# Setup from scratch
cp .env.example .env
# Add your OpenAI API key to .env

pip install -r requirements.txt
python test_foundation.py
uvicorn app.main:app --reload
```

---

## Success Indicators

You'll know it's working when:

✅ `python verify_installation.py` shows PASSED
✅ `python test_foundation.py` shows ALL TESTS PASSED  
✅ `uvicorn app.main:app --reload` starts without errors
✅ Browser at `http://localhost:8000` shows dashboard
✅ You can upload a CSV file successfully

---

**Good luck! 🚀**
