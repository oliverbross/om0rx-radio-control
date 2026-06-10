// Standalone DX spots and filters entry point.

(async function bootstrapSpotsWindow() {
    const templateTarget = document.getElementById('dx-spots-section');
    const partialCache = new Map();
    const popoutStateStorageKey = 'om0rx.spots.popoutState';
    const popoutCommandStorageKey = 'om0rx.spots.popoutCommand';
    const popoutCommandChannelName = 'om0rx-spots-popout-command';

    function clone(value) {
        return JSON.parse(JSON.stringify(value || {}));
    }

    async function resolveTemplateIncludes(html) {
        const includePattern = /<!--\s*@include\s+([^>]+?)\s*-->/g;
        const includes = [...html.matchAll(includePattern)];
        if (includes.length === 0) return html;

        const partials = await Promise.all(includes.map(match => {
            const partialPath = match[1].trim();
            if (partialCache.has(partialPath)) return partialCache.get(partialPath);
            const promise = fetch(partialPath, { cache: 'no-store' })
                .then(response => {
                    if (!response.ok) throw new Error(`HTTP ${response.status} loading ${partialPath}`);
                    return response.text();
                })
                .then(partialHtml => partialHtml.trim());
            partialCache.set(partialPath, promise);
            return promise;
        }));

        let resolved = html;
        includes.forEach((match, index) => {
            resolved = resolved.replace(match[0], partials[index]);
        });
        return resolveTemplateIncludes(resolved);
    }

    async function loadTemplate() {
        const response = await fetch('templates/dx-spots.html?v=20260604-filters-popout-44', {
            cache: 'no-store',
        });
        if (!response.ok) {
            throw new Error(`Failed to load filters template: HTTP ${response.status}`);
        }
        templateTarget.innerHTML = await resolveTemplateIncludes(await response.text());
    }

    await loadTemplate();

    const { createApp } = Vue;
    const app = createApp({
        data() {
            return {
                ...clone(window.FlexRadioSpots ? window.FlexRadioSpots.data : {}),
                viewMode: 'spots',
                logEntries: [],
                logLimit: 100,
                availableLogLimits: [50, 100, 250, 500],
                logFilters: {},
                configData: {},
                statusMessage: null,
                serviceHealth: null,
                spotsFilterDebounceTimer: null,
                standaloneWs: null,
                standaloneCommandChannel: null,
                standaloneRefreshTimer: null,
                mainSnapshotTimer: null,
                lastMainSnapshotAt: 0,
                standaloneBootStarted: false,
                standaloneUsingDatabaseResults: false,
                standaloneRenderTick: 0,
                standaloneVisibleSpots: [],
                standalonePendingSpots: [],
                standaloneSpotFlushTimer: null,
                standaloneClickBridgeBound: false,
                standaloneDropdownFallbackBound: false,
                lastStandaloneResultSignature: '',
                loggingPanelSectionCollapsed: true,
                suppressCallsignLookup: false,
                rotorEnabled: false,
                rotorAutoEnabled: false,
                loggingForm: {
                    callsign: '',
                    frequency: '',
                    band: '',
                    mode: '',
                    time_off: '',
                    rst_sent: '599',
                    rst_received: '599',
                    notes: '',
                    pota: '',
                    sota: '',
                    iota: '',
                    wwff: '',
                },
                radioStatus: {
                    frequency: 14.074,
                    mode: 'DIGU',
                },
                clusterStatus: {
                    connected: false,
                    activeName: '',
                    host: '',
                    port: '',
                },
            };
        },
        computed: {
            ...(window.FlexRadioSpots ? window.FlexRadioSpots.computed : {}),

            filteredSpots() {
                this.standaloneRenderTick;
                if (Array.isArray(this.standaloneVisibleSpots) && this.standaloneVisibleSpots.length > 0) {
                    return this.standaloneVisibleSpots.slice(0, this.maxSpots);
                }
                return [];
            },
        },
        watch: {
            spotsFilter: {
                handler() {
                    if (this.spotsFilterDebounceTimer) {
                        clearTimeout(this.spotsFilterDebounceTimer);
                    }
                    this.spotsFilterDebounceTimer = setTimeout(() => {
                        this.standaloneUsingDatabaseResults = false;
                        this.lastStandaloneResultSignature = '';
                        this.updateStandaloneVisibleSpots();
                        this.loadStandaloneFilteredSearch();
                    }, 300);
                },
                deep: true,
            },
            maxSpots() {
                this.standaloneUsingDatabaseResults = false;
                this.lastStandaloneResultSignature = '';
                this.updateStandaloneVisibleSpots();
                this.loadStandaloneFilteredSearch();
            },
            rblAlertRules: {
                handler() {
                    this.saveRblAlertRules();
                    this.evaluateRblAlertsForVisibleSpots();
                },
                deep: true,
            },
        },
        methods: {
            ...(window.FlexRadioSpots ? window.FlexRadioSpots.methods : {}),

            switchViewMode(mode) {
                this.viewMode = mode === 'visual' ? 'visual' : 'spots';
                if (this.viewMode === 'visual') {
                    this.$nextTick(() => this.queueVisualGlobeDraw());
                }
            },

            showStatus(message, type = 'info') {
                this.statusMessage = { message, type };
                setTimeout(() => {
                    if (this.statusMessage && this.statusMessage.message === message) {
                        this.statusMessage = null;
                    }
                }, 4000);
            },

            formatFrequencyForDisplay(freqMhz) {
                const value = Number(freqMhz || 0);
                return Number.isFinite(value) ? value.toFixed(6) : '';
            },

            formatSpotTime(timestamp) {
                const value = Number(timestamp || 0);
                if (!Number.isFinite(value) || value <= 0) return '';
                const date = new Date(value * 1000);
                return date.toLocaleString('en-GB', {
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false,
                });
            },

            async sendCommand(endpoint, payload) {
                const response = await fetch(`/api/${endpoint}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!response.ok) {
                    const error = await response.json().catch(() => ({}));
                    throw new Error(error.detail || error.message || 'Command failed');
                }
                return response.json();
            },

            async sendStandaloneSpotCommand(action, spot) {
                const command = {
                    id: `${Date.now()}:${Math.random().toString(36).slice(2)}`,
                    type: 'spot-action',
                    action,
                    spot: { ...(spot || {}) },
                };

                try {
                    if (action === 'tune') {
                        const freqMhz = this.normalizeSpotFrequencyMhz(spot);
                        const radioMode = this.getRadioModeForSpot(spot, freqMhz);
                        if (freqMhz && radioMode) {
                            this.sendImmediateSpotTune(freqMhz, radioMode, spot);
                        }
                    }
                } catch (error) {
                    console.warn('Could not tune directly from detached filters window:', error);
                }

                try {
                    if (!this.standaloneCommandChannel && 'BroadcastChannel' in window) {
                        this.standaloneCommandChannel = new BroadcastChannel(popoutCommandChannelName);
                    }
                    if (this.standaloneCommandChannel) {
                        this.standaloneCommandChannel.postMessage(command);
                    }
                } catch (error) {
                    console.warn('Could not send filters command through BroadcastChannel:', error);
                }

                try {
                    window.localStorage.setItem(popoutCommandStorageKey, JSON.stringify(command));
                } catch (error) {
                    console.warn('Could not send filters command through localStorage:', error);
                }

                fetch('/api/spots/popout-command', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(command),
                }).catch(error => {
                    console.warn('Could not send filters command through backend relay:', error);
                });

                this.showStatus(`Sent ${spot.callsign || 'spot'} to main window`, 'success');
            },

            tuneToSpot(spot) {
                this.sendStandaloneSpotCommand('tune', spot);
            },

            showSpotDetails(spot, event) {
                if (event) event.stopPropagation();
                this.sendStandaloneSpotCommand('details', spot);
            },

            applyStandaloneSourceSelection(sources) {
                this.spotsFilter.spotSources = sources;
                this.clearRblSpotFilters();
                this.lastStandaloneResultSignature = '';
                this.updateStandaloneVisibleSpots();
                this.loadStandaloneFilteredSearch();
            },

            showOnlyRblSpots() {
                this.applyStandaloneSourceSelection(['rbl']);
            },

            showOnlyClusterSpots() {
                this.applyStandaloneSourceSelection(['cluster']);
            },

            showAllSpotSources() {
                this.applyStandaloneSourceSelection(['cluster', 'rbl']);
            },

            setupStandaloneClickBridge() {
                if (this.standaloneClickBridgeBound) return;
                this.standaloneClickBridgeBound = true;

                document.addEventListener('click', event => {
                    const sourceButton = event.target.closest('.source-diagnostics-strip .rbl-monitor-action');
                    if (sourceButton) {
                        const label = sourceButton.textContent.trim();
                        if (label === 'Cluster only') {
                            event.preventDefault();
                            event.stopPropagation();
                            this.showOnlyClusterSpots();
                            return;
                        }
                        if (label === 'RBL only') {
                            event.preventDefault();
                            event.stopPropagation();
                            this.showOnlyRblSpots();
                            return;
                        }
                        if (label === 'All sources') {
                            event.preventDefault();
                            event.stopPropagation();
                            this.showAllSpotSources();
                            return;
                        }
                        if (label === 'Mute cluster') {
                            event.preventDefault();
                            event.stopPropagation();
                            this.toggleSpotSourceMute('cluster');
                            this.updateStandaloneVisibleSpots();
                            return;
                        }
                        if (label === 'Mute RBL') {
                            event.preventDefault();
                            event.stopPropagation();
                            this.toggleSpotSourceMute('rbl');
                            this.updateStandaloneVisibleSpots();
                            return;
                        }
                    }

                    const row = event.target.closest('.spots-table tbody tr.spot-row');
                    if (!row) return;
                    const rows = Array.from(row.parentElement.querySelectorAll('tr.spot-row'));
                    const index = rows.indexOf(row);
                    const spot = (this.filteredSpots || this.standaloneVisibleSpots || [])[index];
                    if (!spot) return;

                    event.preventDefault();
                    event.stopPropagation();
                    if (event.target.closest('button')) {
                        this.showSpotDetails(spot, event);
                    } else {
                        this.tuneToSpot(spot);
                    }
                }, true);
            },

            clearLoggingForm() {
                Object.assign(this.loggingForm, {
                    callsign: '',
                    frequency: '',
                    band: '',
                    mode: '',
                    time_off: '',
                    notes: '',
                    pota: '',
                    sota: '',
                    iota: '',
                    wwff: '',
                });
            },

            autoPopulateRST() {
                const mode = String(this.loggingForm.mode || '').toUpperCase();
                const rst = ['FT8', 'FT4', 'FT2'].includes(mode) ? '59' : '599';
                this.loggingForm.rst_sent = rst;
                this.loggingForm.rst_received = rst;
            },

            async loadStandaloneConfig() {
                try {
                    const response = await fetch('/api/config');
                    const data = await response.json();
                    if (response.ok && data.success && data.config) {
                        this.configData = data.config;
                    }
                } catch (error) {
                    console.warn('Could not load filters window config:', error);
                }
            },

            async loadStandaloneServiceHealth() {
                try {
                    const response = await fetch('/api/health/services');
                    const data = await response.json();
                    if (response.ok) {
                        this.serviceHealth = data;
                    }
                } catch (error) {
                    this.serviceHealth = null;
                }
            },

            serviceHealthPillTitle(service) {
                if (!service) return '';
                return [service.label, service.value, service.detail].filter(Boolean).join(' - ');
            },

            getDatastoreService() {
                const services = this.serviceHealth && Array.isArray(this.serviceHealth.services)
                    ? this.serviceHealth.services
                    : [];
                return services.find(service => service.id === 'datastore') || null;
            },

            getDatastoreBadgeText() {
                const service = this.getDatastoreService();
                return service && service.value ? service.value : '';
            },

            getDatastoreBadgeTitle() {
                const service = this.getDatastoreService();
                if (!service) return 'Database backend status is loading';
                return this.serviceHealthPillTitle(service);
            },

            getSpotFilterSnapshotKey(filter) {
                const value = filter || {};
                return JSON.stringify({
                    callsign: value.callsign || '',
                    bands: value.bands || [],
                    modes: value.modes || [],
                    continents: value.continents || [],
                    cqs: value.cqs || [],
                    callStatuses: value.callStatuses || [],
                    dxccStatuses: value.dxccStatuses || [],
                    specials: value.specials || [],
                    spotSources: value.spotSources || [],
                    rblModes: value.rblModes || [],
                    rblMinSnr: value.rblMinSnr || '',
                    rblDedupeMinutes: Number(value.rblDedupeMinutes || 0),
                    sortBy: value.sortBy || 'time',
                    workedB4Include: Boolean(value.workedB4Include),
                    workedB4Exclude: Boolean(value.workedB4Exclude),
                });
            },

            loadSpotsPopoutState(options = {}) {
                const includeControls = options.includeControls !== false;
                try {
                    const raw = window.localStorage.getItem(popoutStateStorageKey);
                    if (!raw) return;
                    const state = JSON.parse(raw);
                    const savedAt = Number(state.savedAt || 0);
                    if (!includeControls && savedAt && savedAt <= this.lastMainSnapshotAt) {
                        return;
                    }

                    const currentFilterKey = this.getSpotFilterSnapshotKey(this.spotsFilter);
                    const snapshotFilterKey = this.getSpotFilterSnapshotKey(state.spotsFilter);

                    if (includeControls && state.spotsFilter && typeof state.spotsFilter === 'object') {
                        this.spotsFilter = {
                            ...this.spotsFilter,
                            ...state.spotsFilter,
                            bands: Array.isArray(state.spotsFilter.bands) ? state.spotsFilter.bands : [],
                            modes: Array.isArray(state.spotsFilter.modes) ? state.spotsFilter.modes : [],
                            continents: Array.isArray(state.spotsFilter.continents) ? state.spotsFilter.continents : [],
                            cqs: Array.isArray(state.spotsFilter.cqs) ? state.spotsFilter.cqs : [],
                            callStatuses: Array.isArray(state.spotsFilter.callStatuses) ? state.spotsFilter.callStatuses : [],
                            dxccStatuses: Array.isArray(state.spotsFilter.dxccStatuses) ? state.spotsFilter.dxccStatuses : [],
                            specials: Array.isArray(state.spotsFilter.specials) ? state.spotsFilter.specials : [],
                            spotSources: Array.isArray(state.spotsFilter.spotSources) ? state.spotsFilter.spotSources : ['cluster'],
                            rblModes: Array.isArray(state.spotsFilter.rblModes) ? state.spotsFilter.rblModes : [],
                        };
                    }
                    if (includeControls && Number(state.maxSpots) > 0) {
                        this.maxSpots = Number(state.maxSpots);
                    }
                    if (includeControls) {
                        this.viewMode = state.viewMode === 'visual' ? 'visual' : 'spots';
                    }

                    if (includeControls && Array.isArray(state.dxSpots)) {
                        this.mergeStandaloneSpots(state.dxSpots);
                    }

                    if (Array.isArray(state.filteredSearchResults) && (includeControls || currentFilterKey === snapshotFilterKey)) {
                        this.filteredSearchResults = state.filteredSearchResults.map(spot => ({ ...spot }));
                    }

                    if (state.spotSourceStats) {
                        this.spotSourceStats = state.spotSourceStats;
                    }

                    if (state.clusterStatus) {
                        this.clusterStatus = {
                            ...this.clusterStatus,
                            ...state.clusterStatus,
                        };
                    }

                    if (state.clusterConnected || (state.dxSpots || []).some(spot => (spot.spot_source || 'cluster') === 'cluster')) {
                        this.clusterConnected = true;
                    }

                    this.lastMainSnapshotAt = Math.max(this.lastMainSnapshotAt, savedAt);
                } catch (error) {
                    console.warn('Could not load filters pop-out state:', error);
                }
            },

            startMainSnapshotSync() {
                this.stopMainSnapshotSync();
                this.mainSnapshotTimer = setInterval(() => {
                    this.loadSpotsPopoutState({ includeControls: false });
                }, 2500);
            },

            stopMainSnapshotSync() {
                if (this.mainSnapshotTimer) {
                    clearInterval(this.mainSnapshotTimer);
                    this.mainSnapshotTimer = null;
                }
            },

            connectStandaloneSpotSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const url = `${protocol}//${window.location.host}/ws/radio`;
                this.standaloneWs = new WebSocket(url);

                this.standaloneWs.onopen = () => {
                    this.clusterConnected = true;
                };

                this.standaloneWs.onmessage = event => {
                    const message = JSON.parse(event.data);
                    if (message.type === 'status') {
                        this.clusterConnected = Boolean(message.data && message.data.cluster_connected);
                        if (message.data && message.data.cluster_info) {
                            this.clusterStatus = {
                                ...this.clusterStatus,
                                ...message.data.cluster_info,
                                connected: this.clusterConnected,
                            };
                        }
                        return;
                    }
                    if (message.type !== 'spots' || !Array.isArray(message.data)) return;
                    this.queueStandaloneSpots(message.data);
                };

                this.standaloneWs.onclose = () => {
                    this.updateStandaloneClusterStateFromStats();
                    setTimeout(() => this.connectStandaloneSpotSocket(), 5000);
                };
            },

            queueStandaloneSpots(spots) {
                if (!Array.isArray(spots) || spots.length === 0) return;
                this.standalonePendingSpots.push(...spots);
                if (this.standaloneSpotFlushTimer) return;
                this.standaloneSpotFlushTimer = setTimeout(() => {
                    const pending = this.standalonePendingSpots.splice(0);
                    this.standaloneSpotFlushTimer = null;
                    this.mergeStandaloneSpots(pending, { preserveScroll: true });
                }, 600);
            },

            mergeStandaloneSpots(spots, options = {}) {
                if (!Array.isArray(spots) || spots.length === 0) return;

                let sawCluster = false;
                spots.forEach(newSpot => {
                    if ((newSpot.spot_source || 'cluster') === 'cluster') {
                        sawCluster = true;
                    }

                    const index = this.findExistingSpotIndex(newSpot, this.dxSpots);
                    if (index >= 0) {
                        Object.assign(this.dxSpots[index], this.mergeSpotAggregate(this.dxSpots[index], newSpot));
                        this.evaluateRblSpotAlert(this.dxSpots[index]);
                        if (index !== 0) {
                            const [spot] = this.dxSpots.splice(index, 1);
                            this.dxSpots.unshift(spot);
                        }
                    } else {
                        this.evaluateRblSpotAlert(newSpot);
                        this.dxSpots.unshift(newSpot);
                    }
                });

                if (sawCluster) {
                    this.clusterConnected = true;
                    this.clusterStatus = {
                        ...this.clusterStatus,
                        connected: true,
                    };
                }

                const limit = Math.max(500, Number(this.maxSpots || 100));
                this.dxSpots = this.sortVisibleSpots(this.dxSpots).slice(0, limit);
                this.updateStandaloneVisibleSpots(options);
            },

            getStandaloneFilteredSpots(sourceSpots) {
                let filtered = Array.isArray(sourceSpots) ? sourceSpots.slice() : [];
                const filter = this.spotsFilter || {};

                if (filter.callsign) {
                    const searchTerm = String(filter.callsign).toLowerCase();
                    filtered = filtered.filter(spot => String(spot.callsign || '').toLowerCase().includes(searchTerm));
                }
                if (Array.isArray(filter.bands) && filter.bands.length > 0) {
                    filtered = filtered.filter(spot => filter.bands.includes(spot.band));
                }
                if (Array.isArray(filter.modes) && filter.modes.length > 0) {
                    filtered = filtered.filter(spot => filter.modes.includes(spot.mode));
                }
                if (Array.isArray(filter.continents) && filter.continents.length > 0) {
                    filtered = filtered.filter(spot => filter.continents.includes(spot.spotter_continent));
                }
                if (Array.isArray(filter.cqs) && filter.cqs.length > 0) {
                    const cqStrings = filter.cqs.map(cq => String(cq));
                    filtered = filtered.filter(spot => cqStrings.includes(String(spot.cq)));
                }
                if (Array.isArray(filter.callStatuses) && filter.callStatuses.length > 0) {
                    filtered = filtered.filter(spot => filter.callStatuses.includes(spot.call_status));
                }
                if (Array.isArray(filter.dxccStatuses) && filter.dxccStatuses.length > 0) {
                    filtered = filtered.filter(spot => filter.dxccStatuses.includes(spot.tag || spot.dxcc_status));
                }
                if (Array.isArray(filter.specials) && filter.specials.length > 0) {
                    filtered = filtered.filter(spot => {
                        if (!spot.special) return false;
                        return filter.specials.some(special => spot.special.includes(special));
                    });
                }

                filtered = this.applySourceAndRblFilters(filtered);

                if (filter.workedB4Include || filter.workedB4Exclude) {
                    filtered = filtered.filter(spot => {
                        const isWorked = !!this.getWorkedDate(spot.callsign, spot.band, spot.mode);
                        if (filter.workedB4Include && filter.workedB4Exclude) return true;
                        if (filter.workedB4Include) return isWorked;
                        if (filter.workedB4Exclude) return !isWorked;
                        return true;
                    });
                }

                filtered = this.filterRblNoise(filtered);
                return this.sortVisibleSpots(filtered).slice(0, this.maxSpots);
            },

            escapeStandaloneHtml(value) {
                return String(value ?? '')
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
            },

            getStandaloneBandItems(spots) {
                const bands = new Map();
                (spots || []).forEach(spot => {
                    const band = spot.band || 'Unknown';
                    const item = bands.get(band) || { band, total: 0, topScore: 0, rbl: 0 };
                    item.total += 1;
                    item.topScore = Math.max(item.topScore, Number(this.getSpotScore(spot) || 0));
                    if ((spot.spot_source || 'cluster') === 'rbl') item.rbl += 1;
                    bands.set(band, item);
                });
                return Array.from(bands.values()).sort((a, b) => b.total - a.total);
            },

            getStandaloneDropdownNameFromButton(button) {
                const label = (button && button.textContent ? button.textContent : '').replace(/\s+/g, ' ').trim();
                if (!label) return '';
                if (label.includes('Show:')) return 'spotCount';
                if (label.includes('Bands')) return 'bands';
                if (label.includes('Modes')) return 'modes';
                if (label.includes('Spotter from')) return 'continents';
                if (label.includes('Zones')) return 'zones';
                if (label.includes('Call Status')) return 'callStatus';
                if (label.includes('DXCC Status')) return 'dxccStatus';
                if (label.includes('Special')) return 'special';
                if (label.includes('Worked b4')) return 'workedB4';
                if (label.startsWith('Presets')) return 'presets';
                if (label.includes('Sort:') || label.startsWith('Sort')) return 'sort';
                if (label === 'RBL ▼' || label === 'RBL') return 'rbl';
                if (label.startsWith('Rows')) return 'spotRows';
                return '';
            },

            closeStandaloneDropdownMenu() {
                document.querySelectorAll('.standalone-filter-menu').forEach(menu => menu.remove());
            },

            positionStandaloneDropdownMenu(menu, button) {
                const rect = button.getBoundingClientRect();
                menu.style.position = 'fixed';
                menu.style.left = `${Math.max(8, rect.left)}px`;
                menu.style.top = `${rect.bottom + 4}px`;
                menu.style.zIndex = '100000';
                menu.style.maxHeight = `${Math.max(180, window.innerHeight - rect.bottom - 18)}px`;
                menu.style.overflow = 'auto';
                document.body.appendChild(menu);

                const menuRect = menu.getBoundingClientRect();
                if (menuRect.right > window.innerWidth - 8) {
                    menu.style.left = `${Math.max(8, window.innerWidth - menuRect.width - 8)}px`;
                }
                if (menuRect.bottom > window.innerHeight - 8 && rect.top > menuRect.height + 12) {
                    menu.style.top = `${Math.max(8, rect.top - menuRect.height - 4)}px`;
                }
            },

            buildStandaloneOptionList(items, selected, options = {}) {
                const selectedValues = Array.isArray(selected)
                    ? selected
                    : (selected === undefined || selected === null ? [] : [selected]);
                const selectedSet = new Set(selectedValues.map(value => String(value)));
                const type = options.type || 'checkbox';
                const filter = options.filter || '';
                const name = options.name || filter || 'standalone-filter';
                return (items || []).map(item => {
                    const value = String(options.value ? options.value(item) : item);
                    const label = String(options.label ? options.label(item) : item);
                    const checked = type === 'radio'
                        ? String(selected || '') === value
                        : selectedSet.has(value);
                    return `
                        <label>
                            <input
                                type="${type}"
                                ${type === 'radio' ? `name="${this.escapeStandaloneHtml(name)}"` : ''}
                                data-filter="${this.escapeStandaloneHtml(filter)}"
                                value="${this.escapeStandaloneHtml(value)}"
                                ${checked ? 'checked' : ''}>
                            ${this.escapeStandaloneHtml(label)}
                        </label>
                    `;
                }).join('');
            },

            getStandaloneDropdownButtonHtml(label, action, extraAttrs = '') {
                return `<button type="button" data-action="${this.escapeStandaloneHtml(action)}" ${extraAttrs}>${this.escapeStandaloneHtml(label)}</button>`;
            },

            getStandaloneDropdownHtml(name) {
                switch (name) {
                    case 'spotCount':
                        return `<div class="dropdown-list">${this.buildStandaloneOptionList(this.availableSpotCounts, String(this.maxSpots), { type: 'radio', filter: 'maxSpots', name: 'standaloneSpotCount' })}</div>`;
                    case 'bands':
                        return `
                            <div class="dropdown-grid two-cols">${this.buildStandaloneOptionList(this.availableBands, this.spotsFilter.bands, { filter: 'bands' })}</div>
                            <div class="dropdown-footer">${this.getStandaloneDropdownButtonHtml('All', 'all', 'data-filter="bands"')}${this.getStandaloneDropdownButtonHtml('Clear', 'clear', 'data-filter="bands"')}</div>
                        `;
                    case 'modes':
                        return `
                            <div class="dropdown-list">${this.buildStandaloneOptionList(this.availableModes, this.spotsFilter.modes, { filter: 'modes' })}</div>
                            <div class="dropdown-footer">${this.getStandaloneDropdownButtonHtml('All', 'all', 'data-filter="modes"')}${this.getStandaloneDropdownButtonHtml('Clear', 'clear', 'data-filter="modes"')}</div>
                        `;
                    case 'continents':
                        return `
                            <div class="dropdown-list">${this.buildStandaloneOptionList(this.availableContinents, this.spotsFilter.continents, { filter: 'continents', value: item => item.id, label: item => item.name })}</div>
                            <div class="dropdown-footer">${this.getStandaloneDropdownButtonHtml('All', 'all', 'data-filter="continents"')}${this.getStandaloneDropdownButtonHtml('Clear', 'clear', 'data-filter="continents"')}</div>
                        `;
                    case 'zones':
                        return `
                            <div class="dropdown-grid three-cols">${this.buildStandaloneOptionList(this.availableCQs, this.spotsFilter.cqs, { filter: 'cqs', label: item => `Zone ${item}` })}</div>
                            <div class="dropdown-footer">${this.getStandaloneDropdownButtonHtml('All', 'all', 'data-filter="cqs"')}${this.getStandaloneDropdownButtonHtml('Clear', 'clear', 'data-filter="cqs"')}</div>
                        `;
                    case 'callStatus':
                        return `
                            <div class="dropdown-list">${this.buildStandaloneOptionList(this.availableCallStatuses, this.spotsFilter.callStatuses, { filter: 'callStatuses' })}</div>
                            <div class="dropdown-footer">${this.getStandaloneDropdownButtonHtml('All', 'all', 'data-filter="callStatuses"')}${this.getStandaloneDropdownButtonHtml('Clear', 'clear', 'data-filter="callStatuses"')}</div>
                        `;
                    case 'dxccStatus':
                        return `
                            <div class="dropdown-list">${this.buildStandaloneOptionList(this.availableDxccStatuses, this.spotsFilter.dxccStatuses, { filter: 'dxccStatuses' })}</div>
                            <div class="dropdown-footer">${this.getStandaloneDropdownButtonHtml('All', 'all', 'data-filter="dxccStatuses"')}${this.getStandaloneDropdownButtonHtml('Clear', 'clear', 'data-filter="dxccStatuses"')}</div>
                        `;
                    case 'special':
                        return `
                            <div class="dropdown-list">${this.buildStandaloneOptionList(this.availableSpecials, this.spotsFilter.specials, { filter: 'specials' })}</div>
                            <div class="dropdown-footer">${this.getStandaloneDropdownButtonHtml('All', 'all', 'data-filter="specials"')}${this.getStandaloneDropdownButtonHtml('Clear', 'clear', 'data-filter="specials"')}</div>
                        `;
                    case 'workedB4':
                        return `
                            <div class="dropdown-list">
                                <label><input type="checkbox" data-filter="workedB4Include" ${this.spotsFilter.workedB4Include ? 'checked' : ''}> Include Worked</label>
                                <label><input type="checkbox" data-filter="workedB4Exclude" ${this.spotsFilter.workedB4Exclude ? 'checked' : ''}> Exclude Worked</label>
                            </div>
                        `;
                    case 'presets':
                        return `<div class="dropdown-list">${(this.availableSpotPresets || [
                            { id: 'dx', name: 'DX Focus' },
                            { id: 'digital', name: 'Digital' },
                            { id: 'new-dxcc', name: 'New DXCC' },
                            { id: 'worked', name: 'Worked' },
                        ]).map(preset => `<button type="button" class="spot-preset-btn" data-preset="${this.escapeStandaloneHtml(preset.id)}">${this.escapeStandaloneHtml(preset.name)}</button>`).join('')}</div>`;
                    case 'sort':
                        return `<div class="dropdown-list">${this.buildStandaloneOptionList(this.availableSpotSorts || [
                            { id: 'time', name: 'Newest' },
                            { id: 'score', name: 'Best' },
                        ], this.spotsFilter.sortBy, { type: 'radio', filter: 'sortBy', name: 'standaloneSpotSort', value: item => item.id, label: item => item.name })}</div>`;
                    case 'rbl':
                        return `
                            <div class="dropdown-list">
                                ${(this.availableSpotSources || []).map(source => `
                                    <label>
                                        <input type="checkbox" data-filter="spotSources" value="${this.escapeStandaloneHtml(source.id)}" ${this.spotsFilter.spotSources.includes(source.id) ? 'checked' : ''}>
                                        Show ${this.escapeStandaloneHtml(source.name)}
                                    </label>
                                `).join('')}
                            </div>
                            <div class="dropdown-list rbl-dropdown-section">${this.buildStandaloneOptionList(this.availableRblModes, this.spotsFilter.rblModes, { filter: 'rblModes', label: item => `RBL ${item}` })}</div>
                            <div class="dropdown-list rbl-dropdown-section">
                                <label class="rbl-number-control">Min dB <input type="number" min="-30" max="60" step="1" data-number-filter="rblMinSnr" value="${this.escapeStandaloneHtml(this.spotsFilter.rblMinSnr)}"></label>
                                <label class="rbl-number-control">Dedupe min <input type="number" min="0" max="120" step="1" data-number-filter="rblDedupeMinutes" value="${this.escapeStandaloneHtml(this.spotsFilter.rblDedupeMinutes)}"></label>
                            </div>
                            <div class="dropdown-footer">${this.getStandaloneDropdownButtonHtml('RBL only', 'rbl-only')}${this.getStandaloneDropdownButtonHtml('Normal only', 'cluster-only')}${this.getStandaloneDropdownButtonHtml('All', 'all-sources')}</div>
                        `;
                    case 'spotRows': {
                        const items = this.getSpotSectionVisibilityItems();
                        return `
                            <div class="dropdown-list">
                                ${items.map(item => `<label><input type="checkbox" data-section-id="${this.escapeStandaloneHtml(item.id)}" ${this.isSpotSectionVisible(item.id) ? 'checked' : ''}> ${this.escapeStandaloneHtml(item.label)}</label>`).join('')}
                            </div>
                            <div class="dropdown-footer">${this.getStandaloneDropdownButtonHtml('Show all', 'show-all-rows')}</div>
                        `;
                    }
                    default:
                        return '';
                }
            },

            getStandaloneFilterArray(filterName) {
                const map = {
                    bands: this.spotsFilter.bands,
                    modes: this.spotsFilter.modes,
                    continents: this.spotsFilter.continents,
                    cqs: this.spotsFilter.cqs,
                    callStatuses: this.spotsFilter.callStatuses,
                    dxccStatuses: this.spotsFilter.dxccStatuses,
                    specials: this.spotsFilter.specials,
                    spotSources: this.spotsFilter.spotSources,
                    rblModes: this.spotsFilter.rblModes,
                };
                return map[filterName] || null;
            },

            getStandaloneAllValues(filterName) {
                const map = {
                    bands: this.availableBands,
                    modes: this.availableModes,
                    continents: (this.availableContinents || []).map(item => item.id),
                    cqs: this.availableCQs,
                    callStatuses: this.availableCallStatuses,
                    dxccStatuses: this.availableDxccStatuses,
                    specials: this.availableSpecials,
                    spotSources: (this.availableSpotSources || []).map(item => item.id),
                    rblModes: this.availableRblModes,
                };
                return map[filterName] || [];
            },

            markStandaloneFiltersChanged() {
                this.standaloneUsingDatabaseResults = false;
                this.lastStandaloneResultSignature = '';
                this.updateStandaloneVisibleSpots({ preserveScroll: true });
                this.updateStandaloneFilterButtonStates();
                this.loadStandaloneFilteredSearch();
            },

            updateStandaloneFilterButtonStates() {
                document.querySelectorAll('.filter-dropdown > .filter-btn').forEach(button => {
                    const name = this.getStandaloneDropdownNameFromButton(button);
                    if (name === 'spotCount') {
                        button.textContent = `📊 Show: ${Number(this.maxSpots || 100)} ▼`;
                    } else if (name === 'sort') {
                        const sort = (this.availableSpotSorts || []).find(item => item.id === this.spotsFilter.sortBy);
                        button.textContent = `Sort: ${sort ? sort.name : 'Newest'} ▼`;
                    }
                    const active = name && typeof this.isFilterActive === 'function' && this.isFilterActive(name);
                    button.classList.toggle('active', Boolean(active));
                });
            },

            applyStandaloneDropdownFilterChange(input) {
                const filterName = input.getAttribute('data-filter');
                if (filterName === 'maxSpots') {
                    this.maxSpots = Number(input.value || 100);
                    this.markStandaloneFiltersChanged();
                    return;
                }
                if (filterName === 'sortBy') {
                    this.spotsFilter.sortBy = input.value || 'time';
                    this.markStandaloneFiltersChanged();
                    return;
                }
                if (filterName === 'workedB4Include' || filterName === 'workedB4Exclude') {
                    this.spotsFilter[filterName] = input.checked;
                    this.markStandaloneFiltersChanged();
                    return;
                }

                const target = this.getStandaloneFilterArray(filterName);
                if (!target) return;
                const value = filterName === 'cqs' ? Number(input.value) : input.value;
                const index = target.findIndex(item => String(item) === String(value));
                if (input.checked && index === -1) {
                    target.push(value);
                } else if (!input.checked && index !== -1) {
                    target.splice(index, 1);
                }
                this.markStandaloneFiltersChanged();
            },

            openStandaloneDropdownMenu(name, button, options = {}) {
                const existing = document.querySelector(`.standalone-filter-menu[data-dropdown-name="${name}"]`);
                this.closeStandaloneDropdownMenu();
                this.openDropdown = null;
                if (existing && !options.force) return;

                const html = this.getStandaloneDropdownHtml(name);
                if (!html) return;

                const menu = document.createElement('div');
                menu.className = `dropdown-menu standalone-filter-menu standalone-filter-menu-${name}`;
                menu.setAttribute('data-dropdown-name', name);
                menu.innerHTML = html;
                this.positionStandaloneDropdownMenu(menu, button);

                menu.addEventListener('click', event => {
                    event.stopPropagation();
                    const actionButton = event.target.closest('button[data-action], button[data-preset]');
                    if (!actionButton) return;
                    event.preventDefault();

                    const preset = actionButton.getAttribute('data-preset');
                    if (preset) {
                        this.applySpotPreset(preset);
                        this.markStandaloneFiltersChanged();
                        this.closeStandaloneDropdownMenu();
                        return;
                    }

                    const action = actionButton.getAttribute('data-action');
                    const filter = actionButton.getAttribute('data-filter');
                    if (action === 'all' && filter) {
                        const target = this.getStandaloneFilterArray(filter);
                        if (target) target.splice(0, target.length, ...this.getStandaloneAllValues(filter));
                        this.markStandaloneFiltersChanged();
                    } else if (action === 'clear' && filter) {
                        const target = this.getStandaloneFilterArray(filter);
                        if (target) target.splice(0, target.length);
                        this.markStandaloneFiltersChanged();
                    } else if (action === 'rbl-only') {
                        this.showOnlyRblSpots();
                    } else if (action === 'cluster-only') {
                        this.showOnlyClusterSpots();
                    } else if (action === 'all-sources') {
                        this.showAllSpotSources();
                    } else if (action === 'show-all-rows') {
                        this.showAllSpotSections();
                        this.renderStandaloneFallbackUi();
                    }
                    this.openStandaloneDropdownMenu(name, button, { force: true });
                });

                menu.addEventListener('change', event => {
                    event.stopPropagation();
                    const input = event.target.closest('input');
                    if (!input) return;

                    const sectionId = input.getAttribute('data-section-id');
                    if (sectionId) {
                        const next = {
                            ...getDefaultSpotSectionVisibility(),
                            ...(this.spotsSectionVisibility || {}),
                        };
                        next[sectionId] = input.checked;
                        this.spotsSectionVisibility = next;
                        this.saveSpotSectionVisibility();
                        this.renderStandaloneFallbackUi();
                        return;
                    }

                    if (input.hasAttribute('data-number-filter')) {
                        const filterName = input.getAttribute('data-number-filter');
                        this.spotsFilter[filterName] = filterName === 'rblDedupeMinutes' ? Number(input.value || 0) : input.value;
                        this.markStandaloneFiltersChanged();
                        return;
                    }

                    this.applyStandaloneDropdownFilterChange(input);
                });

                menu.addEventListener('input', event => {
                    event.stopPropagation();
                    const input = event.target.closest('input[data-number-filter]');
                    if (!input) return;
                    const filterName = input.getAttribute('data-number-filter');
                    this.spotsFilter[filterName] = filterName === 'rblDedupeMinutes' ? Number(input.value || 0) : input.value;
                    this.markStandaloneFiltersChanged();
                });
            },

            setupStandaloneDropdownFallback() {
                if (this.standaloneDropdownFallbackBound) return;
                this.standaloneDropdownFallbackBound = true;
                document.addEventListener('click', event => {
                    if (event.target.closest('.standalone-filter-menu')) return;
                    const button = event.target.closest('.filter-dropdown > .filter-btn');
                    const name = this.getStandaloneDropdownNameFromButton(button);
                    if (button && name) {
                        event.preventDefault();
                        event.stopPropagation();
                        event.stopImmediatePropagation();
                        event.__standaloneDropdownHandled = true;
                        this.openStandaloneDropdownMenu(name, button);
                        return;
                    }
                    this.closeStandaloneDropdownMenu();
                }, true);
                window.addEventListener('resize', () => this.closeStandaloneDropdownMenu());
                this.bindStandaloneDropdownButtons();
            },

            bindStandaloneDropdownButtons() {
                document.querySelectorAll('.filter-dropdown > .filter-btn').forEach(button => {
                    const name = this.getStandaloneDropdownNameFromButton(button);
                    if (!name) return;
                    let boundButton = button;
                    if (button.dataset.standaloneDropdownNative !== 'true') {
                        boundButton = button.cloneNode(true);
                        boundButton.dataset.standaloneDropdownNative = 'true';
                        button.replaceWith(boundButton);
                    }
                    if (boundButton.dataset.standaloneDropdownBound === 'true') return;
                    boundButton.dataset.standaloneDropdownBound = 'true';
                    boundButton.addEventListener('click', event => {
                        if (event.__standaloneDropdownHandled) return;
                        event.preventDefault();
                        event.stopPropagation();
                        event.stopImmediatePropagation();
                        event.__standaloneDropdownHandled = true;
                        this.openStandaloneDropdownMenu(name, boundButton);
                    }, true);
                });
            },

            setupStandaloneRowsMenuFallback() {
                const rowsButton = Array.from(document.querySelectorAll('.filter-btn'))
                    .find(button => button.textContent.trim().startsWith('Rows'));
                if (!rowsButton || rowsButton.dataset.standaloneRowsBound === 'true') return;
                rowsButton.dataset.standaloneRowsBound = 'true';
                rowsButton.addEventListener('click', event => {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    this.toggleStandaloneRowsMenu(rowsButton);
                }, true);
            },

            toggleStandaloneRowsMenu(rowsButton) {
                const wrapper = rowsButton.closest('.filter-dropdown') || rowsButton.parentElement;
                if (!wrapper) return;
                const existing = wrapper.querySelector('.standalone-rows-menu');
                if (existing) {
                    existing.remove();
                    return;
                }

                const menu = document.createElement('div');
                menu.className = 'dropdown-menu spot-rows-menu standalone-rows-menu';
                const items = this.getSpotSectionVisibilityItems();
                menu.innerHTML = `
                    <div class="dropdown-list">
                        ${items.map(item => `
                            <label>
                                <input type="checkbox" data-section-id="${this.escapeStandaloneHtml(item.id)}" ${this.isSpotSectionVisible(item.id) ? 'checked' : ''}>
                                ${this.escapeStandaloneHtml(item.label)}
                            </label>
                        `).join('')}
                    </div>
                    <div class="dropdown-footer">
                        <button type="button" data-action="show-all">Show all</button>
                    </div>
                `;
                wrapper.appendChild(menu);

                menu.querySelectorAll('input[data-section-id]').forEach(input => {
                    input.addEventListener('change', () => {
                        const sectionId = input.getAttribute('data-section-id');
                        const next = {
                            ...getDefaultSpotSectionVisibility(),
                            ...(this.spotsSectionVisibility || {}),
                        };
                        next[sectionId] = input.checked;
                        this.spotsSectionVisibility = next;
                        this.saveSpotSectionVisibility();
                        this.renderStandaloneFallbackUi();
                    });
                });

                const showAll = menu.querySelector('button[data-action="show-all"]');
                if (showAll) {
                    showAll.addEventListener('click', () => {
                        this.showAllSpotSections();
                        menu.remove();
                        this.renderStandaloneFallbackUi();
                    });
                }
            },

            renderStandaloneFallbackUi() {
                const visible = Array.isArray(this.standaloneVisibleSpots) ? this.standaloneVisibleSpots : [];
                const all = Array.isArray(this.dxSpots) ? this.dxSpots : [];
                const visibleStats = this.buildSpotSourceStats(visible);
                const cacheStats = this.buildSpotSourceStats(all);
                this.setupStandaloneDropdownFallback();
                this.bindStandaloneDropdownButtons();

                const counter = document.querySelector('.spots-source-counter');
                if (counter) {
                    const shownParts = [];
                    if (visibleStats.cluster) shownParts.push(`${visibleStats.cluster} cluster`);
                    if (visibleStats.rbl) shownParts.push(`${visibleStats.rbl} RBL`);
                    counter.textContent = `${visibleStats.total} shown (${shownParts.join(' / ') || 'none'}) · cache ${cacheStats.cluster} cluster / ${cacheStats.rbl} RBL`;
                }
                this.bindStandaloneDropdownButtons();
                this.updateStandaloneFilterButtonStates();

                const sourceStrip = this.isSpotSectionVisible('sourceDiagnostics')
                    ? document.querySelector('.source-diagnostics-strip')
                    : null;
                if (sourceStrip) {
                    let summary = sourceStrip.querySelector('.standalone-source-summary');
                    if (!summary) {
                        summary = document.createElement('div');
                        summary.className = 'source-diagnostics-summary standalone-source-summary';
                        sourceStrip.prepend(summary);
                    }
                    summary.innerHTML = [
                        '<strong>Sources</strong>',
                        `<span class="source-health-pill source-health-${this.clusterConnected ? 'ok' : 'error'}">Cluster ${this.clusterConnected ? 'online' : 'offline'}</span>`,
                        `<span>${visibleStats.total} shown</span>`,
                        `<span>${visibleStats.cluster} cluster</span>`,
                        `<span>${visibleStats.rbl} RBL</span>`,
                        `<span>cache ${cacheStats.cluster}/${cacheStats.rbl}</span>`,
                    ].join('');
                }

                let bandStrip = document.querySelector('.standalone-band-activity-strip');
                const bandItems = this.getStandaloneBandItems(visible);
                if (!this.isSpotSectionVisible('bandActivity')) {
                    if (bandStrip) bandStrip.remove();
                } else if (bandItems.length > 0) {
                    if (!bandStrip) {
                        bandStrip = document.createElement('div');
                        bandStrip.className = 'band-activity-strip standalone-band-activity-strip';
                        const anchor = document.querySelector('.source-diagnostics-strip') || document.querySelector('.spots-scroll');
                        if (anchor) anchor.before(bandStrip);
                    }
                    bandStrip.innerHTML = bandItems.map(item => `
                        <button type="button" data-band="${this.escapeStandaloneHtml(item.band)}" class="band-activity-btn${this.spotsFilter.bands.includes(item.band) ? ' active' : ''}">
                            <strong>${this.escapeStandaloneHtml(item.band)}</strong>
                            <span>${item.total}</span>
                            <small>best ${item.topScore}</small>
                            ${item.rbl ? `<small>RBL ${item.rbl}</small>` : ''}
                        </button>
                    `).join('');
                    bandStrip.querySelectorAll('button[data-band]').forEach(button => {
                        button.addEventListener('click', () => {
                            const band = button.getAttribute('data-band');
                            this.spotsFilter.bands = band ? [band] : [];
                            this.updateStandaloneVisibleSpots();
                        }, { once: true });
                    });
                } else if (bandStrip) {
                    bandStrip.remove();
                }

                const tbody = document.querySelector('.spots-table tbody');
                if (!tbody) return;
                if (visible.length === 0) {
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="15" style="text-align: center; padding: 20px; color: #666;">
                                <div>${this.clusterConnected ? 'No spots match current filters' : 'DX Cluster is DISCONNECTED - No spots will be received'}</div>
                            </td>
                        </tr>
                    `;
                    return;
                }

                tbody.innerHTML = visible.map((spot, index) => {
                    const freqMhz = spot.frequency_mhz || parseFloat(spot.frequency) / 1000;
                    const specials = String(spot.special || '')
                        .split(', ')
                        .filter(Boolean)
                        .map(special => `<span class="special-badge">${this.escapeStandaloneHtml(special)}</span>`)
                        .join(' ');
                    return `
                        <tr class="spot-row ${this.escapeStandaloneHtml(this.getSpotRowClass(spot) || '')}" data-standalone-spot-index="${index}">
                            <td style="font-size: 12px;"><button type="button" title="Spot details">ⓘ</button></td>
                            <td style="font-size: 13px;">${this.escapeStandaloneHtml(this.formatSpotTime(spot.timestamp))}</td>
                            <td style="font-size: 12px;"><span style="font-weight: 700; padding: 2px 6px; border-radius: 4px;">${this.escapeStandaloneHtml(this.getSpotScore(spot))}</span></td>
                            <td style="font-size: 13px; font-weight: bold;">${this.escapeStandaloneHtml(spot.band || '')}</td>
                            <td style="font-size: 13px; font-family: monospace; color: #4a9eff;">${this.escapeStandaloneHtml(this.formatSpotFreq(freqMhz))}</td>
                            <td style="font-size: 13px; font-weight: bold; color: #10b981;">${this.escapeStandaloneHtml(spot.callsign || '')}</td>
                            <td style="font-size: 13px;">${this.escapeStandaloneHtml(spot.mode || '')}</td>
                            <td style="font-size: 13px; color: #ccc;">${(spot.spot_source === 'rbl') ? '<span style="color: #fbbf24; font-weight: 700;">RBL</span> ' : ''}${this.escapeStandaloneHtml(spot.country || '-')}</td>
                            <td style="font-size: 13px; text-align: center;">${this.escapeStandaloneHtml(spot.cq || '-')}</td>
                            <td style="font-size: 13px; color: #ccc;">${this.escapeStandaloneHtml(this.getSpotterSummary(spot))}</td>
                            <td>${this.escapeStandaloneHtml(spot.call_status || '-')}</td>
                            <td>${this.escapeStandaloneHtml(spot.dxcc_status || '-')}</td>
                            <td style="font-size: 12px; padding: 4px;">${specials}</td>
                            <td style="font-size: 12px; color: #10b981; font-weight: 500;">${this.escapeStandaloneHtml(this.getWorkedDate(spot.callsign, spot.band, spot.mode))}</td>
                            <td style="font-size: 13px; color: #aaa;">${this.escapeStandaloneHtml(spot.comment || '')}</td>
                        </tr>
                    `;
                }).join('');

                tbody.querySelectorAll('tr[data-standalone-spot-index]').forEach(row => {
                    row.addEventListener('click', () => {
                        const spot = visible[Number(row.getAttribute('data-standalone-spot-index'))];
                        if (spot) this.tuneToSpot(spot);
                    });
                });
            },

            renderStandaloneTableRows() {
                const visible = Array.isArray(this.standaloneVisibleSpots) ? this.standaloneVisibleSpots : [];
                const all = Array.isArray(this.dxSpots) ? this.dxSpots : [];
                const visibleStats = this.buildSpotSourceStats(visible);
                const cacheStats = this.buildSpotSourceStats(all);

                const counter = document.querySelector('.spots-source-counter');
                if (counter) {
                    const shownParts = [];
                    if (visibleStats.cluster) shownParts.push(`${visibleStats.cluster} cluster`);
                    if (visibleStats.rbl) shownParts.push(`${visibleStats.rbl} RBL`);
                    counter.textContent = visibleStats.total > 0
                        ? `${visibleStats.total} shown (${shownParts.join(' / ') || 'none'}) · cache ${cacheStats.cluster} cluster / ${cacheStats.rbl} RBL`
                        : `0 shown · cache ${cacheStats.cluster} cluster / ${cacheStats.rbl} RBL`;
                }
                this.updateStandaloneFilterButtonStates();

                document.querySelectorAll('.source-diagnostics-strip button').forEach(button => {
                    const label = button.textContent.trim();
                    const sources = this.spotsFilter.spotSources || [];
                    button.classList.toggle('active', label === 'Cluster only' && sources.length === 1 && sources[0] === 'cluster');
                    button.classList.toggle('active', label === 'RBL only' && sources.length === 1 && sources[0] === 'rbl');
                    button.classList.toggle('active', label === 'All sources' && sources.includes('cluster') && sources.includes('rbl'));
                });

                const tbody = document.querySelector('.spots-table tbody');
                if (!tbody) return;
                if (visible.length === 0) {
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="15" style="text-align: center; padding: 20px; color: #666;">
                                <div>${this.clusterConnected ? 'No spots match current filters' : 'DX Cluster is DISCONNECTED - No spots will be received'}</div>
                            </td>
                        </tr>
                    `;
                    return;
                }

                tbody.innerHTML = visible.map((spot, index) => {
                    const freqMhz = spot.frequency_mhz || parseFloat(spot.frequency) / 1000;
                    const specials = String(spot.special || '')
                        .split(', ')
                        .filter(Boolean)
                        .map(special => `<span class="special-badge">${this.escapeStandaloneHtml(special)}</span>`)
                        .join(' ');
                    return `
                        <tr class="spot-row ${this.escapeStandaloneHtml(this.getSpotRowClass(spot) || '')}" data-standalone-spot-index="${index}">
                            <td><button type="button" title="Spot details">ⓘ</button></td>
                            <td>${this.escapeStandaloneHtml(this.formatSpotTime(spot.timestamp))}</td>
                            <td><span style="font-weight: 700; padding: 2px 6px; border-radius: 4px;">${this.escapeStandaloneHtml(this.getSpotScore(spot))}</span></td>
                            <td>${this.escapeStandaloneHtml(spot.band || '')}</td>
                            <td style="font-family: monospace; color: #4a9eff;">${this.escapeStandaloneHtml(this.formatSpotFreq(freqMhz))}</td>
                            <td style="font-weight: bold; color: #10b981;">${this.escapeStandaloneHtml(spot.callsign || '')}</td>
                            <td>${this.escapeStandaloneHtml(spot.mode || '')}</td>
                            <td>${(spot.spot_source === 'rbl') ? '<span style="color: #fbbf24; font-weight: 700;">RBL</span> ' : ''}${this.escapeStandaloneHtml(spot.country || '-')}</td>
                            <td>${this.escapeStandaloneHtml(spot.cq || '-')}</td>
                            <td>${this.escapeStandaloneHtml(this.getSpotterSummary(spot))}</td>
                            <td>${this.escapeStandaloneHtml(spot.call_status || '-')}</td>
                            <td>${this.escapeStandaloneHtml(spot.dxcc_status || '-')}</td>
                            <td>${specials}</td>
                            <td>${this.escapeStandaloneHtml(this.getWorkedDate(spot.callsign, spot.band, spot.mode))}</td>
                            <td>${this.escapeStandaloneHtml(spot.comment || '')}</td>
                        </tr>
                    `;
                }).join('');
            },

            updateStandaloneVisibleSpots(options = {}) {
                const scroll = document.querySelector('.spots-scroll');
                const scrollTop = scroll ? scroll.scrollTop : 0;
                const scrollLeft = scroll ? scroll.scrollLeft : 0;
                this.filteredSearchResults = [];
                this.lastSearchFilter = null;
                let visible = this.getStandaloneFilteredSpots(this.dxSpots || []);
                const selectedSources = this.spotsFilter.spotSources || [];
                if (
                    visible.length === 0 &&
                    selectedSources.length === 1 &&
                    selectedSources[0] === 'cluster' &&
                    (this.dxSpots || []).some(spot => (spot.spot_source || 'cluster') === 'rbl')
                ) {
                    this.spotsFilter.spotSources = ['cluster', 'rbl'];
                    visible = this.getStandaloneFilteredSpots(this.dxSpots || []);
                }
                this.standaloneVisibleSpots = visible;
                document.documentElement.dataset.standaloneDxCount = String((this.dxSpots || []).length);
                document.documentElement.dataset.standaloneVisibleCount = String(visible.length);
                document.documentElement.dataset.standaloneSources = (this.spotsFilter.spotSources || []).join(',');
                this.standaloneRenderTick += 1;
                if (this.$forceUpdate) {
                    this.$forceUpdate();
                }
                this.renderStandaloneTableRows();
                if (this.$nextTick) {
                    this.$nextTick(() => {
                        if (options.preserveScroll && scroll) {
                            scroll.scrollTop = scrollTop;
                            scroll.scrollLeft = scrollLeft;
                        }
                    });
                }
            },

            async loadStandaloneLiveCache() {
                try {
                    const limit = Math.max(250, Math.min(500, Number(this.maxSpots || 100) * 5));
                    const response = await fetch(`/api/spots/live-cache?limit=${limit}`);
                    const data = await response.json();
                    if (!response.ok) {
                        throw new Error(data.detail || data.error || `HTTP ${response.status}`);
                    }

                    const spots = Array.isArray(data.spots) ? data.spots.map(spot => ({ ...spot })) : [];
                    document.documentElement.dataset.standaloneLiveCacheCount = String(spots.length);
                    if (spots.length > 0) {
                        if (this.standaloneUsingDatabaseResults) {
                            this.mergeStandaloneSpots(spots);
                            return;
                        }
                        const hardLimit = Math.max(500, Number(this.maxSpots || 100));
                        this.dxSpots = spots.slice(0, hardLimit);
                        this.lastStandaloneResultSignature = this.getStandaloneResultSignature(this.dxSpots);
                        this.filteredSearchResults = [];
                        this.lastSearchFilter = null;
                        this.spotSourceStats = {
                            ...(this.spotSourceStats || {}),
                            live: this.buildSpotSourceStats(this.dxSpots),
                        };
                        this.filteredSearchWarning = '';
                        this.isSearchingSpots = false;
                        this.evaluateRblAlertsForVisibleSpots();
                        this.updateStandaloneVisibleSpots();
                    }

                    const hasRecentCluster = spots.some(spot => {
                        if ((spot.spot_source || 'cluster') !== 'cluster') return false;
                        const timestamp = this.getSpotTimestamp(spot);
                        if (!timestamp) return true;
                        return (Date.now() / 1000 - timestamp) <= 1800;
                    });
                    if (hasRecentCluster) {
                        this.clusterConnected = true;
                        this.clusterStatus = {
                            ...this.clusterStatus,
                            connected: true,
                        };
                    }
                } catch (error) {
                    console.warn('Could not load filters window spot cache:', error);
                }
            },

            getStandaloneResultSignature(spots) {
                return (spots || [])
                    .slice(0, Number(this.maxSpots || 100))
                    .map(spot => [
                        spot.aggregate_key || spot.id || spot.callsign || '',
                        spot.frequency_mhz || spot.frequency || '',
                        spot.timestamp || '',
                        spot.aggregate_count || '',
                    ].join(':'))
                    .join('|');
            },

            async loadStandaloneFilteredSearch() {
                try {
                    const criteria = this.buildSpotFilterCriteria();
                    criteria.limit = Number(this.maxSpots || 100);
                    const response = await fetch('/api/spots/filtered-search', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(criteria),
                    });
                    const result = await response.json();
                    if (!response.ok || !result.ok || !Array.isArray(result.spots)) {
                        throw new Error(result.warning || result.error || result.detail || `HTTP ${response.status}`);
                    }

                    if (result.spots.length > 0) {
                        const nextSpots = result.spots.map(spot => ({ ...spot }));
                        const nextSignature = this.getStandaloneResultSignature(nextSpots);
                        this.standaloneUsingDatabaseResults = true;
                        this.spotSourceStats = {
                            ...(this.spotSourceStats || {}),
                            live: this.buildSpotSourceStats(nextSpots),
                        };
                        this.clusterConnected = nextSpots.some(spot => (spot.spot_source || 'cluster') === 'cluster') || this.clusterConnected;
                        if (nextSignature !== this.lastStandaloneResultSignature) {
                            this.lastStandaloneResultSignature = nextSignature;
                            this.dxSpots = nextSpots;
                            this.updateStandaloneVisibleSpots({ preserveScroll: true });
                        }
                    }
                    this.filteredSearchWarning = '';
                } catch (error) {
                    this.filteredSearchWarning = error.message || 'Spots database search failed';
                    console.warn('Filters window database search failed, keeping live cache:', error);
                }
            },

            updateStandaloneClusterStateFromStats() {
                const health = this.getClusterHealth();
                if (health.status === 'ok' || health.status === 'warn' || health.status === 'stale') {
                    this.clusterConnected = true;
                    this.clusterStatus = {
                        ...this.clusterStatus,
                        connected: true,
                    };
                }
            },

            refreshStandaloneSpots() {
                this.loadSpotSourceStats().then(() => this.updateStandaloneClusterStateFromStats());
                this.loadStandaloneLiveCache();
                this.loadStandaloneFilteredSearch();
                this.loadStandaloneServiceHealth();
                this.refreshWsjtxEngineHealth({ force: true });
            },

            rotorAutoGoto() {},
            resolveRotorTarget() {
                return Promise.resolve({ ok: false, message: 'Rotor is not available in detached filters window' });
            },
            loadQRZProfile() {
                return Promise.resolve();
            },
            loadDXCCStatus() {
                return Promise.resolve();
            },
            showConfigDialog(section) {
                this.showStatus(section === 'wsjtx' ? 'Open WSJT tools in the main window' : 'Open config in the main window', 'info');
            },
            openCallsignSearchModal() {},
            refreshLogEntries() {},
            setLogLimit(limit) {
                this.logLimit = limit;
            },
            hasActiveLogFilters() {
                return false;
            },
            getFilteredLogEntries() {
                return [];
            },
            openColumnConfig() {},
            clearLogFilters() {},

            bootstrapStandaloneSpots() {
                if (this.standaloneBootStarted) return;
                this.standaloneBootStarted = true;

                window.vueInstance = this;
                this.loadSpotSectionVisibility();
                this.loadSpotsPopoutState();
                this.setupStandaloneClickBridge();
                this.setupStandaloneDropdownFallback();

                this.loadStandaloneLiveCache();
                this.loadStandaloneFilteredSearch();
                setTimeout(() => this.loadStandaloneLiveCache(), 1500);
                setTimeout(() => this.loadStandaloneFilteredSearch(), 1800);
                this.setupSpotSourceStatsRefresh();
                this.setupWsjtxEngineHealthRefresh();
                this.setupActivityIntelligenceRefresh();
                this.setupVisualGlobeRefresh();
                this.connectStandaloneSpotSocket();
                this.startMainSnapshotSync();
                this.standaloneRefreshTimer = setInterval(() => {
                    this.refreshStandaloneSpots();
                }, 15000);

                Promise.allSettled([
                    this.loadStandaloneConfig(),
                    this.loadStandaloneServiceHealth(),
                    this.loadSpotSourceStats().then(() => this.updateStandaloneClusterStateFromStats()),
                    this.loadRblProfiles(),
                    this.loadRblCommandStatus(),
                    this.refreshWsjtxEngineHealth({ force: true }),
                    this.loadActivityIntelligence(),
                ]).catch(error => {
                    console.warn('Filters window background startup failed:', error);
                });

                this.loadWorkedCallsigns().then(() => {
                    this.evaluateRblAlertsForVisibleSpots();
                }).catch(error => {
                    console.warn('Could not load worked callsigns in filters window:', error);
                });
                this.loadSpotSourceMuteState();
                this.loadRblAlertRules();
            },
        },
        async mounted() {
            this.bootstrapStandaloneSpots();
        },
        beforeUnmount() {
            if (this.spotsFilterDebounceTimer) clearTimeout(this.spotsFilterDebounceTimer);
            if (this.standaloneRefreshTimer) clearInterval(this.standaloneRefreshTimer);
            if (this.standaloneSpotFlushTimer) clearTimeout(this.standaloneSpotFlushTimer);
            this.stopMainSnapshotSync();
            if (this.standaloneWs) this.standaloneWs.close();
            if (this.standaloneCommandChannel) this.standaloneCommandChannel.close();
            this.cleanupSpotSourceStatsRefresh();
            this.cleanupWsjtxEngineHealthRefresh();
            this.cleanupActivityIntelligenceRefresh();
            this.cleanupVisualGlobeRefresh();
        },
    });

    const mountedApp = app.mount('#app');
    window.vueInstance = mountedApp;
    if (mountedApp && typeof mountedApp.bootstrapStandaloneSpots === 'function') {
        mountedApp.bootstrapStandaloneSpots();
    }
})().catch(error => {
    console.error('Filters window failed to start:', error);
    document.body.innerHTML = `<pre style="color:#fecaca;background:#111827;padding:16px">${error.message}</pre>`;
});
