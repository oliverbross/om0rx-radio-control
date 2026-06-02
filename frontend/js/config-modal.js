// Configuration modal state, computed flags, and API helpers.

console.log('Loading config-modal.js module...');

window.RadioControlConfig = {
    data: {
        configData: {
            ROTOR_ENABLED: false,
            WAVELOG_ENABLED: true,
            QRZ_ENABLED: true,
            CLUSTER_ENABLED: false,
            CLUSTERS: [
                { enabled: true, host: 'localhost', port: 7373, user: 'N0CALL', password: '', use_as_failover: false, name: 'Cluster 1 (Primary)' },
                { enabled: false, host: 'localhost', port: 7373, user: 'N0CALL', password: '', use_as_failover: true, name: 'Cluster 2 (Failover)' },
                { enabled: false, host: 'localhost', port: 7373, user: 'N0CALL', password: '', use_as_failover: true, name: 'Cluster 3 (Failover)' },
                { enabled: false, host: 'localhost', port: 7373, user: 'N0CALL', password: '', use_as_failover: true, name: 'Cluster 4 (Failover)' },
                { enabled: false, host: 'localhost', port: 7373, user: 'N0CALL', password: '', use_as_failover: true, name: 'Cluster 5 (Failover)' },
            ],
            WSJTX_ENABLED: true,
            WSJTX_UDP_PORT: 2237,
            WSJTX_UDP_MULTICAST: '224.0.0.1',
            WSJTX_WS_PORT: 8091,
            WSJTX_AUTO_LOG: true,
            WSJTX_AUTO_ROTATE: true,
            COLORS: {
                'ATNO': '#FFFF8C00',
                'New band': '#FF00BFFF',
                'New mode': '#FFFFC000',
                'New band+mode': '#FFE91E63',
                'Need LoTW': '#FF32CD32',
                'Worked': '#FFB0B0B0',
                'Default': '#FFFFFFFF',
                'New Call': '#FFFF6B35',
                'Confirmed': '#FF10B981',
                'C/New Band': '#FF4A9EFF',
                'C/New Mode': '#FFFFD93D',
                'C/New Band+Mode': '#FF9C27B0',
                'W/New Band': '#FF00BCD4',
                'W/New Mode': '#FFFFA726',
                'W/New Band+Mode': '#FFFF5722',
                'Unknown': '#FF666666',
            },
            WINKEYER_ENABLED: false,
            WINKEYER_PORT: 'COM3',
            WINKEYER_BAUDRATE: 1200,
            WINKEYER_DEFAULT_WPM: 20,
            WINKEYER_MEMORIES: {
                M1: 'CQ DE OM0RX',
                M2: 'UR RST 599',
                M3: 'QSL TU DE OM0RX',
                M4: 'MNI TU',
            },
            RADIO_SHOW_DETAILED_CONTROLS: false,
            RADIO_LAYOUT_PRESET: 'compact',
            RBL_COMMAND_PROFILE: 'dxspider',
            RBL_COMMAND_PROFILES: {},
            ACTIVITY_INTELLIGENCE: {
                enabled: true,
                enrichExistingSpots: true,
                showPriorityScore: true,
                autoSortByPriority: false,
                dxpeditions: {
                    enabled: true,
                    ng3kAdxoEnabled: true,
                    dxcalIcsEnabled: true,
                    ng3kPollHours: 12,
                },
                contests: {
                    enabled: true,
                    wa7bnmEnabled: true,
                    wa7bnmFeedPollHours: 6,
                    wa7bnmDetailParsingEnabled: false,
                    localContestDefinitionsPath: 'config/contest_definitions.yaml',
                    showRunningContestBanner: true,
                },
                portable: {
                    enabled: true,
                    pota: { enabled: true, useUndocumentedApi: true, activeSpotIntervalSeconds: 60 },
                    sota: { enabled: true, activeSpotIntervalSeconds: 60, alertsIntervalSeconds: 300 },
                    wwff: { enabled: true, minRefreshSeconds: 30 },
                    parksnpeaks: { enabled: true, spotsIntervalSeconds: 60, alertsIntervalSeconds: 300 },
                },
                propagation: {
                    enabled: true,
                    swpcEnabled: true,
                    lowerPriorityWhenPoor: true,
                    showReasonTooltips: true,
                    useRbnEvidence: true,
                },
                rbn: {
                    enabled: true,
                    ingestFromExistingCluster: true,
                    directTelnet: false,
                    directTelnetHost: 'telnet.reversebeacon.net',
                    directTelnetPort: 7000,
                    directFt8TelnetHost: 'telnet.reversebeacon.net',
                    directFt8TelnetPort: 7001,
                    ownCallOnlyProcessing: true,
                    stationCalls: [],
                },
            },
        },

        showConfigModal: false,
        configDialogVisible: false,
        activeConfigTab: 'database',
        configMessage: null,
        configTabs: [
            { id: 'database', name: 'Database' },
            { id: 'station', name: 'Station & Cluster' },
            { id: 'flex', name: 'Flex & UDP' },
            { id: 'rotor', name: 'Rotor' },
            { id: 'winkeyer', name: 'WinKeyer' },
            { id: 'wsjtx', name: 'WSJT-X' },
            { id: 'cty', name: 'CTY / Paths' },
            { id: 'logging', name: 'Logging' },
            { id: 'activity', name: 'Activity Intel' },
            { id: 'colours', name: 'Colours' },
            { id: 'specials', name: 'Special Stations' },
        ],

        availableSpecialsList: ['POTA', 'SOTA', 'IOTA', 'WWFF', 'CASTLE', 'LIGHTHOUSE', 'CONTEST', 'IARU'],
        enabledSpecials: ['POTA', 'SOTA', 'IOTA', 'WWFF', 'CONTEST', 'LIGHTHOUSE', 'CASTLE', 'IARU'],
        newSpecialName: '',
    },

    computed: {
        rotorEnabled() {
            return this.configData.ROTOR_ENABLED === true;
        },

        wavelogEnabled() {
            return this.configData.WAVELOG_ENABLED === true;
        },

        qrzEnabled() {
            return this.configData.QRZ_ENABLED === true;
        },

        clusterEnabled() {
            return this.configData.CLUSTER_ENABLED === true;
        },

        winKeyerEnabled() {
            return this.configData.WINKEYER_ENABLED === true;
        },
    },

    methods: {
        async showConfigDialog() {
            console.log('Opening configuration dialog...');
            this.configMessage = null;
            this.activeConfigTab = 'database';

            try {
                const response = await fetch('/api/config');
                const data = await response.json();

                if (data.success) {
                    this.configData = { ...this.configData, ...data.config };
                    this.syncActivityIntelligenceConfigFromSettings();
                    console.log('Configuration loaded:', this.configData);
                }
            } catch (error) {
                console.error('Failed to load configuration:', error);
                this.configMessage = {
                    type: 'error',
                    text: 'Failed to load configuration: ' + error.message,
                };
            }

            this.showConfigModal = true;
            this.configDialogVisible = true;
        },

        closeConfigDialog() {
            console.log('Closing configuration dialog');
            this.showConfigModal = false;
            this.configDialogVisible = false;
            this.configMessage = null;
        },

        async saveConfiguration() {
            console.log('Saving configuration...', this.configData);
            this.configMessage = null;

            try {
                const response = await fetch('/api/config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ config: this.configData }),
                });

                const data = await response.json();

                if (data.success) {
                    console.log('Configuration saved successfully');
                    this.configMessage = {
                        type: 'success',
                        text: 'Configuration saved successfully!',
                    };

                    this.syncWinKeyerConfigFromSettings();
                    this.syncActivityIntelligenceConfigFromSettings();

                    setTimeout(() => {
                        if (this.showConfigModal) {
                            this.closeConfigDialog();
                        }
                    }, 3000);
                } else {
                    console.error('Failed to save configuration:', data.message);
                    this.configMessage = {
                        type: 'error',
                        text: 'Failed to save configuration: ' + (data.message || 'Unknown error'),
                    };
                }
            } catch (error) {
                console.error('Error saving configuration:', error);
                this.configMessage = {
                    type: 'error',
                    text: 'Error saving configuration: ' + error.message,
                };
            }
        },

        toggleClusterPrimary(idx) {
            if (!this.configData.CLUSTERS) return;

            for (let i = 0; i < this.configData.CLUSTERS.length; i++) {
                this.configData.CLUSTERS[i].use_as_failover = i !== idx;
            }
            console.log(`Cluster ${idx + 1} set as primary`);
        },

        addSpecial(special) {
            if (!this.enabledSpecials.includes(special)) {
                this.enabledSpecials.push(special);
                console.log(`Added special: ${special}`);
            }
        },

        removeSpecial(special) {
            const idx = this.enabledSpecials.indexOf(special);
            if (idx > -1) {
                this.enabledSpecials.splice(idx, 1);
                console.log(`Removed special: ${special}`);
            }
        },

        async loadConfig() {
            try {
                const response = await fetch('/api/config');
                if (response.ok) {
                    const data = await response.json();
                    if (data.success && data.config) {
                        console.log('Configuration loaded:', data.config);
                        this.configData = { ...this.configData, ...data.config };
                        console.log('ROTOR_ENABLED from config:', this.configData.ROTOR_ENABLED);
                        this.syncWinKeyerConfigFromSettings();
                        this.syncActivityIntelligenceConfigFromSettings();
                        if (this.loadActivityIntelligence) {
                            this.loadActivityIntelligence();
                        }
                    }
                }
            } catch (error) {
                console.warn('Could not load config:', error);
            }
        },

        syncWinKeyerConfigFromSettings() {
            this.winkeyer.config.port = this.configData.WINKEYER_PORT || 'COM3';
            this.winkeyer.config.baudRate = this.configData.WINKEYER_BAUDRATE || 1200;
            this.winkeyer.config.defaultWpm = this.configData.WINKEYER_DEFAULT_WPM || 20;
            if (this.configData.WINKEYER_MEMORIES) {
                this.winkeyer.memories = this.configData.WINKEYER_MEMORIES;
            }
            console.log('WinKeyer config synced, enabled:', this.winKeyerEnabled);
        },

        syncActivityIntelligenceConfigFromSettings() {
            const defaults = window.RadioControlConfig.data.configData.ACTIVITY_INTELLIGENCE;
            this.configData.ACTIVITY_INTELLIGENCE = {
                ...defaults,
                ...(this.configData.ACTIVITY_INTELLIGENCE || {}),
                dxpeditions: {
                    ...defaults.dxpeditions,
                    ...((this.configData.ACTIVITY_INTELLIGENCE || {}).dxpeditions || {}),
                },
                contests: {
                    ...defaults.contests,
                    ...((this.configData.ACTIVITY_INTELLIGENCE || {}).contests || {}),
                },
                portable: {
                    ...defaults.portable,
                    ...((this.configData.ACTIVITY_INTELLIGENCE || {}).portable || {}),
                    pota: {
                        ...defaults.portable.pota,
                        ...(((this.configData.ACTIVITY_INTELLIGENCE || {}).portable || {}).pota || {}),
                    },
                    sota: {
                        ...defaults.portable.sota,
                        ...(((this.configData.ACTIVITY_INTELLIGENCE || {}).portable || {}).sota || {}),
                    },
                    wwff: {
                        ...defaults.portable.wwff,
                        ...(((this.configData.ACTIVITY_INTELLIGENCE || {}).portable || {}).wwff || {}),
                    },
                    parksnpeaks: {
                        ...defaults.portable.parksnpeaks,
                        ...(((this.configData.ACTIVITY_INTELLIGENCE || {}).portable || {}).parksnpeaks || {}),
                    },
                },
                propagation: {
                    ...defaults.propagation,
                    ...((this.configData.ACTIVITY_INTELLIGENCE || {}).propagation || {}),
                },
                rbn: {
                    ...defaults.rbn,
                    ...((this.configData.ACTIVITY_INTELLIGENCE || {}).rbn || {}),
                },
            };
        },
    },
};
