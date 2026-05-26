// Local Log Modal - Display all logged QSOs in a beautiful table with filtering and pagination
// Shows latest contacts on top

console.log('✅ Loading local-log-modal.js module...');

const LocalLogModal = {
    // State management
    allQsos: [],
    filteredQsos: [],
    currentPage: 1,
    itemsPerPage: 10,
    filters: {
        callsign: '',
        mode: '',
        band: '',
        awards: '' // pota, sota, wwff, iota
    },
    sortField: 'qso_date',
    sortDirection: 'desc', // newest first
    
    /**
     * Initialize local log modal
     */
    init() {
        console.log('📋 Initializing Local Log Modal...');
        
        // Set up close button event listeners
        const closeBtn = document.querySelector('.local-log-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.hideModal();
            });
        }
        
        // Set up modal backdrop click handler
        const modal = document.querySelector('.local-log-modal');
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
            'filter-callsign': 'callsign',
            'filter-mode': 'mode',
            'filter-band': 'band',
            'filter-awards': 'awards'
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
     * Show the local log modal and load QSOs (fresh every time)
     */
    async showModal() {
        const modal = document.querySelector('.local-log-modal');
        if (!modal) return;
        
        // Show modal
        modal.style.display = 'flex';
        
        // Always reload QSOs to get latest data from file
        console.log('📋 Refreshing local QSO log...');
        await this.loadQsos();
        
        // Apply filters and render
        this.applyFilters();
        this.renderTable();
    },
    
    /**
     * Hide the local log modal
     */
    hideModal() {
        const modal = document.querySelector('.local-log-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    },
    
    /**
     * Load QSOs from the Wavelog read path.
     */
    async loadQsos() {
        try {
            console.log('⚡ Loading QSOs from Wavelog...');
            const startTime = performance.now();
            
            const response = await fetch('/api/wavelog-log/entries?limit=5000');
            if (response.ok) {
                const result = await response.json();
                if (result && result.success && Array.isArray(result.entries)) {
                    this.allQsos = window.WavelogQsoNormalizer.toLocalLogQsos(result.entries);
                    const elapsed = performance.now() - startTime;
                    console.log(`✅ Loaded ${this.allQsos.length} QSOs from Wavelog in ${elapsed.toFixed(2)}ms`);
                } else {
                    console.warn('⚠️ Unexpected API response format:', result);
                    this.allQsos = [];
                }
            } else {
                console.error(`❌ Failed to fetch Wavelog QSOs: ${response.statusText}`);
                this.allQsos = [];
            }
        } catch (error) {
            console.error('❌ Error loading Wavelog QSOs:', error);
            this.allQsos = [];
        }
    },
    
    /**
     * Apply filters to QSOs
     */
    applyFilters() {
        this.filteredQsos = this.allQsos.filter(qso => {
            // Filter by callsign (case-insensitive)
            if (this.filters.callsign && !(qso.call || '').toUpperCase().includes(this.filters.callsign)) {
                return false;
            }
            
            // Filter by mode (case-insensitive)
            if (this.filters.mode && (qso.mode || '').toUpperCase() !== this.filters.mode) {
                return false;
            }
            
            // Filter by band (case-insensitive)
            if (this.filters.band && (qso.band || '').toUpperCase() !== this.filters.band) {
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
        return freq.toFixed(3);
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
        const tableBody = document.querySelector('.local-log-table tbody');
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
                <td class="cell-dxcc">${qso.country || '-'}</td>
                <td class="cell-awards">${awardsText}</td>
                <td class="cell-name"><span class="name-qth-text" title="${qso.name || qso.qth || '-'}">${qso.name || qso.qth || '-'}</span></td>
            `;
        });
        
        this.updatePaginationInfo();
    },
    
    /**
     * Update pagination info display and button states
     */
    updatePaginationInfo() {
        const paginationInfo = document.querySelector('.local-log-pagination-info');
        if (!paginationInfo) return;
        
        const totalPages = Math.ceil(this.filteredQsos.length / this.itemsPerPage);
        const startItem = this.filteredQsos.length === 0 ? 0 : (this.currentPage - 1) * this.itemsPerPage + 1;
        const endItem = Math.min(this.currentPage * this.itemsPerPage, this.filteredQsos.length);
        
        paginationInfo.textContent = `Showing ${startItem}-${endItem} of ${this.filteredQsos.length} QSOs (Page ${this.currentPage}/${totalPages || 1})`;
        
        // Update button states
        const prevBtn = document.getElementById('btn-prev-page');
        const nextBtn = document.getElementById('btn-next-page');
        
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
     * Change items per page
     */
    setItemsPerPage(count) {
        this.itemsPerPage = parseInt(count);
        this.currentPage = 1;
        this.renderTable();
    },
    
    /**
     * Go to next page
     */
    nextPage() {
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
     * Export current filtered QSOs as CSV
     */
    exportAsCSV() {
        if (this.filteredQsos.length === 0) {
            alert('No QSOs to export');
            return;
        }
        
        // Create CSV header
        const headers = ['Date', 'Time', 'Callsign', 'Frequency', 'Band', 'Mode', 'RST Sent', 'RST Rcvd', 'DXCC', 'Awards', 'Name/QTH', 'Comment'];
        
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
                qso.name || qso.qth || '',
                qso.comment || ''
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
        a.download = `qso_log_${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
        
        console.log(`✅ Exported ${this.filteredQsos.length} QSOs to CSV`);
    }
};

// Expose module to window so it can be accessed from Vue and HTML event handlers
window.LocalLogModal = LocalLogModal;

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        LocalLogModal.init();
    });
} else {
    LocalLogModal.init();
}
