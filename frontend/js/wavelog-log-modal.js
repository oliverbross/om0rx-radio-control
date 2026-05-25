// Wavelog Log Modal - Display Wavelog logged QSOs in a beautiful table with filtering and pagination
// Shows latest contacts on top

console.log('✅ Loading wavelog-log-modal.js module...');

const WavelogLogModal = {
    // State management
    allQsos: [],
    filteredQsos: [],
    currentPage: 1,
    itemsPerPage: 10,
    currentLoadedLimit: 50, // Track how many records we've loaded from backend
    filters: {
        callsign: '',
        mode: '',
        band: '',
        awards: '' // pota, sota, wwff, iota
    },
    sortField: 'qso_date',
    sortDirection: 'desc', // newest first
    isRefreshing: false,
    lastRefreshedTime: null,
    
    /**
     * Initialize wavelog log modal
     */
    init() {
        console.log('📊 Initializing Wavelog Log Modal...');
        
        // Set up close button event listeners
        const closeBtn = document.querySelector('.wavelog-log-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.hideModal();
            });
        }
        
        // Set up modal backdrop click handler
        const modal = document.querySelector('.wavelog-log-modal');
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.hideModal();
                }
            });
        }
        
        // Set up filter inputs
        this.setupFilters();
    },
    
    /**
     * Set up filter input event listeners
     */
    setupFilters() {
        const filterInputs = {
            'wavelog-filter-callsign': 'callsign',
            'wavelog-filter-mode': 'mode',
            'wavelog-filter-band': 'band',
            'wavelog-filter-awards': 'awards'
        };
        
        for (const [elemId, filterKey] of Object.entries(filterInputs)) {
            const elem = document.getElementById(elemId);
            if (elem) {
                elem.addEventListener('input', (e) => {
                    this.filters[filterKey] = e.target.value.toUpperCase();
                    this.currentPage = 1;
                    this.applyFilters();
                    this.renderTable();
                });
            }
        }
    },
    
    /**
     * Show the wavelog log modal and load QSOs
     */
    async showModal() {
        const modal = document.querySelector('.wavelog-log-modal');
        if (!modal) return;
        
        // Show modal
        modal.style.display = 'flex';
        
        // Always reload Wavelog contacts (they may have changed)
        await this.loadQsos();
        
        // Apply filters and render
        this.applyFilters();
        this.renderTable();
    },
    
    /**
     * Hide the wavelog log modal
     */
    hideModal() {
        const modal = document.querySelector('.wavelog-log-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    },
    
    /**
     * Load all QSOs from Wavelog via backend
     * @param {number} limit - Number of records to load (default 100)
     */
    async loadQsos(limit = 100) {
        try {
            console.log(`📊 Loading Wavelog contacts (limit: ${limit})...`);
            const response = await fetch(`/api/wavelog/contacts?limit=${limit}`);
            if (response.ok) {
                const result = await response.json();
                if (result.success && result.data) {
                    this.allQsos = result.data;
                    this.currentLoadedLimit = limit; // Track the limit
                    // Update last refreshed time
                    const now = new Date();
                    this.lastRefreshedTime = now.toLocaleTimeString('en-US', { 
                        hour12: false, 
                        hour: '2-digit', 
                        minute: '2-digit', 
                        second: '2-digit' 
                    });
                    this.updateRefreshTimestamp();
                    console.log(`✅ Loaded ${this.allQsos.length} QSOs from Wavelog at ${this.lastRefreshedTime}`);
                } else {
                    console.warn('⚠️ Failed to load Wavelog QSOs:', result.message || 'Unknown error');
                    this.allQsos = [];
                }
            } else {
                console.error('❌ Failed to fetch Wavelog QSOs:', response.statusText);
                this.allQsos = [];
            }
        } catch (error) {
            console.error('❌ Error loading Wavelog QSOs:', error);
            this.allQsos = [];
        }
    },
    
    /**
     * Update the refresh timestamp display
     */
    updateRefreshTimestamp() {
        const timeElem = document.getElementById('wavelog-refresh-time');
        if (timeElem && this.lastRefreshedTime) {
            timeElem.textContent = `⏱️ ${this.lastRefreshedTime}`;
            timeElem.classList.remove('loading');
        }
    },
    
    /**
     * Refresh QSOs (manual refresh triggered by user clicking refresh button)
     */
    async refresh() {
        if (this.isRefreshing) {
            console.log('⚠️ Refresh already in progress...');
            return;
        }
        
        this.isRefreshing = true;
        const refreshBtn = document.getElementById('wavelog-btn-refresh');
        const timeElem = document.getElementById('wavelog-refresh-time');
        
        // Show loading state
        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.classList.add('loading');
            refreshBtn.innerHTML = '⏳ Refreshing...';
        }
        if (timeElem) {
            timeElem.classList.add('loading');
            timeElem.textContent = '⏳ Refreshing...';
        }
        
        try {
            console.log('🔄 Manual refresh triggered by user');
            // Refresh with at least the current limit to maintain user's selection
            const refreshLimit = Math.max(this.currentLoadedLimit, this.itemsPerPage);
            await this.loadQsos(refreshLimit);
            
            // Reapply filters and render
            this.applyFilters();
            this.renderTable();
            
            console.log('✅ Refresh complete!');
        } catch (error) {
            console.error('❌ Error during refresh:', error);
            if (timeElem) {
                timeElem.textContent = '⚠️ Refresh failed';
            }
        } finally {
            // Restore button state
            this.isRefreshing = false;
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.classList.remove('loading');
                refreshBtn.innerHTML = '🔄 Refresh';
            }
            this.updateRefreshTimestamp();
        }
    },
    
    /**
     * Apply filters to QSOs
     */
    applyFilters() {
        this.filteredQsos = this.allQsos.filter(qso => {
            // Filter by callsign
            if (this.filters.callsign && !qso.call.includes(this.filters.callsign)) {
                return false;
            }
            
            // Filter by mode
            if (this.filters.mode && qso.mode !== this.filters.mode) {
                return false;
            }
            
            // Filter by band
            if (this.filters.band && qso.band !== this.filters.band) {
                return false;
            }
            
            // Filter by awards (POTA, SOTA, WWFF, IOTA)
            if (this.filters.awards) {
                const hasPOTA = qso.pota_ref && qso.pota_ref.length > 0;
                const hasSOTA = qso.sota_ref && qso.sota_ref.length > 0;
                const hasWWFF = qso.wwff_ref && qso.wwff_ref.length > 0;
                const hasIOTA = qso.iota && qso.iota.length > 0;
                
                if (this.filters.awards === 'POTA' && !hasPOTA) return false;
                if (this.filters.awards === 'SOTA' && !hasSOTA) return false;
                if (this.filters.awards === 'WWFF' && !hasWWFF) return false;
                if (this.filters.awards === 'IOTA' && !hasIOTA) return false;
            }
            
            return true;
        });
        
        // Update page info
        const pageCount = Math.ceil(this.filteredQsos.length / this.itemsPerPage);
        if (this.currentPage > pageCount) {
            this.currentPage = Math.max(1, pageCount);
        }
    },
    
    /**
     * Format date from YYYYMMDD to YYYY-MM-DD
     */
    formatDate(dateStr) {
        if (!dateStr || dateStr.length !== 8) return dateStr;
        return `${dateStr.slice(0, 4)}-${dateStr.slice(4, 6)}-${dateStr.slice(6, 8)}`;
    },
    
    /**
     * Format time from HHMMSS to HH:MM:SS
     */
    formatTime(timeStr) {
        if (!timeStr || timeStr.length !== 6) return timeStr;
        return `${timeStr.slice(0, 2)}:${timeStr.slice(2, 4)}:${timeStr.slice(4, 6)}`;
    },
    
    /**
     * Format frequency to display nicely
     */
    formatFrequency(freq) {
        if (!freq) return '';
        // Convert to number if it's a string (API returns frequency as string)
        const numFreq = typeof freq === 'string' ? parseFloat(freq) : freq;
        if (isNaN(numFreq)) return '-';
        return numFreq.toFixed(3);
    },
    
    /**
     * Get visible QSOs for current page
     */
    getPaginatedQsos() {
        const start = (this.currentPage - 1) * this.itemsPerPage;
        const end = start + this.itemsPerPage;
        return this.filteredQsos.slice(start, end);
    },
    
    /**
     * Render the QSO table
     */
    renderTable() {
        const tableBody = document.querySelector('.wavelog-log-table tbody');
        if (!tableBody) return;
        
        // Clear existing rows
        tableBody.innerHTML = '';
        
        // Get QSOs for current page
        const pageQsos = this.getPaginatedQsos();
        
        if (pageQsos.length === 0) {
            const row = tableBody.insertRow();
            row.innerHTML = '<td colspan="9" style="text-align: center; padding: 20px; color: #888;">No QSOs found</td>';
            this.updatePaginationInfo();
            return;
        }
        
        // Render each QSO row
        pageQsos.forEach(qso => {
            const row = tableBody.insertRow();
            
            // Build awards column
            const awards = [];
            if (qso.pota_ref) awards.push(qso.pota_ref);
            if (qso.sota_ref) awards.push(qso.sota_ref);
            if (qso.wwff_ref) awards.push(qso.wwff_ref);
            if (qso.iota) awards.push(qso.iota);
            const awardsText = awards.join(' / ') || '-';
            
            row.innerHTML = `
                <td class="cell-date">${this.formatDate(qso.qso_date)}</td>
                <td class="cell-time">${this.formatTime(qso.time_on)}</td>
                <td class="cell-call"><strong>${qso.call}</strong></td>
                <td class="cell-freq">${this.formatFrequency(qso.frequency)}</td>
                <td class="cell-band">${qso.band || '-'}</td>
                <td class="cell-mode">${qso.mode}</td>
                <td class="cell-rst">${qso.rst_sent}/${qso.rst_rcvd}</td>
                <td class="cell-dxcc">${(qso.country || '-').toUpperCase()}</td>
                <td class="cell-awards">${awardsText}</td>
                <td class="cell-name">${qso.name ? qso.name.toUpperCase().substring(0, 20) + (qso.name.length > 20 ? '...' : '') : (qso.qth || '-').toUpperCase()}</td>
            `;
        });
        
        this.updatePaginationInfo();
    },
    
    /**
     * Update pagination info display and button states
     */
    updatePaginationInfo() {
        const paginationInfo = document.querySelector('.wavelog-log-pagination-info');
        if (!paginationInfo) return;
        
        const totalPages = Math.ceil(this.filteredQsos.length / this.itemsPerPage);
        const startItem = this.filteredQsos.length === 0 ? 0 : (this.currentPage - 1) * this.itemsPerPage + 1;
        const endItem = Math.min(this.currentPage * this.itemsPerPage, this.filteredQsos.length);
        
        paginationInfo.textContent = `Showing ${startItem}-${endItem} of ${this.filteredQsos.length} QSOs (Page ${this.currentPage}/${totalPages || 1})`;
        
        // Update button states
        const prevBtn = document.getElementById('wavelog-btn-prev-page');
        const nextBtn = document.getElementById('wavelog-btn-next-page');
        
        if (prevBtn) {
            prevBtn.disabled = this.currentPage <= 1;
        }
        if (nextBtn) {
            nextBtn.disabled = this.currentPage >= totalPages || totalPages === 0;
        }
    },
    
    /**
     * Go to specific page
     */
    goToPage(page) {
        const totalPages = Math.ceil(this.filteredQsos.length / this.itemsPerPage);
        if (page >= 1 && page <= totalPages) {
            this.currentPage = page;
            this.renderTable();
        }
    },
    
    /**
     * Go to next page
     */
    async nextPage() {
        const totalPages = Math.ceil(this.filteredQsos.length / this.itemsPerPage);
        if (this.currentPage < totalPages) {
            this.currentPage++;
            this.renderTable();
        }
    },
    
    /**
     * Go to previous page
     */
    prevPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.renderTable();
        }
    },
    
    /**
     * Change items per page and reload data if needed
     */
    async setItemsPerPage(count) {
        const newItemsPerPage = parseInt(count);
        this.itemsPerPage = newItemsPerPage;
        this.currentPage = 1;
        
        // If requesting more items than we've loaded, fetch more from backend
        if (newItemsPerPage > this.currentLoadedLimit) {
            console.log(`⬆️ User requested ${newItemsPerPage} items but only have ${this.currentLoadedLimit} loaded. Fetching more...`);
            await this.loadQsos(newItemsPerPage);
        }
        
        this.applyFilters();
        this.renderTable();
    },
    
    /**
     * Export current filtered QSOs as CSV
     */
    exportAsCSV() {
        if (this.filteredQsos.length === 0) {
            alert('No QSOs to export');
            return;
        }
        
        // Create CSV header
        const headers = ['Date', 'Time', 'Callsign', 'Frequency', 'Band', 'Mode', 'RST Sent', 'RST Rcvd', 'DXCC', 'Awards', 'Name/QTH'];
        
        // Create CSV rows
        const rows = this.filteredQsos.map(qso => {
            const awards = [];
            if (qso.pota_ref) awards.push(qso.pota_ref);
            if (qso.sota_ref) awards.push(qso.sota_ref);
            if (qso.wwff_ref) awards.push(qso.wwff_ref);
            if (qso.iota) awards.push(qso.iota);
            
            return [
                this.formatDate(qso.qso_date),
                this.formatTime(qso.time_on),
                qso.call,
                this.formatFrequency(qso.frequency),
                qso.band || '-',
                qso.mode,
                qso.rst_sent,
                qso.rst_rcvd,
                qso.country || '-',
                awards.join(' / ') || '',
                qso.name || qso.qth || ''
            ];
        });
        
        // Escape CSV values
        const escapeCsvValue = (val) => {
            if (typeof val !== 'string') val = String(val);
            if (val.includes(',') || val.includes('"') || val.includes('\n')) {
                return `"${val.replace(/"/g, '""')}"`;
            }
            return val;
        };
        
        // Build CSV content
        let csv = headers.map(escapeCsvValue).join(',') + '\n';
        csv += rows.map(row => row.map(escapeCsvValue).join(',')).join('\n');
        
        // Download CSV
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `wavelog_contacts_${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
        
        console.log(`✅ Exported ${this.filteredQsos.length} QSOs to CSV`);
    }
};

// Expose module to window so it can be accessed from Vue and HTML event handlers
window.WavelogLogModal = WavelogLogModal;

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        WavelogLogModal.init();
    });
} else {
    WavelogLogModal.init();
}