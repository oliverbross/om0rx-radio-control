// Solar data state and formatting helpers for the Vue application.

console.log('✅ Loading solar-data.js module...');

window.RadioControlSolar = {
    data: {
        solarData: null,
        solarUpdateTimer: null,
    },

    computed: {
        isDaytime() {
            const hour = new Date().getHours();
            return hour >= 6 && hour < 20;
        },
    },

    methods: {
        async loadSolarData() {
            try {
                console.log('🌞 Loading solar data...');
                const response = await fetch('/api/solar');
                if (!response.ok) {
                    throw new Error(`API error: ${response.status}`);
                }

                const data = await response.json();
                this.solarData = data;
                console.log('✅ Solar data loaded:', data.indices);

                return data;
            } catch (error) {
                console.error('❌ Failed to load solar data:', error);
                this.solarData = null;
                return null;
            }
        },

        setupSolarDataRefresh() {
            if (this.solarUpdateTimer) {
                clearInterval(this.solarUpdateTimer);
            }

            this.solarUpdateTimer = setInterval(() => {
                this.loadSolarData();
            }, 10 * 60 * 1000);

            console.log('✅ Solar data auto-refresh setup (10 minutes)');
        },

        formatBandName(band) {
            return band.replace('m_', '-').replace('_', '-');
        },

        getHFCondition(conditions, isDaytime) {
            return isDaytime ? conditions.day : conditions.night;
        },

        getHFConditionClass(conditions, isDaytime) {
            const condition = isDaytime ? conditions.day : conditions.night;
            if (!condition) return 'unknown';

            const cond = condition.toLowerCase();
            if (cond.includes('good') || cond.includes('excellent')) return 'good';
            if (cond.includes('fair') || cond.includes('normal')) return 'fair';
            if (cond.includes('poor') || cond.includes('bad')) return 'poor';
            return 'unknown';
        },

        getSolarData() {
            return window.SolarOverlay ? window.SolarOverlay.getSolarData() : this.solarData;
        },

        cleanupSolarDataRefresh() {
            if (this.solarUpdateTimer) {
                clearInterval(this.solarUpdateTimer);
                this.solarUpdateTimer = null;
            }
        },
    },
};
