# QSO Form Field Retention Fix - Email & Other Fields

## Problem
When logging multiple QSOs, certain form fields (particularly **email**) were retaining values from the previous contact:

1. User logs QSO #1 with Callsign A (email populated from QRZ profile)
2. User enters Callsign B and logs QSO #2
3. If Callsign B's QRZ profile doesn't have an email, the form **retains email from QSO #1**
4. QSO #2 gets logged with Callsign B but with email from Callsign A ❌

## Root Cause
In the `loadQRZProfile()` function (frontend/app.js), fields were only being updated IF they existed in the QRZ profile:

```javascript
// OLD CODE - Only sets field IF qrzProfile has the value
if (this.qrzProfile.email) {
    this.loggingForm.email = this.qrzProfile.email;
}
// If qrzProfile doesn't have email, the old value remains in loggingForm
```

This meant that if a new callsign's QRZ profile lacked a field (name, email, gridsquare, etc.), the previous contact's value was retained.

## Solution
Added explicit field clearing at the start of `loadQRZProfile()` before populating with new data:

```javascript
// ✅ NEW CODE - Clear all optional fields first
this.loggingForm.name = '';
this.loggingForm.email = '';  // ✅ CRITICAL FIX
this.loggingForm.qth = '';
this.loggingForm.country = '';
this.loggingForm.state = '';
// ... etc for all fields that might not be in QRZ profile

// NOW populate from QRZ profile (only sets if value exists)
if (this.qrzProfile.email) {
    this.loggingForm.email = this.qrzProfile.email;
}
```

## Files Modified
- **c:\Projects\om0rx-radio-control\frontend\app.js**
  - `loadQRZProfile()` function (lines 2397-2406)
  - Added clearing of: name, qth, gridsquare, country, state, continent, cq_zone, itu_zone, **email**

## Affected Fields
The following fields are now explicitly cleared when a new callsign is looked up:
- ✅ name
- ✅ **email** (primary fix)
- ✅ qth (QTH/location)
- ✅ gridsquare
- ✅ country
- ✅ state
- ✅ continent
- ✅ cq_zone
- ✅ itu_zone

## How It Works Now
1. User enters/selects Callsign A → QRZ lookup → email populated (if available)
2. User logs QSO with A
3. Form is cleared (email = '')
4. User enters Callsign B → QRZ lookup starts:
   - **Email field is explicitly cleared to ''**
   - QRZ profile loaded for B
   - If B has email: field gets B's email ✅
   - If B doesn't have email: field remains '' ✅ (not A's email!)

## Testing
To verify the fix:
1. **Scenario 1**: Log QSO with Callsign that HAS email in QRZ
2. **Scenario 2**: Log another QSO with Callsign that DOESN'T have email
3. Verify that QSO #2 shows empty email field (not retained from QSO #1)

## Additional Notes
- The `clearLoggingForm()` function was already correct (called on Clear button and 2s after successful submission)
- The form submission clears the form after 2 seconds with `setTimeout(() => this.clearLoggingForm(), 2000)`
- This fix prevents field pollution at the QRZ profile load stage, which is the critical moment when new callsign data is being populated

## Status
✅ **FIXED** - Email and other optional fields will no longer retain values from previous QSOs