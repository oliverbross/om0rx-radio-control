// Radio Controls Module
// FlexRadio Web Control v2.0 - Radio Controls & Commands

console.log('✅ Loading radio-controls.js module...');

const radioControlMethods = {
    // === Band Controls ===
    
    async setBand(band) {
        console.log('Setting band:', band);
        await this.sendCommand('band', { band: band.toLowerCase() });
    },
    
    isActiveBand(band) {
        const freq = this.radioStatus.frequency;
        const bandFreq = this.bandFrequencies[band];
        if (!freq || !bandFreq) return false;
        
        // Check if frequency is within ±5% of band frequency
        const tolerance = bandFreq * 0.05;
        return Math.abs(freq - bandFreq) < tolerance;
    },

    getActiveBandLabel() {
        return this.bands.find(band => this.isActiveBand(band)) || '';
    },

    getActiveBandKey() {
        const band = this.getActiveBandLabel();
        return band ? band.toLowerCase() : '';
    },

    isRotorEnabledForCurrentBand() {
        if (!this.rotorEnabled) return false;
        const bandKey = this.getActiveBandKey();
        if (!bandKey) return false;
        return this.rotorBands && this.rotorBands[bandKey] === true;
    },

    getRotorBandStatusText() {
        if (!this.rotorEnabled) return 'Rotor off';
        const band = this.getActiveBandLabel();
        if (!band) return 'Rotor band';
        return this.isRotorEnabledForCurrentBand() ? `Rotor ${band}` : `Rotor hidden ${band}`;
    },

    getRadioLayoutPreset() {
        return this.configData.RADIO_LAYOUT_PRESET || 'compact';
    },

    isRadioLayoutPreset(preset) {
        return this.getRadioLayoutPreset() === preset;
    },

    shouldShowCompactStepControl() {
        return !this.isRadioLayoutPreset('contest');
    },

    shouldShowCompactAgcControl() {
        return !this.isRadioLayoutPreset('digital');
    },

    shouldShowCompactDigitalButton() {
        return this.isRadioLayoutPreset('compact') || this.isRadioLayoutPreset('digital') || this.isRadioLayoutPreset('full');
    },

    shouldShowCompactRotorControls() {
        if (!this.isRotorEnabledForCurrentBand()) return false;
        return this.getRadioLayoutPreset() !== 'digital';
    },

    shouldShowMutedRotorCard() {
        if (!this.rotorEnabled || this.isRotorEnabledForCurrentBand()) return false;
        if (this.getRadioLayoutPreset() === 'digital') return false;
        return this.compactPanelPrefs.showMutedRotor !== false;
    },

    shouldShowCompactWinKeyer() {
        if (!this.winKeyerEnabled) return false;
        if (this.getRadioLayoutPreset() === 'digital') return false;
        return this.compactPanelPrefs.showWinKeyer !== false;
    },

    shouldShowCompactWinKeyerMemories() {
        if (!this.shouldShowCompactWinKeyer()) return false;
        if (this.getRadioLayoutPreset() === 'compact') {
            return this.compactPanelPrefs.showWinKeyerMemories === true;
        }
        return this.compactPanelPrefs.showWinKeyerMemories !== false;
    },

    shouldShowCompactStatusCard() {
        return this.compactPanelPrefs.showStatus !== false;
    },

    compactLayoutClass() {
        return `compact-layout-${this.getRadioLayoutPreset()}`;
    },

    applyPresetPanelDefaults(preset) {
        if (!this.compactPanelPrefs) return;
        if (preset === 'digital') {
            this.compactPanelPrefs.showMutedRotor = false;
            this.compactPanelPrefs.showWinKeyer = false;
            this.compactPanelPrefs.showWinKeyerMemories = false;
        } else if (preset === 'contest') {
            this.compactPanelPrefs.showMutedRotor = true;
            this.compactPanelPrefs.showWinKeyer = true;
            this.compactPanelPrefs.showWinKeyerMemories = true;
            this.compactPanelPrefs.showStatus = true;
        } else if (preset === 'compact') {
            this.compactPanelPrefs.showMutedRotor = true;
            this.compactPanelPrefs.showWinKeyer = true;
        } else if (preset === 'full') {
            this.compactPanelPrefs.showMutedRotor = true;
            this.compactPanelPrefs.showWinKeyer = true;
            this.compactPanelPrefs.showWinKeyerMemories = true;
            this.compactPanelPrefs.showStatus = true;
        }
        this.saveCompactPanelPrefs();
    },

    loadCompactPanelPrefs() {
        try {
            const raw = localStorage.getItem('om0rx.radio.compactPanelPrefs');
            if (!raw) return;
            const parsed = JSON.parse(raw);
            this.compactPanelPrefs = {
                showMutedRotor: parsed.showMutedRotor !== false,
                showWinKeyer: parsed.showWinKeyer !== false,
                showWinKeyerMemories: parsed.showWinKeyerMemories !== false,
                showStatus: parsed.showStatus !== false,
            };
        } catch (error) {
            console.warn('Could not load compact radio panel preferences:', error);
        }
    },

    saveCompactPanelPrefs() {
        try {
            localStorage.setItem('om0rx.radio.compactPanelPrefs', JSON.stringify(this.compactPanelPrefs));
        } catch (error) {
            console.warn('Could not save compact radio panel preferences:', error);
        }
    },

    toggleCompactPanelPref(prefKey) {
        if (!Object.prototype.hasOwnProperty.call(this.compactPanelPrefs, prefKey)) return;
        this.compactPanelPrefs[prefKey] = !this.compactPanelPrefs[prefKey];
        this.saveCompactPanelPrefs();
    },

    async handleBandSelect(event) {
        const band = event.target.value;
        if (band) {
            await this.setBand(band);
        }
    },
    
    // === Mode Controls ===
    
    async setMode(mode) {
        console.log('Setting mode:', mode);
        await this.sendCommand('mode', { mode });
    },

    async handleModeSelect(event) {
        const mode = event.target.value;
        if (mode) {
            await this.setMode(mode);
        }
    },
    
    // === Filter Controls ===
    
    async setFilter(lo, hi) {
        console.log('Setting filter:', lo, hi);
        await this.sendCommand('filter', { filter_lo: lo, filter_hi: hi });
    },

    getActiveFilterValue() {
        const active = this.currentFilters.find(filter => this.isActiveFilter(filter));
        return active ? `${active.lo}:${active.hi}` : '';
    },

    async handleFilterSelect(event) {
        const value = event.target.value;
        if (!value) return;
        const [lo, hi] = value.split(':').map(Number);
        if (Number.isFinite(lo) && Number.isFinite(hi)) {
            await this.setFilter(lo, hi);
        }
    },

    formatFilterWidth() {
        const lo = Number(this.radioStatus.filter_lo || 0);
        const hi = Number(this.radioStatus.filter_hi || 0);
        const width = Math.abs(hi - lo);
        if (!width) return 'Filter';
        return width >= 1000 ? `${(width / 1000).toFixed(width % 1000 === 0 ? 0 : 1)}K` : `${width}`;
    },

    async toggleDetailedRadioControls() {
        this.configData.RADIO_SHOW_DETAILED_CONTROLS = !this.configData.RADIO_SHOW_DETAILED_CONTROLS;
        this.configData.RADIO_LAYOUT_PRESET = this.configData.RADIO_SHOW_DETAILED_CONTROLS ? 'full' : 'compact';
        try {
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    config: {
                        RADIO_SHOW_DETAILED_CONTROLS: this.configData.RADIO_SHOW_DETAILED_CONTROLS,
                        RADIO_LAYOUT_PRESET: this.configData.RADIO_LAYOUT_PRESET,
                    },
                }),
            });
        } catch (error) {
            console.warn('Could not save radio control layout preference:', error);
        }
    },

    async setRadioLayoutPreset(event) {
        const preset = event.target.value || 'compact';
        this.configData.RADIO_LAYOUT_PRESET = preset;
        this.configData.RADIO_SHOW_DETAILED_CONTROLS = preset === 'full';
        this.applyPresetPanelDefaults(preset);
        try {
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    config: {
                        RADIO_LAYOUT_PRESET: preset,
                        RADIO_SHOW_DETAILED_CONTROLS: this.configData.RADIO_SHOW_DETAILED_CONTROLS,
                    },
                }),
            });
        } catch (error) {
            console.warn('Could not save radio layout preset:', error);
        }
    },
    
    isActiveFilter(filter) {
        return this.radioStatus.filter_lo === filter.lo && 
               this.radioStatus.filter_hi === filter.hi;
    },
    
    // === Slider Controls ===
    
    // Debounced slider helper
    debounceSlider(name, callback, delay = 150) {
        // Clear existing timer for this slider
        if (this.sliderDebounceTimers[name]) {
            clearTimeout(this.sliderDebounceTimers[name]);
        }
        
        // Set new timer
        this.sliderDebounceTimers[name] = setTimeout(callback, delay);
    },
    
    setVolume() {
        this.debounceSlider('volume', async () => {
            await this.sendCommand('volume', { value: this.controls.volume });
        });
    },
    
    setDrive() {
        this.debounceSlider('drive', async () => {
            await this.sendCommand('drive', { value: this.controls.drive });
        });
    },
    
    setTunePower() {
        this.debounceSlider('tunePower', async () => {
            await this.sendCommand('tune_power', { value: this.controls.tunePower });
        });
    },
    
    setMic() {
        this.debounceSlider('mic', async () => {
            await this.sendCommand('mic', { value: this.controls.mic });
        });
    },
    
    setMonitor() {
        this.debounceSlider('monitor', async () => {
            await this.sendCommand('monitor', { value: this.controls.monitor });
        });
    },
    
    setAGCThreshold() {
        this.debounceSlider('agcThreshold', async () => {
            await this.sendCommand('agc_threshold', { value: this.controls.agcThreshold });
        });
    },
    
    // === TX Controls ===
    
    async toggleMox() {
        this.txState.mox = !this.txState.mox;
        await this.sendCommand('mox', { enabled: this.txState.mox });
    },
    
    async toggleTune() {
        this.txState.tune = !this.txState.tune;
        await this.sendCommand('tune', { enabled: this.txState.tune });
    },
    
    async toggleVox() {
        this.txState.vox = !this.txState.vox;
        await this.sendCommand('vox', { enabled: this.txState.vox });
    },
    
    async toggleBreakin() {
        this.txState.breakin = !this.txState.breakin;
        await this.sendCommand('breakin', { enabled: this.txState.breakin });
    },
    
    async setTuningStep() {
        // Convert step text to Hz value
        const stepHz = this.getStepValue();
        await this.sendCommand('step', { step_hz: stepHz });
    },
    
    // === AGC Control ===
    
    async setAGC(mode) {
        console.log('Setting AGC:', mode);
        await this.sendCommand('agc', { mode });
    },
    
    async setAGCFromSlider() {
        const modes = ['off', 'slow', 'med', 'fast'];
        const mode = modes[this.agcSlider];
        if (mode) {
            await this.setAGC(mode);
        }
    },
    
    // === DSP Controls ===
    
    async toggleDSP(control) {
        const key = `${control}_enabled`;
        const newState = !this.radioStatus[key];
        console.log(`Toggling ${control.toUpperCase()}:`, newState);
        await this.sendCommand('dsp', { control, enabled: newState });
        
        // Toggle slider visibility when enabling
        if (newState) {
            this.showDSPSlider[control] = !this.showDSPSlider[control];
        } else {
            this.showDSPSlider[control] = false;
        }
    },
    
    setDSPLevel(control) {
        this.debounceSlider(`dsp_${control}`, async () => {
            const level = this.dspLevels[control];
            console.log(`Setting ${control.toUpperCase()} level:`, level);
            await this.sendCommand('dsp_level', { control: `${control}_level`, value: level });
        });
    },
    
    // === RX2 Control ===
    
    async toggleRX2() {
        const newState = !this.radioStatus.rx2_enabled;
        console.log('Toggling RX2:', newState);
        
        if (newState) {
            // Enable RX2 with frequency offset
            this.subVfoFreq = this.radioStatus.frequency + 0.010;  // +10 kHz
            await this.sendCommand('rx2', { enabled: true, frequency: this.subVfoFreq });
        } else {
            await this.sendCommand('rx2', { enabled: false });
        }
    },
    
    // === SPLIT Control ===
    
    async toggleSplit() {
        const newState = !this.radioStatus.split_enabled;
        console.log('Toggling SPLIT:', newState);
        
        if (newState) {
            // Enable split with TX offset
            const txFreq = this.radioStatus.frequency + 0.005;  // +5 kHz
            this.subVfoFreq = txFreq;
            await this.sendCommand('split', { enabled: true, tx_frequency: txFreq });
        } else {
            await this.sendCommand('split', { enabled: false });
        }
    },
    
    // === Frequency Controls ===
    
    async setFrequency(freq) {
        // Ensure frequency is a number and has proper precision
        const freqNum = parseFloat(freq);
        if (isNaN(freqNum)) {
            console.error('Invalid frequency:', freq);
            return;
        }
        
        console.log('Setting frequency:', freqNum);
        await this.sendCommand('frequency', { frequency: freqNum });
    },
    
    async adjustFrequency(direction) {
        const stepHz = this.currentStepHz;
        const stepMHz = stepHz / 1000000;
        const currentFreq = this.radioStatus.frequency;
        
        let newFreq;
        if (direction === 'up') {
            newFreq = currentFreq + stepMHz;
        } else {
            newFreq = currentFreq - stepMHz;
        }
        
        // Ensure we don't go below 0
        if (newFreq < 0) newFreq = 0;
        
        await this.setFrequency(newFreq);
    },
    
    // === Step Controls ===
    
    cycleStep() {
        this.currentStepIndex = (this.currentStepIndex + 1) % this.currentSteps.length;
        this.setTuningStep();
    },
    
    getStepValue() {
        const stepStr = this.currentSteps[this.currentStepIndex] || '10 Hz';
        const match = stepStr.match(/^([\d.]+)\s*(Hz|kHz)$/);
        if (match) {
            const value = parseFloat(match[1]);
            const unit = match[2];
            return unit === 'kHz' ? value * 1000 : value;
        }
        return 10; // Default fallback
    },
    
    // === RIT/XIT Controls ===
    
    async toggleRIT() {
        this.ritEnabled = !this.ritEnabled;
        console.log('Toggling RIT:', this.ritEnabled);
        await this.sendCommand('rit', { enabled: this.ritEnabled, value: this.ritValue });
    },
    
    async toggleXIT() {
        this.xitEnabled = !this.xitEnabled;
        console.log('Toggling XIT:', this.xitEnabled);
        await this.sendCommand('xit', { enabled: this.xitEnabled, value: this.xitValue });
    },
    
    async setRIT(value) {
        this.ritValue = value;
        if (this.ritEnabled) {
            await this.sendCommand('rit', { enabled: true, value: this.ritValue });
        }
    },
    
    async setXIT(value) {
        this.xitValue = value;
        if (this.xitEnabled) {
            await this.sendCommand('xit', { enabled: true, value: this.xitValue });
        }
    },
    
    // === AGC Cycling ===
    
    cycleAGC() {
        const modes = ['off', 'slow', 'med', 'fast'];
        const currentIndex = modes.indexOf(this.radioStatus.agc_mode);
        const nextIndex = (currentIndex + 1) % modes.length;
        this.setAGC(modes[nextIndex]);
    },
    
    // === Rotator Control ===
    
    async rotorGoto() {
        if (!this.rotorEnabled) {
            alert('Rotator not enabled');
            return;
        }

        if (this.rotorAzimuth === '' || this.rotorAzimuth === null || isNaN(this.rotorAzimuth)) {
            alert('Please enter a valid azimuth (0-359)');
            return;
        }

        const az = ((Math.round(this.rotorAzimuth) % 360) + 360) % 360;
        if (az < 0 || az > 359) {
            alert('Azimuth must be between 0 and 359 degrees');
            return;
        }

        try {
            console.log(`🎯 Rotor GOTO: ${az}°`);
            const response = await fetch('/api/rotor/goto', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ azimuth: az })
            });

            if (!response.ok) {
                const errorData = await response.json();
                const errorMsg = errorData.detail || `HTTP ${response.status}`;
                console.error('Rotor GOTO failed:', errorMsg);
                alert('Rotor command failed: ' + errorMsg);
                return;
            }

            const data = await response.json();
            if (data.ok) {
                console.log(`✅ Rotor moving to ${az}°`);
                this.showStatus(`🎯 Rotor → ${az}°`, 'success');
            } else {
                const errorMsg = data.message || data.error || 'Unknown error';
                console.error('Rotor GOTO failed:', errorMsg);
                alert('Rotor command failed: ' + errorMsg);
            }
        } catch (error) {
            console.error('Rotor GOTO error:', error);
            alert('Rotor error: ' + error.message);
        }
    },

    rotorDirection(direction) {
        if (!this.rotorEnabled || !this.rotorConnected) return;
        
        console.log('Rotor direction:', direction);
        
        try {
            fetch('/api/rotor/direction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ direction: direction })
            });
        } catch (error) {
            console.error('Rotor direction error:', error);
        }
    },

    async checkRotorStatus() {
        if (!this.rotorEnabled) return;
        if (this.rotorStatusLoading) return;
        this.rotorStatusLoading = true;
        
        try {
            const data = await this.fetchJsonWithTimeout('/api/rotor/status', {}, 4000);
            if (data.enabled) {
                this.rotorConnected = data.azimuth !== null;
                if (data.azimuth !== null) {
                    this.rotorAzimuth = data.azimuth;
                }
            } else {
                this.rotorConnected = false;
            }
        } catch (error) {
            console.error('Failed to check rotor status:', error);
            this.rotorConnected = false;
        } finally {
            this.rotorStatusLoading = false;
        }
    },

    toggleRotorAuto() {
        if (!this.rotorEnabled) {
            alert('Rotator not enabled');
            return;
        }

        this.rotorAutoEnabled = !this.rotorAutoEnabled;
        console.log(`🤖 Rotor AUTO ${this.rotorAutoEnabled ? 'ENABLED' : 'DISABLED'}`);
        this.saveRotorAutoConfig();
    },

    async openRotorCompassWindow() {
        if (window.pywebview?.api?.open_rotor_compass_window) {
            try {
                const result = await window.pywebview.api.open_rotor_compass_window();
                if (!result || result.success !== false) return;
                console.warn('Native rotor compass window failed:', result.error || result);
            } catch (error) {
                console.warn('Could not open native rotor compass window:', error);
            }
        }

        const features = [
            'width=720',
            'height=760',
            'left=120',
            'top=90',
            'resizable=yes',
            'scrollbars=no',
            'menubar=no',
            'toolbar=no',
            'location=no',
            'status=no',
        ].join(',');
        if (this.rotorCompassWindow && !this.rotorCompassWindow.closed) {
            this.rotorCompassWindow.focus();
            return;
        }
        this.rotorCompassWindow = window.open('/rotor-compass.html', 'rotorCompassWindow', features);
        if (!this.rotorCompassWindow) {
            alert('Popup blocked. Allow popups for this app to open the rotor compass.');
        }
    },

    cancelRotorAuto() {
        if (this.rotorAutoTimer) {
            clearTimeout(this.rotorAutoTimer);
            this.rotorAutoTimer = null;
        }
        this.rotorAutoPending = null;
        console.log('⏸️ Rotor AUTO action cancelled');
    },

    buildRotorRequest(callsign, frequency_khz, gridsquare, latitude, longitude, options = {}) {
        return {
            callsign,
            frequency_khz,
            gridsquare: gridsquare || null,
            latitude: latitude ?? null,
            longitude: longitude ?? null,
            location_source: options.location_source || options.source || null,
            grid_source: options.grid_source || null,
            qrz_grid: options.qrz_grid || null,
            qrz_gridsquare: options.qrz_gridsquare || null,
            wavelog_grid: options.wavelog_grid || null,
            wavelog_gridsquare: options.wavelog_gridsquare || null,
            qrz_latitude: options.qrz_latitude ?? null,
            qrz_longitude: options.qrz_longitude ?? null,
            wavelog_latitude: options.wavelog_latitude ?? null,
            wavelog_longitude: options.wavelog_longitude ?? null,
            cty_latitude: options.cty_latitude ?? null,
            cty_longitude: options.cty_longitude ?? null
        };
    },

    updateBeamingDisplay(callsign, data) {
        if (data.short_path_bearing === undefined || data.long_path_bearing === undefined) {
            return;
        }

        this.currentBeamingCallsign = callsign;
        this.shortPathBearing = data.short_path_bearing;
        this.longPathBearing = data.long_path_bearing;
        this.beamingSource = data.source || null;
        this.beamingSourceLabel = data.source_label || data.source || null;
        this.beamingConfidence = data.confidence || null;
        this.beamingApproximate = !!data.approximate;
        this.lastBeamingTime = new Date();
    },

    async resolveRotorTarget(callsign, frequency_khz, gridsquare, latitude, longitude, options = {}) {
        const response = await fetch('/api/rotor/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.buildRotorRequest(callsign, frequency_khz, gridsquare, latitude, longitude, options))
        });

        if (!response.ok) {
            throw new Error(`Rotor resolve failed: HTTP ${response.status}`);
        }

        const data = await response.json();
        this.updateBeamingDisplay(callsign, data);
        return data;
    },

    async rotorAutoGoto(callsign, frequency_khz, gridsquare, latitude, longitude, options = {}) {
        // Only proceed if AUTO is enabled
        if (!this.rotorAutoEnabled || !this.rotorEnabled) {
            console.warn(`⚠️ rotorAutoGoto called but not enabled: rotorAutoEnabled=${this.rotorAutoEnabled}, rotorEnabled=${this.rotorEnabled}`);
            return;
        }

        console.log(`✅ rotorAutoGoto starting for ${callsign} with grid=${gridsquare}, lat=${latitude}, lon=${longitude}`);

        // Cancel any pending AUTO action
        this.cancelRotorAuto();

        // Set pending info
        this.rotorAutoPending = { callsign, frequency_khz, gridsquare, latitude, longitude, options };
        const delayMs = (this.configData.ROTOR_AUTO_DELAY_SEC || 2.0) * 1000;
        console.log(`⏱️ Rotor AUTO pending: ${callsign} - waiting ${delayMs/1000}s for cancellation`);

        // 2-second delay before actually moving
        this.rotorAutoTimer = setTimeout(async () => {
            if (this.rotorAutoPending === null) {
                return; // Already cancelled
            }

            try {
                const response = await fetch('/api/rotor/auto/goto', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        ...this.buildRotorRequest(callsign, frequency_khz, gridsquare, latitude, longitude, options)
                    })
                });

                if (response.ok) {
                    const data = await response.json();
                    console.log(`📡 Rotor AUTO response:`, data);
                    
                    // Always update beaming display if we have bearing data
                    this.updateBeamingDisplay(callsign, data);
                    if (data.short_path_bearing !== undefined && data.long_path_bearing !== undefined) {
                        console.log(`✅ Beaming display updated: SP=${data.short_path_bearing}°, LP=${data.long_path_bearing}°`);
                    }
                    
                    if (data.ok) {
                        console.log(`✅ AUTO rotor moved to ${data.bearing}°: ${callsign}`);
                        const qualifier = data.approximate ? ' approx.' : '';
                        this.showStatus(`🤖 Rotor → ${data.bearing}°${qualifier} for ${callsign}`, 'success');
                    } else {
                        console.log(`ℹ️ Rotor AUTO not executed: ${data.message}`);
                        this.showStatus(`⚠️ AUTO rotor: ${data.message}`, 'warning');
                    }
                } else {
                    console.error('Rotor AUTO GOTO failed:', response.statusText);
                    this.showStatus(`❌ Rotor AUTO error: ${response.statusText}`, 'error');
                }
            } catch (error) {
                console.error('Rotor AUTO GOTO error:', error);
                this.showStatus(`❌ Rotor AUTO error: ${error.message}`, 'error');
            } finally {
                this.rotorAutoTimer = null;
                this.rotorAutoPending = null;
            }
        }, delayMs);
    },

    // Manual rotor GO for short path bearing
    async rotorGotoShortPath() {
        if (this.shortPathBearing === null) {
            alert('No short path bearing available');
            return;
        }
        this.rotorAzimuth = this.shortPathBearing;
        await this.rotorGoto();
    },

    // Manual rotor GO for long path bearing
    async rotorGotoLongPath() {
        if (this.longPathBearing === null) {
            alert('No long path bearing available');
            return;
        }
        this.rotorAzimuth = this.longPathBearing;
        await this.rotorGoto();
    },

    async saveRotorAutoConfig() {
        try {
            const response = await fetch('/api/rotor/auto/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    home_grid: this.rotorHomeGrid || 'JN88TQ',
                    home_lat: this.rotorHomeLat || 48.17,
                    home_lon: this.rotorHomeLon || 17.08,
                    bands: this.rotorBands,
                    auto_enabled: this.rotorAutoEnabled
                })
            });

            if (response.ok) {
                console.log('✅ Rotor AUTO config saved');
            } else {
                console.error('Failed to save rotor AUTO config');
                alert('Failed to save rotor AUTO config');
            }
        } catch (error) {
            console.error('Rotor AUTO config save error:', error);
            alert('Error: ' + error.message);
        }
    },

    async loadRotorAutoConfig() {
        try {
            const response = await fetch('/api/rotor/auto/status');
            if (response.ok) {
                const data = await response.json();
                if (data.ok) {
                    this.rotorAutoEnabled = data.auto_enabled || false;
                    this.rotorHomeGrid = data.home_grid || 'JN88TQ';
                    this.rotorHomeLat = data.home_lat || 48.17;
                    this.rotorHomeLon = data.home_lon || 17.08;
                    this.rotorBands = { ...this.rotorBands, ...data.bands };
                    console.log('✅ Rotor AUTO config loaded:', data);
                }
            }
        } catch (error) {
            console.warn('Could not load rotor AUTO config:', error);
        }
    },

    async handleDirectorToggle() {
        if (!this.rotorEnabled) {
            return;
        }
        
        if (!this.rotorPreset || this.rotorPreset === '') {
            return;
        }
        
        let newAz = this.rotorPreset === 'longpath' && this.longPathBearing !== null
            ? this.longPathBearing
            : this.shortPathBearing;
        if (this.rotorPreset !== 'shortpath' && this.rotorPreset !== 'longpath') {
            newAz = this.rotorAzimuth + 180;
        }
        if (newAz === null || newAz === undefined || isNaN(newAz)) {
            alert('No bearing available for selected path');
            return;
        }
        newAz = ((Math.round(newAz) % 360) + 360) % 360;
        
        console.log(`🌐 Director toggle: ${this.rotorPreset} at ${this.rotorAzimuth}° → ${Math.round(newAz)}°`);
        
        try {
            const response = await fetch('/api/rotor/goto', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ azimuth: Math.round(newAz) })
            });
            
            if (response.ok) {
                const data = await response.json();
                this.rotorAzimuth = Math.round(newAz);
                console.log('✅ Rotor director toggled:', data);
            } else {
                alert('Rotor command failed: ' + response.statusText);
            }
        } catch (error) {
            console.error('Rotor director toggle error:', error);
            alert('Rotor error: ' + error.message);
        }
    },

    validateAzimuth() {
        if (this.rotorAzimuth < 0) this.rotorAzimuth = 0;
        if (this.rotorAzimuth > 360) this.rotorAzimuth = 360;
    },

    // === Cluster Commands ===

    async sendClusterCommand(command) {
        try {
            console.log(`📡 Sending cluster command: ${command}`);
            const response = await fetch('/api/cluster/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: command })
            });

            const data = await response.json();
            if (data.success) {
                console.log(`✅ Cluster command sent: ${command}`);
                this.showStatus(`📡 Cluster: ${command}`, 'success');
            } else {
                console.error('Cluster command failed:', data.message);
                this.showStatus(`❌ Cluster error: ${data.message}`, 'error');
            }
        } catch (error) {
            console.error('Cluster command error:', error);
            this.showStatus(`❌ Cluster error: ${error.message}`, 'error');
        }
    },

    async sendSHDX() {
        await this.sendClusterCommand('SH/DX/100');
    },

    async reconnectCluster() {
        try {
            console.log('🔗 Attempting cluster reconnect...');
            const response = await fetch('/api/cluster/reconnect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            const data = await response.json();
            if (data.success) {
                console.log('✅ Cluster reconnect initiated');
                this.showStatus('🔗 Cluster reconnecting...', 'info');
            } else {
                console.error('Cluster reconnect failed:', data.message);
                this.showStatus(`❌ Reconnect failed: ${data.message}`, 'error');
            }
        } catch (error) {
            console.error('Cluster reconnect error:', error);
            this.showStatus(`❌ Reconnect error: ${error.message}`, 'error');
        }
    }
};

// Export for use in main app
window.FlexRadioControls = radioControlMethods;
