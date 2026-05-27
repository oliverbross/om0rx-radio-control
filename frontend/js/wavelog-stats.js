// Wavelog dashboard statistics state, computed values, and API loading.

console.log('✅ Loading wavelog-stats.js module...');

window.RadioControlWavelogStats = {
    data: {
        wavelogStats: null,
        wavelogWpStats: null,
        statsLoading: false,
        wavelogStatsRefreshTimer: null,
        wavelogStatsRetryTimers: [],
        wavelogStatsLastLoadedAt: 0,
    },

    computed: {
        consolidatedWavelogModes() {
            if (!this.wavelogWpStats || !this.wavelogWpStats.statistics || !this.wavelogWpStats.statistics.totalgroupedmodes) {
                console.log('❌ No wavelog WP stats available for consolidation');
                return [];
            }

            const modes = this.wavelogWpStats.statistics.totalgroupedmodes;
            console.log('🔍 Raw modes data:', modes);

            const consolidated = {
                CW: 0,
                SSB: 0,
                DIGI: 0,
            };

            const ssbModes = ['SSB', 'USB', 'LSB', 'AM', 'FM'];
            const digitalModes = ['FT8', 'FT4', 'MFSK', 'RTTY', 'PSK', 'PSK31', 'PSK63', 'JT65', 'JT9',
                'OLIVIA', 'DOMINO', 'HELL', 'MT63', 'THOR', 'THROB', 'CONTESTI', 'JS8'];

            modes.forEach(modeObj => {
                const mode = (modeObj.col_submode || modeObj.col_mode).toUpperCase();
                const count = parseInt(modeObj.count || modeObj.total) || 0;
                console.log(`  Mode: ${mode}, Count: ${count}, Raw obj:`, modeObj);

                if (mode === 'CW') {
                    consolidated.CW += count;
                } else if (ssbModes.includes(mode)) {
                    consolidated.SSB += count;
                } else if (digitalModes.includes(mode)) {
                    consolidated.DIGI += count;
                } else {
                    console.log(`⚠️ Unknown mode "${mode}" added to DIGI`);
                    consolidated.DIGI += count;
                }
            });

            console.log('✅ Consolidated totals:', consolidated);

            return [
                { mode: 'CW', total: consolidated.CW },
                { mode: 'SSB', total: consolidated.SSB },
                { mode: 'DIGI', total: consolidated.DIGI },
            ];
        },
    },

    methods: {
        async loadWavelogStatistics(options = {}) {
            const force = Boolean(options.force);
            if (this.statsLoading && !force) {
                return;
            }

            try {
                console.log('📊 Loading Wavelog statistics...');
                this.statsLoading = true;
                const cacheBust = force ? `?t=${Date.now()}` : '';

                const [statsResponse, wpStatsResponse] = await Promise.all([
                    fetch(`/api/wavelog-log/statistics${cacheBust}`, { cache: 'no-store' }),
                    fetch(`/api/wavelog-log/wp-statistics${cacheBust}`, { cache: 'no-store' }),
                ]);

                if (statsResponse.ok) {
                    const statsData = await statsResponse.json();
                    this.wavelogStats = statsData.data;
                    this.wavelogStatsLastLoadedAt = Date.now();
                    console.log('✅ Wavelog statistics loaded:', this.wavelogStats);
                } else {
                    console.error('❌ Failed to load Wavelog statistics:', statsResponse.status);
                }

                if (wpStatsResponse.ok) {
                    const wpStatsData = await wpStatsResponse.json();
                    this.wavelogWpStats = wpStatsData.data;
                    console.log('✅ Wavelog WP statistics loaded:', this.wavelogWpStats);
                } else {
                    console.error('❌ Failed to load Wavelog WP statistics:', wpStatsResponse.status);
                }
            } catch (error) {
                console.error('❌ Failed to load Wavelog statistics:', error);
                this.wavelogStats = null;
                this.wavelogWpStats = null;
            } finally {
                this.statsLoading = false;
            }
        },

        setupWavelogStatisticsRefresh() {
            this.cleanupWavelogStatisticsRefresh();
            this.wavelogStatsRefreshTimer = setInterval(() => {
                this.loadWavelogStatistics();
            }, 60000);
        },

        cleanupWavelogStatisticsRefresh() {
            if (this.wavelogStatsRefreshTimer) {
                clearInterval(this.wavelogStatsRefreshTimer);
                this.wavelogStatsRefreshTimer = null;
            }
            for (const timer of this.wavelogStatsRetryTimers || []) {
                clearTimeout(timer);
            }
            this.wavelogStatsRetryTimers = [];
        },

        clearWavelogLookupCaches(callsign = '') {
            const call = String(callsign || '').trim().toUpperCase();
            if (!call) {
                this.wavelogLookupCache = {};
                this.lastWavelogRawLookup = null;
                this.lastWavelogLookupKey = null;
                return;
            }

            if (this.wavelogLookupCache) {
                for (const key of Object.keys(this.wavelogLookupCache)) {
                    if (key.startsWith(`${call}|`)) {
                        delete this.wavelogLookupCache[key];
                    }
                }
            }
            if (this.lastWavelogLookupKey?.startsWith(`${call}|`)) {
                this.lastWavelogRawLookup = null;
                this.lastWavelogLookupKey = null;
            }
        },

        scheduleWavelogStatisticsRefresh(reason = 'scheduled', delays = [0]) {
            for (const delay of delays) {
                const timer = setTimeout(async () => {
                    this.wavelogStatsRetryTimers = (this.wavelogStatsRetryTimers || []).filter(item => item !== timer);
                    console.log(`📊 Refreshing Wavelog statistics (${reason})`);
                    await this.loadWavelogStatistics({ force: true });
                }, Math.max(0, Number(delay) || 0));
                this.wavelogStatsRetryTimers.push(timer);
            }
        },

        async handleQsoLogged(qsoData = {}) {
            const callsign = qsoData.callsign || qsoData.call || this.loggingForm?.callsign || '';
            this.clearWavelogLookupCaches(callsign);
            this.scheduleWavelogStatisticsRefresh('QSO logged', [0, 8000, 30000]);

            if (typeof this.loadWorkedCallsigns === 'function') {
                await this.loadWorkedCallsigns();
            }
            if (typeof this.loadQsoOutboxStatus === 'function') {
                await this.loadQsoOutboxStatus();
            }
            if (
                callsign &&
                this.loggingForm?.callsign &&
                String(this.loggingForm.callsign).trim().toUpperCase() === String(callsign).trim().toUpperCase() &&
                typeof this.loadDXCCStatus === 'function'
            ) {
                await this.loadDXCCStatus({ force: true });
            }
        },

        formatModeCount(mode, submode, count) {
            if (submode) {
                return `${mode}/${submode}: ${count}`;
            }
            return `${mode}: ${count}`;
        },
    },
};
