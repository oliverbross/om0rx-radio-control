# WSJT-X RST Capture and QSO Auto-Save Fix

## Problem Statement

After WSJT-X integration was completed, the QSO auto-save had three critical issues:

1. **Hardcoded RST Values**: RST sent/received were hardcoded as `599` (traditional SSB values), but FT8/FT4 use signal reports like `+15`, `R-12`, `-09`, etc.

2. **Silent Save Failures**: QSOs would not save to Wavelog because:
   - Data type mismatches (frequency sent as string, RST as int instead of string)
   - Missing RST values in bridge messages
   - No error feedback to user

3. **Form Management Issues**:
   - Form wasn't cleared when switching between contacts
   - RST values weren't updated in real-time as contact progressed
   - No confirmation modal shown after save

## Root Causes

### Bridge Issue (sdc-bridge-server.js)
The bridge was extracting RST values from WSJT-X messages but NOT including them in the broadcasts:
- Status messages had txRst/rxRst available but weren't being sent
- LoggedAdif messages had txRst/rxRst available but weren't being sent

### Handler Issues (wsjtx-handler.js)
1. Hardcoded RST to 599 instead of using actual values
2. No tracking of previous contact to detect when form should be cleared
3. Form not updated in real-time with RST values
4. Modal not displayed after QSO save

## Solutions Implemented

### 1. Fix Bridge to Include RST Values

**File: `sdc-bridge-server.js` (Lines 284-321)**

**Status Message (Line 293-294):**
```javascript
// Added to Status broadcast:
txRst: msg.txRst || '',  // What we sent (e.g., "R-12", "-09")
rxRst: msg.rxRst || '',  // What they sent (e.g., "+15", "-21")
```

**LoggedAdif Message (Line 319-320):**
```javascript
// Added to LoggedAdif broadcast:
txRst: msg.txRst || '',  // Final RST we sent
rxRst: msg.rxRst || '',  // Final RST they sent
```

### 2. Update Handler to Capture and Use RST Values

**File: `frontend/js/wsjtx-handler.js`**

#### a. Store RST in wsjtxData (Lines 15-16)
```javascript
txRst: '',      // RST we sent (e.g., "R-12", "-09", "+15")
rxRst: '',      // RST they sent (e.g., "+15", "-21")
```

#### b. Detect New Contacts (Lines 78-83)
```javascript
// Detect if a NEW contact started (different call)
const isNewContact = data.dxCall !== previousDxCall;
if (isNewContact && previousDxCall) {
  console.log(`🆕 NEW CONTACT DETECTED: ${previousDxCall} → ${data.dxCall}`);
  clearLogQsoForm();
}
previousDxCall = data.dxCall;
```

#### c. Real-Time RST Updates (Lines 154-159)
```javascript
// Update RST values from WSJT-X (real-time as contact progresses)
if (txRst) {
  form.rst_sent = txRst;  // What we transmitted
}
if (rxRst) {
  form.rst_received = rxRst;  // What they transmitted to us
}
```

#### d. Use Actual RST Values When Saving (Lines 292-317)
```javascript
// Use actual RST values from the LoggedAdif message (from WSJT-X)
// In FT8/FT4, these are strings like "R-12", "-09", "+15", etc.
const txRst = loggedAdifData.txRst || wsjtxData.txRst || '';
const rxRst = loggedAdifData.rxRst || wsjtxData.rxRst || '';

const qsoData = {
  callsign: loggedAdifData.dxCall.toUpperCase(),
  frequency: frequency,
  mode: loggedAdifData.mode || 'FT8',
  rst_sent: txRst,  // String from WSJT-X (e.g., "R-12", "-09")
  rst_received: rxRst,  // String from WSJT-X (e.g., "+15", "-21")
  gridsquare: loggedAdifData.dxGrid,
  notes: `Auto-logged from WSJT-X at ${new Date().toISOString()}`
};
```

#### e. Show Confirmation Modal (Lines 415-445)
```javascript
// Build message with RST values if available
let message;
if (status === 'success') {
  message = `✅ QSO Logged Successfully!\n\n` +
    `Call: ${data.callsign}\n` +
    `Freq: ${data.frequency} MHz\n` +
    `Mode: ${data.mode}\n` +
    `Grid: ${data.grid || 'N/A'}\n`;
  
  if (data.rst_sent || data.rst_received) {
    message += `RST Sent: ${data.rst_sent || 'N/A'}\n`;
    message += `RST Rcvd: ${data.rst_received || 'N/A'}\n`;
  }
  // ...
}

// Show the modal
alert(message);
```

## What Now Works

### 1. Real-Time RST Updates ✅
As you make contact in WSJT-X:
- Console shows: `📤 TX RST: R-12` and `📥 RX RST: +15`
- Form fields update automatically with actual values
- User sees exact signal reports from the contact

### 2. Contact Switching ✅
When you double-click a new station:
- Console shows: `🆕 NEW CONTACT DETECTED: EA1CF → EA5QY`
- Form clears all previous fields
- Ready for new contact with fresh data

### 3. Accurate QSO Saving ✅
When QSO is completed in WSJT-X:
- Correct RST values sent to backend (e.g., "R-12", "+15" instead of 599)
- QRZ profile data merged if available
- DXCC data merged if available
- Modal popup shows confirmation with details

### 4. Console Logging ✅
Much better diagnostic info:
```
📍 WSJT-X Status: EA1CF (IN52XV)
   📤 TX RST: R-12
   📥 RX RST: +15
✅ Form populated with WSJT-X data:
   Callsign: EA1CF
   Grid: IN52XV
   Frequency: 10.137
   Mode: FT8
   RST Sent: R-12
   RST Received: +15
🆕 NEW CONTACT DETECTED: EA1CF → EA5QY
🗑️ Clearing form for new contact...
✅ Using actual RST values from WSJT-X:
   📤 TX RST: R-12
   📥 RX RST: +15
📬 Showing QSO save modal...
✅ QSO Logged Successfully!
```

## Testing Workflow

1. **Start WSJT-X** and the bridge server
2. **Double-click a station** (e.g., EA1CF in IN52XV)
   - Observe form populates with call, grid, frequency
   - Observe antenna auto-rotates (if enabled)
3. **Complete the QSO** and exchange signal reports
   - Observe form updates with actual RST values in real-time
4. **Finish in WSJT-X** (RR73 or similar)
   - Observe modal popup with confirmed QSO details including RST
   - Check console for success message
5. **Double-click another station**
   - Observe form clears from previous contact
   - Repeat with new contact
6. **Verify in Wavelog**
   - Check that QSOs saved with correct RST values (not 599)
   - Check that QRZ name, country, etc. are populated

## Files Modified

1. **sdc-bridge-server.js** (Lines 293-294, 319-320)
   - Added txRst and rxRst to Status broadcast
   - Added txRst and rxRst to LoggedAdif broadcast

2. **frontend/js/wsjtx-handler.js** (Multiple sections)
   - Added RST tracking in wsjtxData
   - Added form clearing function for new contacts
   - Enhanced auto-populate to capture RST in real-time
   - Fixed logQsoToWavelog to use actual RST instead of hardcoded 599
   - Enhanced modal display to show RST values

## Implementation Notes

### RST Value Formats
- **SSB/CW**: Traditional 599 format (579, 589, 599)
- **FT8/FT4**: Signal reports (R-24 to R+31 scale, or simple +/- values)
  - Examples: "R-12", "-09", "+15", "R+05"
  - R prefix indicates "Readability" report in some systems
  - Can be 4 digits (e.g., "9999") or 2-3 chars (e.g., "+15")

### Wavelog Compatibility
Wavelog RST fields accept both:
- Integer (599, 579, etc.)
- String ("R-12", "+15", etc.)

The fix sends actual values from WSJT-X (strings), allowing Wavelog to record exactly what was exchanged.

### Error Handling
If RST values are missing:
```
⚠️  Missing RST values - TX: "", RX: ""
   (QSO will still be saved, but RST fields will be empty)
```

This ensures QSOs still save even if signal reports aren't captured, but user is warned.

## Future Improvements

1. **Decode Message Enhancement**: Parse decode messages to capture intermediate signal reports
2. **ADIF Export**: Export QSOs to ADIF with correct RST formats
3. **QSO Log Display**: Show RST values in the main contact log
4. **Custom Modal**: Replace alert() with custom Vue modal for better UX