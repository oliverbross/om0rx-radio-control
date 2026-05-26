// Wavelog dashboard statistics state, computed values, and API loading.

console.log('✅ Loading wavelog-stats.js module...');

window.RadioControlWavelogStats = {
    data: {
        wavelogStats: null,
        wavelogWpStats: null,
        statsLoading: false,
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
        async loadWavelogStatistics() {
            try {
                console.log('📊 Loading Wavelog statistics...');
                this.statsLoading = true;

                const [statsResponse, wpStatsResponse] = await Promise.all([
                    fetch('/api/wavelog-log/statistics'),
                    fetch('/api/wavelog-log/wp-statistics'),
                ]);

                if (statsResponse.ok) {
                    const statsData = await statsResponse.json();
                    console.log('📊 Raw statistics response:', JSON.stringify(statsData, null, 2));
                    this.wavelogStats = statsData.data;
                    console.log('✅ Wavelog statistics loaded:', this.wavelogStats);
                    console.log('  - Today:', this.wavelogStats?.Today);
                    console.log('  - Month:', this.wavelogStats?.month_qsos);
                    console.log('  - Year:', this.wavelogStats?.year_qsos);
                    console.log('  - Total:', this.wavelogStats?.total_qsos);
                } else {
                    console.error('❌ Failed to load Wavelog statistics:', statsResponse.status);
                }

                if (wpStatsResponse.ok) {
                    const wpStatsData = await wpStatsResponse.json();
                    console.log('📊 Raw WP statistics response:', JSON.stringify(wpStatsData, null, 2));
                    this.wavelogWpStats = wpStatsData.data;
                    console.log('✅ Wavelog WP statistics loaded:', this.wavelogWpStats);
                    if (this.wavelogWpStats?.statistics?.totalgroupedmodes) {
                        console.log('  - Total modes:', this.wavelogWpStats.statistics.totalgroupedmodes.length);
                        const consolidated = this.consolidatedWavelogModes;
                        console.log('📊 Consolidated modes:', consolidated);
                        console.log('  - CW:', consolidated[0]?.total || 0);
                        console.log('  - SSB:', consolidated[1]?.total || 0);
                        console.log('  - DIGI:', consolidated[2]?.total || 0);
                    }
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

        formatModeCount(mode, submode, count) {
            if (submode) {
                return `${mode}/${submode}: ${count}`;
            }
            return `${mode}: ${count}`;
        },
    },
};
