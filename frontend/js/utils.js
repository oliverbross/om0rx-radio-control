// Utility Functions Module
// FlexRadio Web Control v2.0 - Utility Functions & Formatters

console.log('✅ Loading utils.js module...');

const utilityMethods = {
    // === Frequency Formatting ===
    
    formatFrequency(freq) {
        if (!freq) return '----.------';
        
        // Always format as MHz with full 6-digit precision: 014.074.000
        const mhz = freq.toFixed(6);
        const parts = mhz.split('.');
        const intPart = parts[0].padStart(3, '0');
        const decPart = parts[1] || '000000';
        
        return `${intPart}.${decPart.substring(0, 3)}.${decPart.substring(3, 6)}`;
    },
    
    formatFrequencyForDisplay(freq) {
        // Format frequency for display with full precision like Flex radio
        // Examples: 28.300.000, 7.100.000, 15.200.000
        if (!freq) return '----.------';
        
        const freqNum = parseFloat(freq);
        if (isNaN(freqNum)) return '----.------';
        
        // Always show 6 decimal places, then format with dots
        const mhz = freqNum.toFixed(6);
        const parts = mhz.split('.');
        const intPart = parts[0].padStart(2, '0'); // At least 2 digits for integer part
        const decPart = parts[1] || '000000';
        
        // Format as XX.XXX.XXX (like Flex radio display)
        return `${intPart}.${decPart.substring(0, 3)}.${decPart.substring(3, 6)}`;
    },
    
    formatFrequencyPrecise(freq) {
        // Format frequency with full precision for internal use
        if (!freq) return 0;
        
        const freqNum = parseFloat(freq);
        if (isNaN(freqNum)) return 0;
        
        // Return with 6 decimal places precision
        return parseFloat(freqNum.toFixed(6));
    },
    
    // === Frequency to Band Conversion ===
    
    freqToBand(freqMHz) {
        if (!freqMHz) return null;
        
        const freq = parseFloat(freqMHz);
        if (isNaN(freq)) return null;
        
        // Convert MHz to band name
        if (freq >= 1.8 && freq <= 2.0) return '160m';
        if (freq >= 3.5 && freq <= 4.0) return '80m';
        if (freq >= 5.3 && freq <= 5.4) return '60m';
        if (freq >= 7.0 && freq <= 7.3) return '40m';
        if (freq >= 10.1 && freq <= 10.15) return '30m';
        if (freq >= 14.0 && freq <= 14.35) return '20m';
        if (freq >= 18.068 && freq <= 18.168) return '17m';
        if (freq >= 21.0 && freq <= 21.45) return '15m';
        if (freq >= 24.89 && freq <= 24.99) return '12m';
        if (freq >= 28.0 && freq <= 29.7) return '10m';
        if (freq >= 50.0 && freq <= 54.0) return '6m';
        if (freq >= 144.0 && freq <= 148.0) return '2m';
        if (freq >= 420.0 && freq <= 450.0) return '70cm';
        
        return null; // Unknown band
    },
    
    formatFrequencyFromKHz(freqKHz) {
        // Convert kHz to MHz and format for display
        if (!freqKHz) return '----.------';
        
        const freqMHz = parseFloat(freqKHz) / 1000;
        return this.formatFrequencyForDisplay(freqMHz);
    },
    
    formatFrequencyCompact(freq) {
        // Compact frequency format for spots list
        if (!freq) return '----';
        
        const freqNum = parseFloat(freq);
        if (isNaN(freqNum)) return '----';
        
        // For frequencies >= 1 MHz, show as MHz with 3 decimals
        if (freqNum >= 1) {
            return freqNum.toFixed(3);
        } else {
            // For frequencies < 1 MHz, show in kHz
            return (freqNum * 1000).toFixed(0) + 'k';
        }
    },
    
    // === Status & UI Helpers ===
    
    showStatus(text, type = 'success') {
        this.statusMessage = { text, type };
        setTimeout(() => {
            this.statusMessage = null;
        }, 3000);
    },
    
    updateClock() {
        const now = new Date();
        this.currentTime = now.toISOString().substr(11, 8);
        
        // Also update the logging form's UTC time if form is visible/open
        if (this.loggingForm && !this.loggingPanelSectionCollapsed) {
            const h = String(now.getUTCHours()).padStart(2, '0');
            const m = String(now.getUTCMinutes()).padStart(2, '0');
            const s = String(now.getUTCSeconds()).padStart(2, '0');
            this.loggingForm.time_off = `${h}:${m}:${s}`;
        }
    },
    
    // === Date & Time Formatting ===
    
    formatQSODate(qsoDate) {
        // Format ADIF date (YYYYMMDD) with optional time to readable format
        if (!qsoDate) return '-';
        
        // Handle format: YYYYMMDD or YYYYMMDD HHMMSS
        const parts = qsoDate.trim().split(' ');
        const dateStr = parts[0];
        const timeStr = parts[1];
        
        if (dateStr.length === 8) {
            const year = dateStr.substring(0, 4);
            const month = dateStr.substring(4, 6);
            const day = dateStr.substring(6, 8);
            
            let result = `${month}/${day}/${year}`;
            
            if (timeStr && timeStr.length === 6) {
                const hour = timeStr.substring(0, 2);
                const min = timeStr.substring(2, 4);
                result += ` ${hour}:${min}`;
            }
            
            return result;
        }
        
        return qsoDate;
    },
    
    formatUTCTime() {
        const now = new Date();
        const h = String(now.getUTCHours()).padStart(2, '0');
        const m = String(now.getUTCMinutes()).padStart(2, '0');
        const s = String(now.getUTCSeconds()).padStart(2, '0');
        return `${h}:${m}:${s}`;
    },
    
    formatUTCDate() {
        const now = new Date();
        return now.toISOString().split('T')[0];
    },
    
    // === Validation Helpers ===
    
    isValidFrequency(freq) {
        const freqNum = parseFloat(freq);
        return !isNaN(freqNum) && freqNum > 0 && freqNum < 1000; // 0-1000 MHz range
    },
    
    isValidCallsign(callsign) {
        if (!callsign || typeof callsign !== 'string') return false;
        // Basic callsign validation - at least 3 chars, contains letters and numbers
        const cleanCall = callsign.trim().toUpperCase();
        return /^[A-Z0-9]{3,}$/.test(cleanCall) && /[A-Z]/.test(cleanCall) && /[0-9]/.test(cleanCall);
    },
    
    // === Number Formatting ===
    
    formatNumber(num, decimals = 0) {
        if (num === null || num === undefined || isNaN(num)) return '-';
        return parseFloat(num).toFixed(decimals);
    },
    
    formatPower(watts) {
        if (!watts || isNaN(watts)) return '0W';
        const w = parseInt(watts);
        if (w >= 1000) {
            return (w / 1000).toFixed(1) + 'kW';
        }
        return w + 'W';
    },
    
    // === String Helpers ===
    
    capitalizeFirst(str) {
        if (!str) return '';
        return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
    },
    
    truncateText(text, maxLength = 50) {
        if (!text || text.length <= maxLength) return text;
        return text.substring(0, maxLength - 3) + '...';
    },
    
    // === Color & Status Helpers ===
    
    getStatusColor(status) {
        const statusColors = {
            'connected': '#10b981',
            'disconnected': '#ef4444',
            'connecting': '#f59e0b',
            'error': '#ef4444',
            'success': '#10b981',
            'warning': '#f59e0b',
            'info': '#3b82f6'
        };
        return statusColors[status?.toLowerCase()] || '#6b7280';
    },
    
    getBandColor(band) {
        const bandColors = {
            '160M': '#ef4444', '80M': '#f97316', '60M': '#f59e0b', '40M': '#eab308',
            '30M': '#84cc16', '20M': '#22c55e', '17M': '#10b981', '15M': '#14b8a6',
            '12M': '#06b6d4', '10M': '#0ea5e9', '6M': '#3b82f6', '2M': '#6366f1'
        };
        return bandColors[band] || '#6b7280';
    },
    
    getModeColor(mode) {
        const modeColors = {
            'USB': '#3b82f6', 'LSB': '#3b82f6', 'CW': '#f59e0b',
            'RTTY': '#ef4444', 'PSK': '#ef4444', 'FT8': '#10b981',
            'FT4': '#10b981', 'AM': '#8b5cf6', 'FM': '#8b5cf6',
            'DIGI': '#06b6d4', 'DIGU': '#06b6d4', 'DIGL': '#06b6d4'
        };
        return modeColors[mode?.toUpperCase()] || '#6b7280';
    },
    
    // === Frequency Conversion Helpers ===
    
    mhzToKhz(mhz) {
        return parseFloat(mhz) * 1000;
    },
    
    khzToMhz(khz) {
        return parseFloat(khz) / 1000;
    },
    
    hzToMhz(hz) {
        return parseFloat(hz) / 1000000;
    },
    
    mhzToHz(mhz) {
        return parseFloat(mhz) * 1000000;
    },
    
    // === Status Color Styling ===
    
    getCallStatusStyle(status) {
        const colors = {
            'New Call': '#FF6B35',        // Orange-Red (exciting new contact!)
            'New Band': '#4A9EFF',        // Bright Blue  
            'New Mode': '#FFD93D',        // Yellow
            'New Band+Mode': '#E91E63',   // Pink (special combo!)
            'Worked': '#B0B0B0',          // Gray
            'Confirmed': '#10B981'        // Green
        };
        const color = colors[status] || '#fff';
        return `font-size: 13px; font-weight: bold; color: ${color};`;
    },
    
    getDxccStatusStyle(status) {
        const colors = {
            'ATNO': '#FF6B35',            // Orange-Red (All Time New One - HUGE!)
            'C/New Band': '#4A9EFF',      // Bright Blue (confirmed country, new band)
            'C/New Mode': '#FFD93D',      // Yellow (confirmed country, new mode)
            'C/New Band+Mode': '#9C27B0', // Purple (confirmed country, new combo)
            'W/New Band': '#00BCD4',      // Cyan (worked country, new band)
            'W/New Mode': '#FFA726',      // Orange (worked country, new mode)
            'W/New Band+Mode': '#FF5722', // Deep Orange (worked country, new combo)
            'Worked': '#B0B0B0',          // Gray
            'Confirmed': '#10B981',       // Green
            'Unknown': '#666666'          // Dark Gray (unresolved DXCC)
        };
        const color = colors[status] || '#fff';
        return `font-size: 13px; font-weight: bold; color: ${color};`;
    },
    
    // === QRZ API Integration ===
    
    async loadQRZProfile() {
        const callsign = this.loggingForm.callsign.trim().toUpperCase();
        if (!callsign) return;
        
        this.qrzLoading = true;
        try {
            const encodedCallsign = encodeURIComponent(callsign);
            const response = await fetch(`/api/qrz/profile/${encodedCallsign}`);
            this.qrzProfile = await response.json();
            
            if (this.qrzProfile.success) {
                // Clear fields that might not be in QRZ profile to avoid retaining previous values
                this.loggingForm.name = '';
                this.loggingForm.qth = '';
                this.loggingForm.gridsquare = '';
                this.loggingForm.country = '';
                this.loggingForm.state = '';
                this.loggingForm.continent = '';
                this.loggingForm.cq_zone = '';
                this.loggingForm.itu_zone = '';
                this.loggingForm.email = '';  // Always clear email to prevent retention from previous QSO
                
                // Station Tab - Auto-populate from QRZ
                if (this.qrzProfile.name) {
                    this.loggingForm.name = this.qrzProfile.name;
                }
                if (this.qrzProfile.state || this.qrzProfile.country) {
                    // Build location string from state and country
                    const locParts = [];
                    if (this.qrzProfile.state) locParts.push(this.qrzProfile.state);
                    if (this.qrzProfile.country) locParts.push(this.qrzProfile.country);
                    if (locParts.length > 0) {
                        this.loggingForm.qth = locParts.join(', ');
                    }
                }
                
                // General Tab - Auto-populate from QRZ
                if (this.qrzProfile.country) {
                    this.loggingForm.country = this.qrzProfile.country;
                }
                if (this.qrzProfile.state) {
                    this.loggingForm.state = this.qrzProfile.state;
                }
                if (this.qrzProfile.cont) {
                    this.loggingForm.continent = this.qrzProfile.cont;
                }
                if (this.qrzProfile.cqzone) {
                    this.loggingForm.cq_zone = this.qrzProfile.cqzone;
                }
                if (this.qrzProfile.ituzone) {
                    this.loggingForm.itu_zone = this.qrzProfile.ituzone;
                }
                if (this.qrzProfile.grid) {
                    this.loggingForm.gridsquare = this.qrzProfile.grid;
                }
                if (this.qrzProfile.email) {
                    this.loggingForm.email = this.qrzProfile.email;
                }
                
                // Load Wavelog data to fill in any missing fields
                await this.loadWavelogProfile();
                
                // Trigger AUTO rotor if enabled
                const gridsquare = this.qrzProfile.grid || null;
                const frequency_khz = this.loggingForm.frequency * 1000;  // Convert MHz to kHz
                this.rotorAutoGoto(callsign, frequency_khz, gridsquare, null, null);
                
                // Also load history
                const histResponse = await fetch(`/api/qrz/history/${encodedCallsign}?limit=8`);
                const histData = await histResponse.json();
                this.qrzHistory = histData.data || [];
            }
        } catch (error) {
            console.error('QRZ profile error:', error);
            this.qrzProfile = { success: false };
        } finally {
            this.qrzLoading = false;
        }
    },
    
    async loadWavelogProfile() {
        // Use Wavelog private_lookup to get additional data
        const callsign = this.loggingForm.callsign.trim().toUpperCase();
        if (!callsign) return;
        
        try {
            const response = await fetch('/api/wavelog/private_lookup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    callsign: callsign,
                    band: this.freqToBand(this.loggingForm.frequency) || '20m',
                    mode: this.loggingForm.mode || 'SSB'
                })
            });
            
            const data = await response.json();
            if (data && typeof data === 'object') {
                // Fill in missing fields from Wavelog
                if (data.gridsquare && !this.loggingForm.gridsquare) {
                    this.loggingForm.gridsquare = data.gridsquare;
                }
                if (data.cont && !this.loggingForm.continent) {
                    this.loggingForm.continent = data.cont;
                }
                if (data.cqz && !this.loggingForm.cq_zone) {
                    this.loggingForm.cq_zone = data.cqz;
                }
                if (data.ituz && !this.loggingForm.itu_zone) {
                    this.loggingForm.itu_zone = data.ituz;
                }
                if (data.state && !this.loggingForm.state) {
                    this.loggingForm.state = data.state;
                }
                if (data.county && !this.loggingForm.us_county) {
                    this.loggingForm.us_county = data.county;
                }
                if (data.name && !this.loggingForm.name) {
                    this.loggingForm.name = data.name;
                }
                if (data.qsl_manager && !this.loggingForm.qsl_manager) {
                    this.loggingForm.qsl_manager = data.qsl_manager;
                }
            }
        } catch (error) {
            console.error('Wavelog lookup error:', error);
            // Silently fail - this is optional enhancement
        }
    },
    
    async loadDXCCStatus() {
        const callsign = this.loggingForm.callsign.trim().toUpperCase();
        if (!callsign) return;
        
        this.dxccLoading = true;
        try {
            // Use private_lookup API with optional band and mode parameters
            const band = this.loggingForm.frequency ? this.freqToBand(this.loggingForm.frequency) : null;
            const mode = this.loggingForm.mode || null;
            
            const response = await fetch('/api/wavelog/private_lookup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    callsign: callsign,
                    band: band || '20m',
                    mode: mode || 'SSB'
                })
            });
            this.dxccStatus = await response.json();
            
            // Parse private_lookup data
            if (this.dxccStatus.success && this.dxccStatus.data) {
                this.dxccBands = this.parseDXCCData(this.dxccStatus.data);
            }
        } catch (error) {
            console.error('DXCC status error:', error);
            this.dxccStatus = { success: false };
        } finally {
            this.dxccLoading = false;
        }
        
        // Load previous QSOs
        this.loadPreviousQSOs();
    },
    
    async loadPreviousQSOs() {
        const callsign = this.loggingForm.callsign.trim().toUpperCase();
        if (!callsign) {
            this.previousQSOs = [];
            return;
        }
        
        this.previousQSOsLoading = true;
        try {
            console.log(`[Previous QSOs] 🔍 Loading for callsign: ${callsign}`);
            
            const response = await fetch('/api/wavelog/recent_qsos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    callsign: callsign,
                    limit: 5
                })
            });
            
            const result = await response.json();
            console.log(`[Previous QSOs] 📡 Full response:`, result);
            
            if (result.success && result.data) {
                // Handle both array and object responses
                const qsos = Array.isArray(result.data) ? result.data : [];
                console.log(`[Previous QSOs] ✅ Received ${qsos.length} QSOs`);
                
                if (qsos.length > 0) {
                    console.log(`[Previous QSOs] 📋 First QSO:`, JSON.stringify(qsos[0], null, 2));
                    console.log(`[Previous QSOs] 📋 All QSOs:`, JSON.stringify(qsos, null, 2));
                } else {
                    console.warn(`[Previous QSOs] ⚠️ Response marked success but no QSOs found`);
                }
                
                this.previousQSOs = qsos.slice(0, 5);  // Ensure max 5 QSOs
                console.log(`[Previous QSOs] ✅ Set previousQSOs array (length: ${this.previousQSOs.length})`);
            } else {
                console.warn(`[Previous QSOs] ❌ No success or data in response for ${callsign}. Result:`, result);
                this.previousQSOs = [];
            }
        } catch (error) {
            console.error('[Previous QSOs] ❌ Error loading:', error);
            console.error('[Previous QSOs] Stack:', error.stack);
            this.previousQSOs = [];
        } finally {
            this.previousQSOsLoading = false;
        }
    },
    
    parseDXCCData(data) {
        // Parse DXCC data from Wavelog private_lookup response
        // This method processes the band/mode confirmation status
        const bands = {};
        
        // Extract band-specific data if available
        if (data.bands) {
            Object.keys(data.bands).forEach(band => {
                const bandData = data.bands[band];
                bands[band] = {
                    worked: bandData.worked || false,
                    confirmed: bandData.confirmed || false,
                    modes: bandData.modes || {}
                };
            });
        }
        
        return bands;
    },
    
    autoPopulateRST() {
        // Auto-populate RST values based on current mode
        const mode = this.loggingForm.mode || this.radioStatus.mode || '';
        
        if (mode.includes('CW')) {
            this.loggingForm.rst_sent = '599';
            this.loggingForm.rst_rcvd = '599';
        } else if (mode.includes('FT8') || mode.includes('FT4') || mode.includes('JS8') || 
                   mode.includes('MSK144') || mode.includes('WSPR') || mode.includes('JT')) {
            // Digital modes typically use signal reports
            this.loggingForm.rst_sent = '+00';
            this.loggingForm.rst_rcvd = '+00';
        } else {
            // SSB and other voice modes
            this.loggingForm.rst_sent = '59';
            this.loggingForm.rst_rcvd = '59';
        }
    },
    
    async autoPopulateForm() {
        // Auto-populate from DX spots when callsign is entered manually
        const callsign = this.loggingForm.callsign.toUpperCase();
        
        // Look for matching spot
        const spot = this.dxSpots.find(s => s.callsign === callsign);
        if (spot) {
            // Found matching spot - use spot data with full precision
            this.loggingForm.frequency = spot.frequency;
            this.loggingForm.mode = spot.mode || '';
            
            // Auto-populate from comments if available (POTA/SOTA/etc)
            if (spot.comment) {
                this.loggingForm.notes = spot.comment;
            }
        } else {
            // No matching spot - use current radio frequency/mode with full precision
            this.loggingForm.mode = this.radioStatus.mode || '';
            this.loggingForm.frequency = this.radioStatus.frequency || 0;
        }
        
        // Auto-populate RST based on mode
        this.autoPopulateRST();
        
        // Load QRZ profile and DXCC status
        await this.loadQRZProfile();
        await this.loadDXCCStatus();
    },
    
    // === Status Styling Methods ===
    
    getCallStatusStyle(status) {
        // Return CSS style object for call status coloring
        if (!status) {
            return { color: '#FFFFFF' };
        }
        
        const colors = {
            'New Call': '#FF6B35',        // Orange-Red (exciting new contact!)
            'New Band': '#4A9EFF',        // Bright Blue  
            'New Mode': '#FFD93D',        // Yellow
            'New Band+Mode': '#E91E63',   // Pink (special combo!)
            'Worked': '#B0B0B0',          // Gray
            'Confirmed': '#10B981'        // Green
        };
        const color = colors[status] || '#FFFFFF';
        return { color: color, fontWeight: 'bold', fontSize: '13px' };
    },
    
    getDxccStatusStyle(status) {
        // Return CSS style object for DXCC status coloring
        if (!status) {
            return { color: '#FFFFFF' };
        }
        
        const colors = {
            'ATNO': '#FF6B35',            // Orange-Red (All Time New One - HUGE!)
            'C/New Band': '#4A9EFF',      // Bright Blue (confirmed country, new band)
            'C/New Mode': '#FFD93D',      // Yellow (confirmed country, new mode)
            'C/New Band+Mode': '#9C27B0', // Purple (confirmed country, new combo)
            'W/New Band': '#00BCD4',      // Cyan (worked country, new band)
            'W/New Mode': '#FFA726',      // Orange (worked country, new mode)
            'W/New Band+Mode': '#FF5722', // Deep Orange (worked country, new combo)
            'Worked': '#B0B0B0',          // Gray
            'Confirmed': '#10B981',       // Green
            'Unknown': '#666666'          // Dark Gray (unresolved DXCC)
        };
        const color = colors[status] || '#FFFFFF';
        return { color: color, fontWeight: 'bold', fontSize: '13px' };
    }
};

// Export for use in main app
window.FlexRadioUtils = utilityMethods;