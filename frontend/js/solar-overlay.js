// Solar & HF Conditions Overlay Module
// Displays compact solar/HF conditions as overlays on callsign/profile areas

console.log('✅ Loading solar-overlay.js module...');

const SolarOverlay = {
    // Cache for solar data
    solarCache: {
        data: null,
        timestamp: 0,
        refreshIntervalMs: 10 * 60 * 1000 // 10 minutes
    },

    // Configuration
    config: {
        showOverlays: true,
        autoRefresh: true,
        overlayPosition: 'bottom', // 'bottom', 'top', 'bottom-right'
        showDetailedBands: false,  // Show individual band conditions
        compactMode: true         // Use compact display
    },

    /**
     * Initialize solar overlay system
     */
    async init() {
        console.log('🌞 Initializing Solar Overlay System...');
        
        // Load initial solar data
        await this.loadSolarData();
        
        // Set up auto-refresh if enabled
        if (this.config.autoRefresh) {
            setInterval(() => {
                this.loadSolarData();
            }, this.solarCache.refreshIntervalMs);
        }
        
        // Create CSS if not exists
        this.injectCSS();
        
        console.log('✅ Solar Overlay System initialized');
    },

    /**
     * Load solar data from backend API
     */
    async loadSolarData() {
        try {
            const response = await fetch('/api/solar');
            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }
            
            const data = await response.json();
            this.solarCache.data = data;
            this.solarCache.timestamp = Date.now();
            
            console.log('🌞 Solar data loaded:', data.indices);
            
            // Update existing overlays
            this.updateExistingOverlays();
            
            return data;
            
        } catch (error) {
            console.error('❌ Failed to load solar data:', error);
            return null;
        }
    },

    /**
     * Create overlay HTML for a callsign area
     */
    createOverlay(parentElement, options = {}) {
        if (!this.config.showOverlays || !this.solarCache.data) {
            return null;
        }

        const data = this.solarCache.data;
        const indices = data.indices || {};
        const levels = data.quality_levels || {};
        
        // Create overlay container
        const overlay = document.createElement('div');
        overlay.className = 'solar-overlay';
        overlay.dataset.overlayId = Date.now() + Math.random();
        
        // Build compact overlay content
        if (this.config.compactMode) {
            overlay.innerHTML = `
                <div class="solar-compact">
                    <div class="solar-indices">
                        <span class="solar-badge solar-sfi ${levels.sfi || 'unknown'}" title="Solar Flux Index">
                            SFI ${indices.sfi || '—'}
                        </span>
                        <span class="solar-badge solar-a ${levels.a_index || 'unknown'}" title="A-index (Geomagnetic Activity)">
                            A${indices.a_index || '—'}
                        </span>
                        <span class="solar-badge solar-k ${levels.k_index || 'unknown'}" title="K-index (Geomagnetic Activity)">
                            K${indices.k_index || '—'}
                        </span>
                    </div>
                    ${this.config.showDetailedBands ? this.createBandConditions(data.hf_conditions) : ''}
                </div>
            `;
        } else {
            // Detailed overlay
            overlay.innerHTML = `
                <div class="solar-detailed">
                    <div class="solar-header">Solar & HF</div>
                    <div class="solar-indices">
                        <div class="solar-index">
                            <span class="label">SFI</span>
                            <span class="value ${levels.sfi || 'unknown'}">${indices.sfi || '—'}</span>
                        </div>
                        <div class="solar-index">
                            <span class="label">A</span>
                            <span class="value ${levels.a_index || 'unknown'}">${indices.a_index || '—'}</span>
                        </div>
                        <div class="solar-index">
                            <span class="label">K</span>
                            <span class="value ${levels.k_index || 'unknown'}">${indices.k_index || '—'}</span>
                        </div>
                    </div>
                    ${this.createBandConditions(data.hf_conditions)}
                </div>
            `;
        }
        
        // Position overlay
        this.positionOverlay(overlay, parentElement, options);
        
        // Add to parent
        if (parentElement.style.position === '' || parentElement.style.position === 'static') {
            parentElement.style.position = 'relative';
        }
        parentElement.appendChild(overlay);
        
        return overlay;
    },

    /**
     * Create band conditions display
     */
    createBandConditions(hfConditions) {
        if (!hfConditions) return '';
        
        const isDay = this.isDaytime();
        const bands = Object.entries(hfConditions).map(([band, conditions]) => {
            const condition = isDay ? conditions.day : conditions.night;
            const conditionClass = this.getConditionClass(condition);
            
            return `
                <span class="band-condition ${conditionClass}" title="${band.replace('m_', 'm-')} ${isDay ? 'Day' : 'Night'}: ${condition}">
                    ${band.replace('m_', 'm-').replace('_', '-')}
                </span>
            `;
        }).join('');
        
        return `
            <div class="band-conditions">
                <div class="conditions-label">${isDay ? '☀️' : '🌙'}</div>
                ${bands}
            </div>
        `;
    },

    /**
     * Position overlay on parent element
     */
    positionOverlay(overlay, parentElement, options = {}) {
        const position = options.position || this.config.overlayPosition;
        
        overlay.style.position = 'absolute';
        overlay.style.zIndex = '1000';
        overlay.style.pointerEvents = 'none'; // Don't interfere with parent clicks
        
        switch (position) {
            case 'bottom':
                overlay.style.bottom = '2px';
                overlay.style.left = '50%';
                overlay.style.transform = 'translateX(-50%)';
                break;
            case 'bottom-right':
                overlay.style.bottom = '2px';
                overlay.style.right = '2px';
                break;
            case 'top':
                overlay.style.top = '2px';
                overlay.style.left = '50%';
                overlay.style.transform = 'translateX(-50%)';
                break;
            case 'top-right':
                overlay.style.top = '2px';
                overlay.style.right = '2px';
                break;
            default:
                // Default to bottom center
                overlay.style.bottom = '2px';
                overlay.style.left = '50%';
                overlay.style.transform = 'translateX(-50%)';
        }
    },

    /**
     * Add overlay to DX spots callsign cells
     */
    addToSpotsCells() {
        if (!this.solarCache.data) return;
        
        // Find all callsign cells in spots table
        const callsignCells = document.querySelectorAll('.spots-table td:nth-child(4)'); // 4th column is callsign
        
        callsignCells.forEach(cell => {
            // Don't add multiple overlays
            if (cell.querySelector('.solar-overlay')) return;
            
            // Add overlay to callsign cell
            this.createOverlay(cell, { position: 'bottom-right' });
        });
    },

    /**
     * Add overlay to specific element by selector
     */
    addToElement(selector, options = {}) {
        const elements = document.querySelectorAll(selector);
        elements.forEach(element => {
            // Don't add multiple overlays
            if (element.querySelector('.solar-overlay')) return;
            
            this.createOverlay(element, options);
        });
    },

    /**
     * Update all existing overlays with fresh data
     */
    updateExistingOverlays() {
        const existingOverlays = document.querySelectorAll('.solar-overlay');
        existingOverlays.forEach(overlay => {
            const parent = overlay.parentElement;
            if (parent) {
                overlay.remove();
                this.createOverlay(parent);
            }
        });
    },

    /**
     * Remove all overlays
     */
    removeAllOverlays() {
        const overlays = document.querySelectorAll('.solar-overlay');
        overlays.forEach(overlay => overlay.remove());
    },

    /**
     * Toggle overlay visibility
     */
    toggleOverlays() {
        this.config.showOverlays = !this.config.showOverlays;
        
        if (this.config.showOverlays) {
            this.updateExistingOverlays();
        } else {
            this.removeAllOverlays();
        }
    },

    /**
     * Helper: Determine if it's daytime (rough estimate)
     */
    isDaytime() {
        const hour = new Date().getHours();
        return hour >= 6 && hour < 20; // 6 AM to 8 PM considered day
    },

    /**
     * Helper: Get CSS class for HF condition
     */
    getConditionClass(condition) {
        if (!condition) return 'unknown';
        
        const cond = condition.toLowerCase();
        if (cond.includes('good') || cond.includes('excellent')) return 'good';
        if (cond.includes('fair') || cond.includes('normal')) return 'fair';
        if (cond.includes('poor') || cond.includes('bad')) return 'poor';
        return 'unknown';
    },

    /**
     * Inject required CSS styles
     */
    injectCSS() {
        // Remove old styles if they exist to force refresh
        const existingStyle = document.getElementById('solar-overlay-styles');
        if (existingStyle) existingStyle.remove();
        
        const style = document.createElement('style');
        style.id = 'solar-overlay-styles';
        style.textContent = `
            /* Solar Overlay Styles */
            .solar-overlay {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                user-select: none;
                filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
            }
            
            .solar-compact {
                background: rgba(20, 20, 30, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                padding: 2px 6px;
                backdrop-filter: blur(4px);
            }
            
            .solar-indices {
                display: flex;
                gap: 4px;
                align-items: center;
            }
            
            .solar-badge {
                font-size: 9px;
                font-weight: 600;
                padding: 1px 4px;
                border-radius: 3px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                white-space: nowrap;
            }
            
            .solar-badge.good {
                background: rgba(34, 197, 94, 0.8);
                color: white;
            }
            
            .solar-badge.fair {
                background: rgba(251, 191, 36, 0.8);
                color: black;
            }
            
            .solar-badge.poor {
                background: rgba(239, 68, 68, 0.8);
                color: white;
            }
            
            .solar-badge.unknown {
                background: rgba(107, 114, 128, 0.8);
                color: white;
            }
            
            .band-conditions {
                margin-top: 2px;
                display: flex;
                gap: 2px;
                align-items: center;
            }
            
            .conditions-label {
                font-size: 8px;
                margin-right: 2px;
            }
            
            .band-condition {
                font-size: 11px;
                padding: 1px 2px;
                border-radius: 2px;
                background: rgba(107, 114, 128, 0.6);
                color: white;
            }
            
            .band-condition.good {
                background: rgba(34, 197, 94, 0.7);
            }
            
            .band-condition.fair {
                background: rgba(251, 191, 36, 0.7);
            }
            
            .band-condition.poor {
                background: rgba(239, 68, 68, 0.7);
            }
            
            /* Detailed overlay styles */
            .solar-detailed {
                background: rgba(15, 15, 25, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                padding: 8px;
                min-width: 120px;
                backdrop-filter: blur(8px);
            }
            
            .solar-header {
                font-size: 10px;
                font-weight: 700;
                text-align: center;
                margin-bottom: 4px;
                color: rgba(255, 255, 255, 0.8);
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            .solar-detailed .solar-indices {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 6px;
                margin-bottom: 6px;
            }
            
            .solar-index {
                text-align: center;
            }
            
            .solar-index .label {
                display: block;
                font-size: 10px;
                color: rgba(255, 255, 255, 0.6);
                margin-bottom: 1px;
            }
            
            .solar-index .value {
                display: block;
                font-size: 13px;
                font-weight: 700;
            }
            
            .solar-index .value.good {
                color: #22c55e;
            }
            
            .solar-index .value.fair {
                color: #fbbf24;
            }
            
            .solar-index .value.poor {
                color: #ef4444;
            }
            
            .solar-index .value.unknown {
                color: #6b7280;
            }
            
            /* Responsive adjustments */
            @media (max-width: 768px) {
                .solar-badge {
                    font-size: 8px;
                    padding: 1px 3px;
                }
                
                .band-condition {
                    font-size: 6px;
                }
            }
            
            /* Animation for updates */
            .solar-overlay {
                transition: opacity 0.2s ease-in-out;
            }
            
            .solar-overlay.updating {
                opacity: 0.7;
            }
        `;
        
        document.head.appendChild(style);
    },

    /**
     * Get current solar data
     */
    getSolarData() {
        return this.solarCache.data;
    },

    /**
     * Check if data is fresh
     */
    isDataFresh() {
        if (!this.solarCache.data) return false;
        
        const age = Date.now() - this.solarCache.timestamp;
        return age < this.solarCache.refreshIntervalMs;
    },

    /**
     * Force refresh solar data
     */
    async refresh() {
        console.log('🔄 Force refreshing solar data...');
        await this.loadSolarData();
    }
};

// Export for use in other modules
window.SolarOverlay = SolarOverlay;