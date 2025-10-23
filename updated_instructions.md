# 🔄 UPDATE INSTRUCTIONS

## Issues Fixed & Features Added

### ✅ Issue 1: Risk Level Parsing Fixed
**Problem:** "medium risk" was showing as "unknown"  
**Fix:** Updated `classifier.py` to handle "medium risk", "MEDIUM", etc. formats

### ✅ Issue 2: Feedback System Added
**Features:**
- 👍👎 Thumbs up/down buttons on each classification
- Full metrics page with:
  - Precision, Recall, F1 Score, Accuracy
  - Confusion Matrix visualization
  - True/False Positives/Negatives
- New API endpoints for feedback submission

### ✅ Issue 3: MalShare Integration Added
**Features:**
- Real hash lookup using MalShare API
- Detects malware from MalShare database
- Auto-registers when API key is configured

---

## 📥 Files to Update

### Backend Files (in `app/` directory)

1. **app/classification/classifier.py**
   - Fixed risk level parsing
   - Location: `app/classification/classifier.py`

2. **app/storage/repository.py**
   - Added `FeedbackRepository` class
   - Added metrics calculation methods
   - Location: `app/storage/repository.py`

3. **app/api/feedback.py** (NEW FILE)
   - Feedback submission endpoint
   - Metrics API endpoints
   - Location: `app/api/feedback.py`

4. **app/enrichment/malshare_enricher.py** (NEW FILE)
   - MalShare hash lookup enricher
   - Location: `app/enrichment/malshare_enricher.py`

5. **app/main.py**
   - Registered feedback router
   - Registered MalShare enricher
   - Location: `app/main.py`

6. **app/config.py**
   - Added malshare_api_key field
   - Location: `app/config.py`

### Frontend Files (in `ui/` directory)

7. **ui/index.html**
   - Added "Metrics" button in header
   - Location: `ui/index.html`

8. **ui/app.js**
   - Added feedback buttons to detail modal
   - Added submitFeedback() function
   - Location: `ui/app.js`

9. **ui/metrics.html** (NEW FILE)
   - Complete metrics dashboard page
   - Confusion matrix visualization
   - Location: `ui/metrics.html`

### Configuration Files

10. **.env.example**
    - Added MALSHARE_API_KEY
    - Location: `.env.example`

---

## 🚀 How to Apply Updates

### Option 1: Replace Individual Files (Recommended)

```bash
# Backup your current files (optional but recommended)
cp app/classification/classifier.py app/classification/classifier.py.backup
cp app/storage/repository.py app/storage/repository.py.backup
cp app/main.py app/main.py.backup
cp app/config.py app/config.py.backup
cp ui/app.js ui/app.js.backup
cp ui/index.html ui/index.html.backup

# Copy updated files
cp /path/to/updated_files/classifier.py app/classification/
cp /path/to/updated_files/repository.py app/storage/
cp /path/to/updated_files/feedback.py app/api/
cp /path/to/updated_files/malshare_enricher.py app/enrichment/
cp /path/to/updated_files/main.py app/
cp /path/to/updated_files/config.py app/
cp /path/to/updated_files/index.html ui/
cp /path/to/updated_files/app.js ui/
cp /path/to/updated_files/metrics.html ui/
cp /path/to/updated_files/.env.example .
```

### Option 2: Manual Edits

See individual sections below for specific changes.

---

## 🔑 Configuration

### Add MalShare API Key (Optional)

1. Edit your `.env` file:
   ```bash
   nano .env
   ```

2. Add your MalShare API key:
   ```
   MALSHARE_API_KEY=your_actual_api_key_here
   ```

3. Save and restart the server

---

## 🧪 Testing

### Test Risk Level Fix

1. Upload CSV with indicators
2. Check classifications show "high", "medium", or "low" (not "unknown")

### Test Feedback System

1. Open http://localhost:8000
2. Upload sample indicators
3. Click "View" on any classified indicator
4. Click 👍 or 👎 buttons
5. Visit http://localhost:8000/metrics.html
6. Verify metrics are displayed

### Test MalShare Integration

1. Add MALSHARE_API_KEY to .env
2. Restart server
3. Upload a CSV with file hashes
4. Check enrichments include "malshare" provider
5. View indicator details to see MalShare data

---

## 📊 New API Endpoints

### Feedback Endpoints

```bash
# Submit feedback
POST /api/feedback/submit
Body: {
  "indicator_id": 1,
  "feedback_type": "correct",  # or "incorrect"
  "comment": "optional comment"
}

# Get metrics
GET /api/feedback/metrics

# Get feedback stats
GET /api/feedback/stats

# Get feedback for specific indicator
GET /api/feedback/indicator/{id}
```

### Testing API Endpoints

```bash
# Submit thumbs up
curl -X POST "http://localhost:8000/api/feedback/submit" \
  -H "Content-Type: application/json" \
  -d '{"indicator_id": 1, "feedback_type": "correct"}'

# Get metrics
curl "http://localhost:8000/api/feedback/metrics"

# Get stats
curl "http://localhost:8000/api/feedback/stats"
```

---

## 🎯 Metrics Explained

### Confusion Matrix

```
                 Predicted Positive | Predicted Negative
Actual Positive  True Positive (TP) | False Negative (FN)
Actual Negative  False Positive (FP)| True Negative (TN)
```

**Definitions:**
- **Positive** = High or Medium risk
- **Negative** = Low risk

### Metrics Formulas

- **Precision** = TP / (TP + FP) - "How many predicted threats were actual threats?"
- **Recall** = TP / (TP + FN) - "How many actual threats did we catch?"
- **F1 Score** = 2 × (Precision × Recall) / (Precision + Recall) - "Balanced measure"
- **Accuracy** = (TP + TN) / Total - "Overall correctness"

---

## 🔍 Verification Checklist

After applying updates, verify:

- [ ] Server starts without errors
- [ ] Dashboard loads at http://localhost:8000
- [ ] Metrics page loads at http://localhost:8000/metrics.html
- [ ] Metrics link in header works
- [ ] Can upload CSV successfully
- [ ] Classifications show correct risk levels (not "unknown")
- [ ] Can click "View" on indicators
- [ ] Thumbs up/down buttons appear on classified indicators
- [ ] Can submit feedback
- [ ] Metrics page shows data after feedback submission
- [ ] MalShare enricher registered (check startup logs if API key configured)

---

## 🐛 Troubleshooting

### Error: "No module named 'app.api.feedback'"

**Solution:** Make sure `feedback.py` is in `app/api/` directory

### Error: "FeedbackRepository not found"

**Solution:** Make sure `repository.py` is updated with FeedbackRepository class

### Metrics page shows all zeros

**Solution:** This is normal if no feedback has been submitted yet. Submit some feedback first.

### MalShare not working

**Solution:**
1. Check MALSHARE_API_KEY is in .env
2. Check startup logs for "MalShare enricher registered"
3. Verify API key is valid

### Risk levels still showing "unknown"

**Solution:**
1. Make sure `classifier.py` is updated
2. Restart the server
3. Re-classify indicators or upload new ones

---

## 📝 Database Changes

The feedback system uses the existing `feedbacks` table (already in schema).  
No database migration needed - just restart the server.

---

## 🎉 What's New Summary

1. **Fixed:** Risk level parsing now handles all formats
2. **Added:** Complete feedback system with metrics
3. **Added:** MalShare integration for real hash lookups
4. **Added:** Metrics dashboard with confusion matrix
5. **Added:** Thumbs up/down buttons in UI
6. **Added:** 4 new API endpoints for feedback
7. **Added:** Performance metrics (precision, recall, F1, accuracy)

---

## 📞 Need Help?

If you encounter issues:

1. Check the logs:
   ```bash
   # Look for errors in startup logs
   uvicorn app.main:app --reload
   ```

2. Verify all files were copied correctly
3. Make sure .env has required API keys
4. Check browser console for JavaScript errors (F12)

---

**🎊 Enjoy your enhanced Threat Analysis Agent!** 🎊