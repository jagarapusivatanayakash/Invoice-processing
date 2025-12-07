# 🎨 Invoice Processing UI

Simple, functional web interface for invoice processing with HITL.

## 📋 Features

### Page 1: Process Invoice
- Upload invoice image
- Enter invoice details (ID, vendor, amount)
- Submit for processing
- **Real-time status updates** (polls every 2 seconds)
- Shows current processing stage
- Alerts when invoice needs review

### Page 2: Pending Reviews
- Lists all invoices waiting for human review
- Shows invoice details and match score
- **Accept** or **Reject** buttons
- Auto-refreshes every 10 seconds
- Re-invokes agent when decision made

## 🚀 Quick Start

### 1. Start the API
```bash
cd /path/to/invoice-langgraph
python agent_api.py
```

### 2. Open Browser
```
http://localhost:8000
```

That's it! The UI will be served automatically.

## 📖 How to Use

### Processing an Invoice

1. **Upload Image** (optional)
   - Click "Choose File"
   - Select invoice image (.png, .jpg, .pdf)

2. **Enter Details**
   - Invoice ID: `INV-2024-12-001`
   - Vendor Name: `TechCorp Solutions Ltd`
   - Amount: `46500.00`
   - Currency: `USD`

3. **Submit**
   - Click "🚀 Process Invoice"
   - Watch status update in real-time

4. **Status Updates**
   - **Processing** (yellow): Agent is working
   - **Paused** (red): Needs human review
   - **Completed** (green): Done!

### Reviewing Pending Invoices

1. **Switch to Pending Tab**
   - Click "⏳ Pending Reviews"

2. **Review Invoice**
   - See invoice details
   - Check match score
   - Read reason for hold

3. **Make Decision**
   - Click "✅ Accept" to approve
   - Click "❌ Reject" to decline
   - Agent automatically resumes!

4. **Auto-Refresh**
   - List refreshes every 10 seconds
   - Click "🔄 Refresh" for manual update

## 🎯 Status Flow

```
User Submits → Processing (yellow, spinning)
                    ↓
            Match Score Check
                    ↓
        ┌───────────┴───────────┐
        ↓                       ↓
   Match Failed           Match Success
        ↓                       ↓
Paused (red alert)      Processing Continues
        ↓                       ↓
  Pending Reviews Tab     Completed (green)
        ↓
  User Accepts/Rejects
        ↓
  Agent Resumes
        ↓
  Completed (green)
```

## 🔧 Technical Details

### API Endpoints Used

```javascript
// Process Invoice
POST /api/agent/invoke
FormData: { image, invoice_data }

// Check Status (polling every 2s)
GET /api/agent/status/{thread_id}

// List Pending (auto-refresh 10s)
GET /api/reviews/pending

// Submit Decision
POST /api/agent/decision
{ thread_id, decision, reviewer_id }
```

### Real-time Updates

- **Status Polling**: Every 2 seconds while processing
- **Pending List**: Auto-refresh every 10 seconds
- **Instant Feedback**: Decision submission updates immediately

### Browser Compatibility

- ✅ Chrome, Edge, Firefox, Safari
- ✅ Desktop and mobile
- ✅ No JavaScript framework needed
- ✅ Pure HTML/CSS/Vanilla JS

## 🎨 UI Components

### Processing Page
- Upload section (drag & drop ready)
- Form inputs (validated)
- Submit button (disabled when processing)
- Status box (color-coded)
- Progress indicators

### Pending Page
- Card-based layout
- Badge indicators
- Action buttons
- Empty state handling
- Error handling

## 💡 Features

✅ **Real-time Status**: Polls API every 2 seconds  
✅ **Auto-refresh**: Pending list updates every 10 seconds  
✅ **Responsive**: Works on all screen sizes  
✅ **User-friendly**: Clear status messages  
✅ **Error Handling**: Graceful error messages  
✅ **Confirmation**: Asks before accept/reject  

## 🔐 Security Notes

- Currently allows any reviewer_id
- No authentication implemented
- For production, add proper auth

## 📝 Customization

### Change API URL
```javascript
// In index.html, line ~400
const API_BASE = 'http://localhost:8000';
// Change to your API URL
```

### Adjust Polling Intervals
```javascript
// Status polling (line ~500)
setInterval(() => checkStatus(threadId), 2000); // 2 seconds

// Pending refresh (line ~750)
setInterval(() => loadPendingReviews(), 10000); // 10 seconds
```

### Modify Styles
All CSS is in `<style>` tag at the top of `index.html`

## 🐛 Troubleshooting

**UI doesn't load:**
- Make sure API is running: `python agent_api.py`
- Check browser console for errors
- Verify `ui/index.html` exists

**Status not updating:**
- Check browser console for CORS errors
- Verify API is accessible
- Check network tab in DevTools

**Pending reviews not showing:**
- Verify invoice failed matching (score < 90%)
- Check API endpoint: `GET /api/reviews/pending`
- Look for errors in browser console

## 📦 Files

```
ui/
└── index.html    # Complete single-file UI (400+ lines)
```

That's it! Single HTML file, zero dependencies.
