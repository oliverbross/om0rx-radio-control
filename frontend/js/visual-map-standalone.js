// Standalone visual DX spots map entry point.

(async function bootstrapVisualMapWindow() {
    const templateTarget = document.getElementById('dx-spots-section');
    const partialCache = new Map();

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
        const response = await fetch('templates/dx-spots.html?v=20260602-visual-map-cache-fix', {
            cache: 'no-store',
        });
        if (!response.ok) {
            throw new Error(`Failed to load visual map template: HTTP ${response.status}`);
        }
        templateTarget.innerHTML = await resolveTemplateIncludes(await response.text());
    }

    function arrayParam(params, key) {
        return (params.get(key) || '')
            .split(',')
            .map(item => item.trim())
            .filter(Boolean);
    }

    function applyUrlState(vm) {
        const params = new URLSearchParams(window.location.search);
        vm.viewMode = 'visual';
        vm.visualMapMode = params.get('map') || vm.visualMapMode || 'globe';
        vm.visualSpotWindowMinutes = Number(params.get('window') || vm.visualSpotWindowMinutes || 60);
        vm.visualSpotLatestOnly = params.get('latest') !== '0';
        vm.visualOverlayMode = params.get('overlay') || vm.visualOverlayMode || 'dxcc';
        vm.visualLocationConfidence = params.get('confidence') || vm.visualLocationConfidence || 'all';
        vm.visualPathColorBy = params.get('pathColor') || vm.visualPathColorBy || 'band';
        vm.visualPathWidth = Number(params.get('pathWidth') || vm.visualPathWidth || 2.1);
        vm.visualSpotQuickFilter = params.get('quick') || vm.visualSpotQuickFilter || 'all';

        const sources = arrayParam(params, 'sources');
        vm.spotsFilter.spotSources = sources.length > 0 ? sources : ['cluster'];
        vm.spotsFilter.bands = arrayParam(params, 'bands');
        vm.spotsFilter.modes = arrayParam(params, 'modes');
        vm.spotsFilter.rblModes = arrayParam(params, 'rblModes');
        vm.spotsFilter.rblMinSnr = params.get('rblMinSnr') || '';
        vm.spotsFilter.rblDedupeMinutes = Number(params.get('rblDedupeMinutes') || 0);
    }

    await loadTemplate();

    const { createApp } = Vue;
    const app = createApp({
        data() {
            return {
                ...clone(window.FlexRadioSpots ? window.FlexRadioSpots.data : {}),
                viewMode: 'visual',
                logEntries: [],
                logLimit: 100,
                availableLogLimits: [50, 100, 250, 500],
                logFilters: {},
                configData: {},
                statusMessage: null,
                visualStandaloneWs: null,
                visualStandaloneRefreshTimer: null,
                visualStandaloneStatusTimer: null,
                loggingPanelSectionCollapsed: true,
                suppressCallsignLookup: false,
                loggingForm: {
                    callsign: '',
                    frequency: '',
                    band: '',
                    mode: '',
                    time_off: '',
                    rst_sent: '599',
                    rst_rcvd: '599',
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
        },
        methods: {
            ...(window.FlexRadioSpots ? window.FlexRadioSpots.methods : {}),

            switchViewMode() {
                this.viewMode = 'visual';
                this.$nextTick(() => this.queueVisualGlobeDraw());
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

            loadQRZProfile() {},
            loadDXCCStatus() {},
            rotorAutoGoto() {},
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

            async loadStandaloneConfig() {
                try {
                    const response = await fetch('/api/config');
                    const data = await response.json();
                    if (response.ok && data.success && data.config) {
                        this.configData = data.config;
                    }
                } catch (error) {
                    console.warn('Could not load visual map config:', error);
                }
            },

            connectStandaloneSpotSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const url = `${protocol}//${window.location.host}/ws/radio`;
                this.visualStandaloneWs = new WebSocket(url);

                this.visualStandaloneWs.onopen = () => {
                    this.clusterConnected = true;
                };

                this.visualStandaloneWs.onmessage = event => {
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
                    message.data.forEach(newSpot => {
                        const index = this.findExistingSpotIndex(newSpot, this.dxSpots);
                        if (index >= 0) {
                            Object.assign(this.dxSpots[index], this.mergeSpotAggregate(this.dxSpots[index], newSpot));
                            if (index !== 0) {
                                const [spot] = this.dxSpots.splice(index, 1);
                                this.dxSpots.unshift(spot);
                            }
                        } else {
                            this.dxSpots.unshift(newSpot);
                        }
                    });
                    this.dxSpots = this.dxSpots.slice(0, Math.max(200, Number(this.maxSpots || 100)));
                    this.queueVisualGlobeDraw();
                };

                this.visualStandaloneWs.onclose = () => {
                    this.clusterConnected = false;
                    setTimeout(() => this.connectStandaloneSpotSocket(), 5000);
                };
            },

            refreshStandaloneFallback() {
                this.visualFallbackFilterKey = '';
                this.loadSpotSourceStats();
                this.loadVisualFallbackSpots();
            },
        },
        async mounted() {
            window.vueInstance = this;
            applyUrlState(this);
            await this.loadStandaloneConfig();
            await Promise.allSettled([
                this.loadSpotSourceStats(),
                this.loadRblProfiles(),
                this.loadRblCommandStatus(),
            ]);
            this.setupSpotSourceStatsRefresh();
            this.setupVisualGlobeRefresh();
            this.connectStandaloneSpotSocket();
            await this.loadVisualFallbackSpots();
            this.visualStandaloneRefreshTimer = setInterval(() => {
                this.refreshStandaloneFallback();
            }, 15000);
            this.$nextTick(() => this.queueVisualGlobeDraw());
        },
        beforeUnmount() {
            this.cleanupSpotSourceStatsRefresh();
            this.cleanupVisualGlobeRefresh();
            if (this.visualStandaloneRefreshTimer) {
                clearInterval(this.visualStandaloneRefreshTimer);
            }
            if (this.visualStandaloneWs) {
                this.visualStandaloneWs.close();
            }
        },
    });

    window.vueInstance = app.mount('#app');
})().catch(error => {
    console.error('Visual map window failed to start:', error);
    document.body.innerHTML = `<pre style="color:#fecaca;background:#111827;padding:16px">${error.message}</pre>`;
});
