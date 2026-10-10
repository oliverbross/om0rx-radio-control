// Configuration modal state, computed flags, and API helpers.

console.log('Loading config-modal.js module...');

window.RadioControlConfig = {
    data: {
        configData: {
            ROTOR_ENABLED: false,
            WAVELOG_ENABLED: true,
            QRZ_ENABLED: true,
            CLUSTER_ENABLED: false,
            DATABASE_BACKEND: 'auto',
            POSTGRES_DSN: '',
            POSTGRES_HOST: '',
            POSTGRES_PORT: 5432,
            POSTGRES_DB: '',
            POSTGRES_USER: '',
            POSTGRES_PASSWORD: '',
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
            WSJTX_BRIDGE_COMMAND_URL: 'http://127.0.0.1:8092/wsjtx/command',
            WSJTX_AUTO_LOG: true,
            WSJTX_AUTO_ROTATE: true,
            WSJTX_AUTO_CQ_TEXT: 'CQ OM0RX JN88',
            WSJTX_AUTO_CQ_SEND: false,
            WSJTX_AUTO_ANSWER_TEST_MESSAGE: 'CQ EA1TEST IN80',
            WSJTX_AUTO_ANSWER_TEST_CALL: 'EA1TEST',
            WSJTX_AUTO_ANSWER_TEST_GRID: 'IN80',
            WSJTX_AUTO_ANSWER_TEST_DF: 1500,
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
            FLEX_ANTENNA_POLICY: {
                enabled: true,
                bands: {
                    '160m': 'ANT2',
                    '80m': 'ANT2',
                    '60m': 'ANT2',
                    '40m': 'ANT2',
                    '30m': 'ANT2',
                    '20m': 'ANT1',
                    '17m': 'ANT1',
                    '15m': 'ANT1',
                    '12m': 'ANT1',
                    '10m': 'ANT1',
                },
            },
            KPA500_ENABLED: false,
            KPA500_PORT: 'COM6',
            KPA500_BAUDRATE: 38400,
            DIGITAL_KPA_POLICY: 'operate',
            KAT500_ENABLED: false,
            KAT500_PORT: 'COM11',
            KAT500_BAUDRATE: 38400,
            ELECRAFT_FOLLOW_RADIO: true,
            KAT500_ANTENNA_POLICY: {
                '160m': 2, '80m': 2, '60m': 2, '40m': 2, '30m': 2,
                '20m': 1, '17m': 1, '15m': 1, '12m': 1, '10m': 1, '6m': 1,
            },
            KAT500_ANTENNA_NAMES: {
                '1': 'KAT ANT1', '2': 'KAT ANT2', '3': 'KAT ANT3',
            },
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
        digitalEngineStatus: null,
        digitalEngineChoice: 'none',
        digitalEngineBusy: false,
        digitalEngineMessage: '',
        mshvAutoDxSettings: null,
        mshvAutoDxBusy: false,
        mshvAutoDxMessage: '',
        mshvAutoDxDirty: false,
        mshvAutoDxSaveTimer: null,
        mshvAutoDxRevision: 0,
        mshvAutoDxSavedRevision: 0,
        configDialogVisible: false,
        activeConfigTab: 'database',
        configMessage: null,
        postgresConnectionTesting: false,
        postgresConnectionTest: null,
        wsjtxHealth: null,
        wsjtxHealthLoading: false,
        wsjtxLaunchLoading: false,
        wsjtxPreflightLoading: false,
        wsjtxPreflight: null,
        wsjtxLaunchResult: null,
        wsjtxLaunchLogs: null,
        wsjtxLaunchLogsLoading: false,
        wsjtxHealthMessage: null,
        wsjtxTimelineFilter: '',
        elecraftStatus: null,
        elecraftStatusLoading: false,
        elecraftActionLoading: false,
        elecraftStatusTimer: null,
        configTabs: [
            { id: 'database', name: 'Database' },
            { id: 'station', name: 'Station & Cluster' },
            { id: 'flex', name: 'Flex & UDP' },
            { id: 'elecraft', name: 'Elecraft' },
            { id: 'rotor', name: 'Rotor' },
            { id: 'winkeyer', name: 'WinKeyer' },
            { id: 'wsjtx', name: 'Digital engines' },
            { id: 'mshv', name: 'MSHV hunting' },
            { id: 'cty', name: 'CTY / Paths' },
            { id: 'logging', name: 'Logging' },
            { id: 'activity', name: 'Activity Intel' },
            { id: 'colours', name: 'Colours' },
            { id: 'specials', name: 'Special Stations' },
        ],

        availableSpecialsList: ['POTA', 'SOTA', 'IOTA', 'WWFF', 'BUNKER', 'CASTLE', 'LIGHTHOUSE', 'CONTEST', 'IARU'],
        enabledSpecials: ['POTA', 'SOTA', 'IOTA', 'WWFF', 'BUNKER', 'CONTEST', 'LIGHTHOUSE', 'CASTLE', 'IARU'],
        newSpecialName: '',
        configuredSecretKeys: [],
        secretUnchangedSentinel: '__OM0RX_SECRET_UNCHANGED__',
    },

    computed: {
        mshvOwnsDigitalPlanner() {
            // Historical template name: both MSHV ownership and the disabled
            // provider must keep every OM0RX/WSJT-Z TX control inert.
            return (this.digitalEngineStatus?.selected_engine || 'none') !== 'wsjtz';
        },
        digitalEngineDisabled() {
            return this.digitalEngineStatus?.selected_engine === 'none';
        },
        digitalEngineBlocksOm0rx() {
            return (this.digitalEngineStatus?.selected_engine || 'none') !== 'wsjtz';
        },
        wsjtzOwnsDigitalPlanner() {
            return this.digitalEngineStatus?.selected_engine === 'wsjtz';
        },
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
        normalizeMshvAwardSettings(settings = {}) {
            return {
                ...settings,
                award_hunting: {
                    enabled: true,
                    stack_scores: true,
                    new_dxcc_weight: 10000,
                    new_dxcc_band_weight: 1000,
                    unconfirmed_dxcc_weight: 8500,
                    new_continent_weight: 2500,
                    new_cq_zone_weight: 2200,
                    new_itu_zone_weight: 2000,
                    new_grid_weight: 500,
                    ...(settings.award_hunting || {}),
                },
                reference_hunting: {
                    enabled: true,
                    pota_enabled: true,
                    sota_enabled: true,
                    wwff_enabled: true,
                    new_reference_weight: 2500,
                    new_reference_band_weight: 1000,
                    new_reference_band_mode_weight: 500,
                    pota_weight: 1800,
                    sota_weight: 1800,
                    wwff_weight: 1400,
                    max_activation_age_seconds: 900,
                    require_local_decode: true,
                    ...(settings.reference_hunting || {}),
                },
                propagation_adaptation: {
                    enabled: true,
                    window_seconds: 900,
                    unique_decode_weight: 20,
                    distant_decode_weight: 40,
                    successful_qso_weight: 250,
                    max_band_boost: 1500,
                    ...(settings.propagation_adaptation || {}),
                },
                pileup_strategy: {
                    enabled: true,
                    audio_offsets_hz: [0, -120, 120, -240, 240],
                    rotate_after_attempts: 2,
                    revisit_delay_seconds: 120,
                    ...(settings.pileup_strategy || {}),
                },
                directed_callers: {
                    enabled: true,
                    inbox_size: 8,
                    max_age_seconds: 90,
                    ...(settings.directed_callers || {}),
                },
                campaign: {
                    profile: 'balanced',
                    dxcc_weight_percent: 100,
                    state_weight_percent: 100,
                    zone_weight_percent: 100,
                    grid_weight_percent: 100,
                    reference_weight_percent: 100,
                    ...(settings.campaign || {}),
                },
                outcome_learning: {
                    enabled: true,
                    telemetry_file: 'logs/autodx-outcomes.jsonl',
                    ...(settings.outcome_learning || {}),
                },
            };
        },

        mshvAudioOffsetsText() {
            return (this.mshvAutoDxSettings?.pileup_strategy?.audio_offsets_hz || []).join(', ');
        },

        applyMshvCampaignProfile(profile) {
            const campaign = this.mshvAutoDxSettings?.campaign;
            if (!campaign) return;
            const profiles = {
                balanced: [100, 100, 100, 100, 100],
                'dxcc-challenge': [175, 75, 100, 75, 75],
                'five-band-dxcc': [200, 50, 75, 50, 50],
                'worked-all-states': [75, 200, 75, 75, 50],
                waz: [75, 50, 200, 50, 50],
                'itu-zones': [75, 50, 200, 50, 50],
                grids: [75, 50, 50, 200, 50],
                references: [75, 50, 50, 50, 200],
            };
            campaign.profile = String(profile || 'custom');
            const values = profiles[campaign.profile];
            if (values) {
                [
                    campaign.dxcc_weight_percent,
                    campaign.state_weight_percent,
                    campaign.zone_weight_percent,
                    campaign.grid_weight_percent,
                    campaign.reference_weight_percent,
                ] = values;
            }
            this.queueMshvAutoDxSave();
        },

        markMshvCampaignCustom() {
            if (this.mshvAutoDxSettings?.campaign) {
                this.mshvAutoDxSettings.campaign.profile = 'custom';
            }
        },

        updateMshvAudioOffsets(value) {
            if (!this.mshvAutoDxSettings?.pileup_strategy) return false;
            const tokens = String(value || '').split(',').map(item => item.trim()).filter(Boolean);
            const offsets = tokens.map(Number);
            if (!offsets.length || offsets.length > 16 || offsets.some(item => !Number.isInteger(item) || item < -2400 || item > 2400)) {
                this.mshvAutoDxMessage = 'Enter 1–16 whole-number audio offsets from −2400 to 2400 Hz.';
                return false;
            }
            this.mshvAutoDxSettings.pileup_strategy.audio_offsets_hz = [...new Set(offsets)];
            this.mshvAutoDxMessage = '';
            return true;
        },

        queueMshvAutoDxSave() {
            this.mshvAutoDxDirty = true;
            this.mshvAutoDxRevision += 1;
            this.scheduleMshvAutoDxSave();
        },

        scheduleMshvAutoDxSave() {
            if (this.mshvAutoDxSaveTimer) clearTimeout(this.mshvAutoDxSaveTimer);
            this.mshvAutoDxSaveTimer = setTimeout(() => {
                this.mshvAutoDxSaveTimer = null;
                this.saveMshvAutoDxSettings();
            }, 450);
        },

        mshvEffectiveAutoDxText(settings = this.mshvAutoDxSettings) {
            if (!settings?.effective) return 'engine stopped';
            if (typeof settings.effective.effective_enabled !== 'boolean') return 'unknown';
            return settings.effective.effective_enabled ? 'on' : 'off';
        },

        mshvRuntimeParityText(settings = this.mshvAutoDxSettings) {
            const parity = settings?.runtime_parity;
            if (!parity || !['match', 'drift'].includes(parity.status)) return 'unknown';
            if (parity.status === 'match') return 'matched';
            return `drift: ${(parity.drift || []).join(', ') || 'unspecified'}`;
        },

        mshvAutoDxStatus() {
            return this.digitalEngineStatus?.autodx_status || {};
        },

        mshvTargetText() {
            const status = this.mshvAutoDxStatus();
            const target = status.target;
            if (!target) return 'none';
            if (typeof target === 'string') return target;
            const band = status.active_schedule?.band || (target.band_index != null ? `band ${target.band_index}` : '');
            return [target.call, band, target.grid].filter(Boolean).join(' · ') || 'none';
        },

        mshvTimeText(value) {
            if (value == null || value === '') return '—';
            if (typeof value === 'number') return `${Math.max(0, Math.round(value))} s`;
            const parsed = new Date(value);
            return Number.isNaN(parsed.valueOf()) ? String(value) : parsed.toLocaleTimeString();
        },

        async loadDigitalEngineStatus() {
            try {
                const response = await fetch('/api/digital/status');
                const status = await response.json();
                if (!response.ok) throw new Error(status.detail || 'Engine status unavailable');
                this.digitalEngineStatus = status;
                this.digitalEngineChoice = status.selected_engine || status.provider || 'none';
                window.om0rxDigitalEngine = this.digitalEngineChoice;
                window.dispatchEvent(new CustomEvent('digital-engine-status', { detail: status }));
                if (this.configDialogVisible && ['wsjtx', 'mshv'].includes(this.activeConfigTab) && this.digitalEngineChoice === 'mshv_auto_dx') {
                    await this.loadMshvAutoDxSettings();
                }
                return status;
            } catch (error) {
                this.digitalEngineMessage = error.message;
                return null;
            }
        },

        async launchDigitalEngine(engine) {
            const provider = String(engine || '').trim();
            if (!['wsjtz', 'mshv_auto_dx'].includes(provider)) {
                this.digitalEngineMessage = 'Unknown digital engine.';
                return null;
            }
            this.digitalEngineChoice = provider;
            return this.digitalEngineAction('start', provider);
        },

        async digitalEngineAction(action, engine = this.digitalEngineChoice) {
            this.digitalEngineBusy = true;
            this.digitalEngineMessage = '';
            try {
                const response = await fetch(`/api/digital/${action}`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ engine }),
                });
                const result = await response.json();
                if (!response.ok || result.success === false) {
                    throw new Error(result.message || result.detail || result.error || `Engine ${action} failed`);
                }
                if (action === 'halt-tx' || action === 'halt') {
                    const accepted = result.command_accepted ? 'halt command accepted' : 'no halt command accepted';
                    const confirmed = result.idle_confirmed ? 'RF idle freshly confirmed' : 'RF idle confirmation pending';
                    this.digitalEngineMessage = `${accepted}; ${confirmed}.`;
                } else {
                    this.digitalEngineMessage = result.startup?.starting
                        ? 'Engine process accepted and is still starting; TX remains unavailable until heartbeat/readiness is confirmed.'
                        : (result.message || `Engine ${action} completed.`);
                }
                await this.loadDigitalEngineStatus();
            } catch (error) {
                this.digitalEngineMessage = error.message;
                await this.loadDigitalEngineStatus();
            } finally {
                this.digitalEngineBusy = false;
            }
        },

        digitalEngineHealthText(key) {
            const value = this.digitalEngineStatus?.health?.[key];
            if (value == null) return 'not reported';
            if (typeof value === 'object') return value.detail || value.status || value.state || 'not reported';
            return String(value);
        },

        async loadMshvAutoDxSettings(force = false) {
            if (this.mshvAutoDxDirty && !force) return this.mshvAutoDxSettings;
            this.mshvAutoDxBusy = true;
            this.mshvAutoDxMessage = '';
            try {
                const response = await fetch('/api/digital/mshv-settings');
                const result = await response.json();
                if (!response.ok || result.success === false) {
                    throw new Error(result.detail || result.error || 'MSHV Auto DX settings unavailable');
                }
                this.mshvAutoDxSettings = this.normalizeMshvAwardSettings(result);
                this.mshvAutoDxDirty = false;
                this.mshvAutoDxRevision = 0;
                this.mshvAutoDxSavedRevision = 0;
                return result;
            } catch (error) {
                this.mshvAutoDxMessage = error.message;
                return null;
            } finally {
                this.mshvAutoDxBusy = false;
            }
        },

        async saveMshvAutoDxSettings() {
            if (!this.mshvAutoDxSettings) return;
            if (this.mshvAutoDxBusy) {
                this.scheduleMshvAutoDxSave();
                return;
            }
            if (this.mshvAutoDxSaveTimer) {
                clearTimeout(this.mshvAutoDxSaveTimer);
                this.mshvAutoDxSaveTimer = null;
            }
            this.mshvAutoDxBusy = true;
            this.mshvAutoDxMessage = '';
            const savingRevision = this.mshvAutoDxRevision;
            try {
                const settings = this.mshvAutoDxSettings;
                const { normal_call_seconds: _derivedAttemptBudget, ...writableAutomationTiming } = settings.automation_timing || {};
                const response = await fetch('/api/digital/mshv-settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        enabled: settings.desired?.enabled === true,
                        callsign: settings.callsign,
                        grid: settings.grid,
                        min_snr: settings.min_snr,
                        grid_chase_us_only: settings.grid_chase_us_only,
                        band_switching_enabled: settings.band_switching_enabled,
                        automation_timing: writableAutomationTiming,
                        band_schedules: JSON.parse(JSON.stringify(settings.band_schedules)),
                        enabled_bands: [...settings.enabled_bands],
                        auto_dx_modes: [...settings.auto_dx_modes],
                        atno_chase_type: settings.atno_chase_type,
                        scarce_threshold: settings.scarce_threshold,
                        filter_matrix_enabled: settings.filter_matrix_enabled,
                        filter_new: { ...(settings.filter_new || {}) },
                        filter_new_on_band: { ...(settings.filter_new_on_band || {}) },
                        filter_continents: [...(settings.filter_continents || [])],
                        allow_band_dxcc_outside_continent: settings.allow_band_dxcc_outside_continent !== false,
                        filter_lotw_only: settings.filter_lotw_only,
                        treat_73_as_cq: settings.treat_73_as_cq,
                        watch_unconfirmed_dxcc: settings.watch_unconfirmed_dxcc,
                        selection_order: settings.selection_order || 'score',
                        call_window_seconds: settings.call_window_seconds,
                        max_consecutive_windows: settings.max_consecutive_windows,
                        same_target_revisit_delay_seconds: settings.same_target_revisit_delay_seconds,
                        recent_qso_cooldown_seconds: settings.recent_qso_cooldown_seconds,
                        min_band_dwell_seconds: settings.min_band_dwell_seconds,
                        engaged_completion_grace_seconds: settings.engaged_completion_grace_seconds,
                        spot_sources: JSON.parse(JSON.stringify(settings.spot_sources)),
                        target_priority: { ...settings.target_priority },
                        us_states: JSON.parse(JSON.stringify(settings.us_states || {
                            enabled: true, minimum_worked: 3, require_confirmation: true,
                            prefer_lotw: true, missing_confirmation_weight: 8500,
                            under_quota_weight: 7000, bands: [3, 4, 6, 7, 8, 9, 10, 11, 12],
                        })),
                        dxpedition: JSON.parse(JSON.stringify(settings.dxpedition || {})),
                        cluster_chase: JSON.parse(JSON.stringify(settings.cluster_chase || {})),
                        award_hunting: JSON.parse(JSON.stringify(settings.award_hunting)),
                        reference_hunting: JSON.parse(JSON.stringify(settings.reference_hunting)),
                        propagation_adaptation: JSON.parse(JSON.stringify(settings.propagation_adaptation)),
                        pileup_strategy: JSON.parse(JSON.stringify(settings.pileup_strategy)),
                        directed_callers: JSON.parse(JSON.stringify(settings.directed_callers)),
                        campaign: JSON.parse(JSON.stringify(settings.campaign)),
                        outcome_learning: JSON.parse(JSON.stringify(settings.outcome_learning)),
                    }),
                });
                const result = await response.json();
                if (!response.ok || result.success === false) {
                    throw new Error(result.detail || result.error || 'MSHV Auto DX settings were not saved');
                }
                this.mshvAutoDxSavedRevision = savingRevision;
                if (this.mshvAutoDxRevision === savingRevision) {
                    this.mshvAutoDxSettings = this.normalizeMshvAwardSettings(result);
                    this.mshvAutoDxDirty = false;
                    this.mshvAutoDxMessage = result.message || 'MSHV hunting settings applied and saved.';
                }
            } catch (error) {
                this.mshvAutoDxMessage = error.message;
            } finally {
                this.mshvAutoDxBusy = false;
                if (this.mshvAutoDxRevision > savingRevision) this.scheduleMshvAutoDxSave();
            }
        },

        addMshvDxClusterServer() {
            if (!this.mshvAutoDxSettings?.spot_sources?.dx_cluster) return;
            this.mshvAutoDxSettings.spot_sources.dx_cluster.servers.push({
                name: 'DX Cluster', host: 'localhost', port: 7300, enabled: false,
            });
            this.queueMshvAutoDxSave();
        },

        removeMshvDxClusterServer(index) {
            if (!this.mshvAutoDxSettings?.spot_sources?.dx_cluster) return;
            this.mshvAutoDxSettings.spot_sources.dx_cluster.servers.splice(index, 1);
            this.queueMshvAutoDxSave();
        },
        async showConfigDialog(initialTab = 'database') {
            console.log('Opening configuration dialog...');
            this.configMessage = null;
            this.activeConfigTab = initialTab || 'database';

            try {
                const response = await fetch('/api/config');
                const data = await response.json();

                if (data.success) {
                    this.configData = { ...this.configData, ...data.config };
                    this.captureConfiguredSecrets(data.config);
                    this.syncActivityIntelligenceConfigFromSettings();
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
            this.activeConfigTab = initialTab || this.activeConfigTab || 'database';
            if (this.activeConfigTab === 'wsjtx') {
                this.loadWsjtxHealth();
            } else if (this.activeConfigTab === 'mshv') {
                this.digitalEngineChoice = 'mshv_auto_dx';
                this.loadDigitalEngineStatus();
                this.loadMshvAutoDxSettings(true);
            } else if (this.activeConfigTab === 'elecraft') {
                this.startElecraftPolling();
            }
        },

        closeConfigDialog() {
            console.log('Closing configuration dialog');
            this.showConfigModal = false;
            this.configDialogVisible = false;
            this.configMessage = null;
            this.stopElecraftPolling();
        },

        async saveConfiguration() {
            console.log('Saving configuration');
            this.configMessage = null;

            try {
                const configForSave = { ...this.configData };
                for (const key of this.configuredSecretKeys || []) {
                    if (configForSave[key] === '' || configForSave[key] == null ||
                        (Array.isArray(configForSave[key]) && configForSave[key].length === 0)) {
                        configForSave[key] = this.secretUnchangedSentinel;
                    }
                }
                const response = await fetch('/api/config', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ config: configForSave }),
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
                    if (this.activeConfigTab === 'elecraft') {
                        await this.loadElecraftStatus();
                    }

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

        captureConfiguredSecrets(publicConfig = {}) {
            this.secretUnchangedSentinel = publicConfig.SECRET_UNCHANGED_SENTINEL || this.secretUnchangedSentinel;
            this.configuredSecretKeys = Object.entries(publicConfig)
                .filter(([key, value]) => key.endsWith('_CONFIGURED') && value === true)
                .map(([key]) => key.slice(0, -'_CONFIGURED'.length));
            for (const key of this.configuredSecretKeys) {
                this.configData[key] = key === 'CLUSTERS' ? [] : '';
            }
            delete this.configData.SECRET_UNCHANGED_SENTINEL;
        },

        async testPostgresConnection() {
            this.postgresConnectionTesting = true;
            this.postgresConnectionTest = null;

            try {
                const response = await fetch('/api/config/postgres/test', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ config: this.configData }),
                });
                const data = await response.json();
                this.postgresConnectionTest = {
                    success: data.success === true,
                    message: data.message || (data.success ? 'PostgreSQL connection ok' : 'PostgreSQL connection failed'),
                };
            } catch (error) {
                this.postgresConnectionTest = {
                    success: false,
                    message: 'PostgreSQL connection failed: ' + error.message,
                };
            } finally {
                this.postgresConnectionTesting = false;
            }
        },

        selectConfigTab(tabId) {
            this.activeConfigTab = tabId;
            this.stopElecraftPolling();
            if (tabId === 'wsjtx') {
                this.loadWsjtxHealth();
            } else if (tabId === 'mshv') {
                this.digitalEngineChoice = 'mshv_auto_dx';
                this.loadDigitalEngineStatus();
                this.loadMshvAutoDxSettings(true);
            } else if (tabId === 'elecraft') {
                this.startElecraftPolling();
            }
        },

        startElecraftPolling() {
            this.stopElecraftPolling();
            this.loadElecraftStatus();
            this.elecraftStatusTimer = setInterval(() => {
                if (this.configDialogVisible && this.activeConfigTab === 'elecraft') {
                    this.loadElecraftStatus(false);
                }
            }, 2500);
        },

        stopElecraftPolling() {
            if (this.elecraftStatusTimer) {
                clearInterval(this.elecraftStatusTimer);
                this.elecraftStatusTimer = null;
            }
        },

        async loadElecraftStatus(showLoading = true, refreshHardware = showLoading) {
            if (showLoading) this.elecraftStatusLoading = true;
            try {
                const response = await fetch(`/api/elecraft/status?refresh=${refreshHardware ? 'true' : 'false'}`);
                const data = await response.json();
                if (!response.ok || !data.success) {
                    throw new Error(data.detail || data.message || 'Status request failed');
                }
                this.elecraftStatus = data.status;
            } catch (error) {
                this.elecraftStatus = {
                    ...(this.elecraftStatus || {}),
                    error: error.message,
                };
            } finally {
                if (showLoading) this.elecraftStatusLoading = false;
            }
        },

        async elecraftAction(path, body = null) {
            this.elecraftActionLoading = true;
            this.configMessage = null;
            try {
                const options = { method: 'POST', headers: {} };
                if (body !== null) {
                    options.headers['Content-Type'] = 'application/json';
                    options.body = JSON.stringify(body);
                }
                const response = await fetch(`/api/elecraft/${path}`, options);
                const data = await response.json();
                if (!response.ok || !data.success) {
                    throw new Error(data.detail || data.message || 'Elecraft command failed');
                }
                if (data.status) this.elecraftStatus = data.status;
                await this.loadElecraftStatus(false);
            } catch (error) {
                this.configMessage = { type: 'error', text: error.message };
            } finally {
                this.elecraftActionLoading = false;
            }
        },

        getWsjtxHealthColor() {
            const status = (this.wsjtxHealth && this.wsjtxHealth.status) || '';
            if (status === 'ok') return '#10b981';
            if (status === 'off') return '#888';
            if (status === 'warn') return '#f59e0b';
            return '#4a9eff';
        },

        formatWsjtxBool(value, okLabel = 'yes', noLabel = 'no') {
            return value ? okLabel : noLabel;
        },

        formatWsjtxClient() {
            const health = this.wsjtxHealth || {};
            const client = health.client || {};
            if (!client.id) return 'No client seen';
            const age = Number.isFinite(Number(health.last_seen_ms))
                ? `, last seen ${Math.round(Number(health.last_seen_ms) / 1000)}s ago`
                : '';
            return `${client.id}${age}`;
        },

        formatWsjtxProcesses() {
            const processes = (this.wsjtxHealth && this.wsjtxHealth.processes) || {};
            return `WSJT ${processes.wsjtx ? 'seen' : 'not seen'}, decoder ${processes.decoder ? 'seen' : 'not seen'}`;
        },

        formatWsjtxLastDecode() {
            const health = this.wsjtxHealth || {};
            const lastDecode = health.last_decode || {};
            if (!lastDecode.message) {
                return 'No decode seen';
            }
            const age = Number.isFinite(Number(health.last_decode_age_ms))
                ? `${Math.round(Number(health.last_decode_age_ms) / 1000)}s ago`
                : 'age unknown';
            const df = Number.isFinite(Number(lastDecode.deltaFrequency))
                ? ` @ ${lastDecode.deltaFrequency} Hz`
                : '';
            return `${lastDecode.message}${df}, ${age}`;
        },

        getWsjtxReadinessChecks() {
            return Array.isArray(this.wsjtxHealth?.checks) ? this.wsjtxHealth.checks : [];
        },

        getWsjtxPreflightChecks() {
            return Array.isArray(this.wsjtxPreflight?.checks) ? this.wsjtxPreflight.checks : [];
        },

        getWsjtxBridgeTimeline() {
            const timeline = this.wsjtxHealth?.timeline || this.wsjtxHealth?.bridge?.timeline || [];
            if (!Array.isArray(timeline)) return [];
            const query = String(this.wsjtxTimelineFilter || '').trim().toLowerCase();
            const events = query
                ? timeline.filter(event => this.getWsjtxTimelineSearchText(event).includes(query))
                : timeline;
            return events.slice(-12).reverse();
        },

        hasWsjtxBridgeTimeline() {
            const timeline = this.wsjtxHealth?.timeline || this.wsjtxHealth?.bridge?.timeline || [];
            return Array.isArray(timeline) && timeline.length > 0;
        },

        clearWsjtxTimelineFilter() {
            this.wsjtxTimelineFilter = '';
        },

        getWsjtxCommandErrorSummary() {
            const stats = this.wsjtxHealth?.bridge?.stats || {};
            const count = Number(stats.commandErrors || 0);
            if (!Number.isFinite(count) || count <= 0) return null;
            const timeline = this.wsjtxHealth?.timeline || this.wsjtxHealth?.bridge?.timeline || [];
            const failed = Array.isArray(timeline)
                ? timeline.slice().reverse().find(event => event?.success === false || event?.error)
                : null;
            const traceId = failed?.trace_id || failed?.traceId || failed?.payload?.traceId || '';
            return {
                count,
                traceId,
                title: failed ? this.formatWsjtxTimelineTitle(failed) : 'Bridge command failure',
                detail: failed ? this.formatWsjtxTimelineDetail(failed) : 'Check the bridge timeline for the failed command.',
            };
        },

        focusWsjtxCommandErrorTrace() {
            const summary = this.getWsjtxCommandErrorSummary();
            if (summary?.traceId) {
                this.wsjtxTimelineFilter = summary.traceId;
            }
        },

        getWsjtxTimelineSearchText(event) {
            const payload = event?.payload || {};
            return [
                event?.direction,
                event?.type,
                event?.command,
                event?.message,
                event?.error,
                event?.dx_call,
                event?.dx_grid,
                event?.mode,
                event?.traceId,
                event?.trace_id,
                payload.call,
                payload.callsign,
                payload.mode,
                payload.grid,
                payload.traceId,
                payload.trace_id,
            ].filter(value => value !== undefined && value !== null)
                .map(value => String(value).toLowerCase())
                .join(' ');
        },

        getWsjtxTimelineTraceId(event) {
            const payload = event?.payload || {};
            const traceId = event?.trace_id || event?.traceId || payload.traceId || payload.trace_id || '';
            return String(traceId || '').trim();
        },

        async copyWsjtxTraceToClipboard(traceId) {
            const cleanTraceId = String(traceId || '').trim();
            if (!cleanTraceId) return;
            try {
                if (navigator.clipboard?.writeText) {
                    await navigator.clipboard.writeText(cleanTraceId);
                } else {
                    const input = document.createElement('textarea');
                    input.value = cleanTraceId;
                    input.setAttribute('readonly', 'readonly');
                    input.style.position = 'fixed';
                    input.style.opacity = '0';
                    document.body.appendChild(input);
                    input.select();
                    document.execCommand('copy');
                    document.body.removeChild(input);
                }
                this.wsjtxHealthMessage = { type: 'success', text: `Copied WSJT trace ${cleanTraceId}` };
                if (typeof this.showStatus === 'function') {
                    this.showStatus(`Copied WSJT trace ${cleanTraceId}`, 'success');
                }
            } catch (error) {
                this.wsjtxHealthMessage = { type: 'error', text: 'Trace copy failed: ' + error.message };
                if (typeof this.showStatus === 'function') {
                    this.showStatus('Trace copy failed: ' + error.message, 'error');
                }
            }
        },

        formatWsjtxTimelineTitle(event) {
            if (!event) return 'event';
            const command = event.command || event.type || 'event';
            const call = event.dx_call || event.payload?.call || '';
            const mode = event.mode || event.payload?.mode || '';
            return [command, call, mode].filter(Boolean).join(' ');
        },

        formatWsjtxTimelineDetail(event) {
            if (!event) return '';
            const parts = [];
            const traceId = event.trace_id || event.traceId || event.payload?.traceId || '';
            if (traceId) parts.push(`trace ${traceId}`);
            if (event.error) {
                parts.push(event.error);
                return parts.join(' · ');
            }
            if (event.message) parts.push(event.message);
            if (event.dx_grid) parts.push(event.dx_grid);
            if (event.rx_df) parts.push(`RX ${event.rx_df}`);
            if (event.tx_df) parts.push(`TX ${event.tx_df}`);
            if (event.bytes) parts.push(`${event.bytes} bytes`);
            return parts.join(' · ') || event.label || '';
        },

        getWsjtxTimelineClass(event) {
            const direction = String(event?.direction || 'unknown').toLowerCase();
            const success = event?.success;
            const suffix = success === false ? 'fail' : (direction === 'out' ? 'out' : 'in');
            return `wsjtx-timeline-row wsjtx-timeline-${suffix}`;
        },

        getWsjtxCheckClass(check) {
            const status = String(check?.status || 'unknown').toLowerCase();
            return `wsjtx-health-check wsjtx-health-check-${status}`;
        },

        formatWsjtxCheckStatus(check) {
            const status = String(check?.status || 'unknown').toUpperCase();
            return status === 'OK' ? 'OK' : status;
        },

        getWsjtxValidationClass() {
            if (!this.wsjtxHealth) return 'wsjtx-health-state wsjtx-health-state-unknown';
            if (this.wsjtxHealth.validation?.ready) return 'wsjtx-health-state wsjtx-health-state-ok';
            if ((this.wsjtxHealth.validation?.failures || 0) > 0) return 'wsjtx-health-state wsjtx-health-state-fail';
            return 'wsjtx-health-state wsjtx-health-state-warn';
        },

        getWsjtxHealthMessageColor() {
            if (this.wsjtxHealthMessage?.type === 'success') return '#10b981';
            if (this.wsjtxHealthMessage?.type === 'warning') return '#f59e0b';
            return '#ff6b6b';
        },

        formatWsjtxValidationSummary() {
            const health = this.wsjtxHealth || {};
            const validation = health.validation || {};
            if (!this.wsjtxHealth) return 'not checked';
            if (validation.ready) {
                return 'ready for WSJT target prepare';
            }
            if (validation.critical_total) {
                return `${validation.critical_ok || 0}/${validation.critical_total} critical checks ready`;
            }
            return health.value || health.status || 'unknown';
        },

        getWsjtxPreflightClass() {
            if (!this.wsjtxPreflight) return 'wsjtx-health-state wsjtx-health-state-unknown';
            if (this.wsjtxPreflight.ready) return 'wsjtx-health-state wsjtx-health-state-ok';
            if ((this.wsjtxPreflight.validation?.failures || 0) > 0) return 'wsjtx-health-state wsjtx-health-state-fail';
            return 'wsjtx-health-state wsjtx-health-state-warn';
        },

        formatWsjtxPreflightSummary() {
            const preflight = this.wsjtxPreflight || {};
            const validation = preflight.validation || {};
            if (!this.wsjtxPreflight) return '';
            if (preflight.ready) {
                return 'launch self-test passed';
            }
            if (validation.critical_total) {
                return `${validation.critical_ok || 0}/${validation.critical_total} launch checks ready`;
            }
            return 'launch self-test incomplete';
        },

        getWsjtxLaunchResultClass() {
            if (!this.wsjtxLaunchResult) return 'wsjtx-health-state wsjtx-health-state-unknown';
            if (this.wsjtxLaunchResult.success === false) return 'wsjtx-health-state wsjtx-health-state-fail';
            return 'wsjtx-health-state wsjtx-health-state-ok';
        },

        formatWsjtxLaunchSummary() {
            const result = this.wsjtxLaunchResult || {};
            if (result.already_running) {
                return 'engine already running';
            }
            if (result.pid) {
                return `engine launched: PID ${result.pid}`;
            }
            if (Array.isArray(result.existing_pids) && result.existing_pids.length) {
                return `existing PID ${result.existing_pids.join(', ')}`;
            }
            return result.success === false ? 'engine launch failed' : 'launch command completed';
        },

        formatWsjtxLaunchPids() {
            const result = this.wsjtxLaunchResult || {};
            const pids = [];
            if (result.pid) pids.push(result.pid);
            if (Array.isArray(result.existing_pids)) {
                result.existing_pids.forEach(pid => {
                    if (pid && !pids.includes(pid)) pids.push(pid);
                });
            }
            return pids.length ? pids.join(', ') : 'not reported';
        },

        formatWsjtxLaunchCommand() {
            const command = this.wsjtxLaunchResult?.command;
            if (Array.isArray(command)) return command.join(' ');
            return command || 'not reported';
        },

        getWsjtxLaunchLogRows() {
            const result = this.wsjtxLaunchResult || {};
            return [
                { label: 'stdout', path: result.stdout_log || '' },
                { label: 'stderr', path: result.stderr_log || '' },
            ].filter(row => row.path);
        },

        getWsjtxLaunchLogSections() {
            const logs = this.wsjtxLaunchLogs?.logs || {};
            return ['stdout', 'stderr'].map(key => {
                const log = logs[key] || {};
                const lines = Array.isArray(log.lines) ? log.lines : [];
                return {
                    key,
                    label: `${key} log`,
                    path: log.path || this.wsjtxLaunchResult?.[`${key}_log`] || '',
                    exists: log.exists === true,
                    size: Number(log.size || 0),
                    modified: log.modified || '',
                    text: log.text || lines.join('\n') || '(no recent output)',
                    truncated: log.truncated === true,
                };
            }).filter(section => section.path);
        },

        async loadWsjtxLaunchLogs(lines = 120) {
            this.wsjtxLaunchLogsLoading = true;
            try {
                const payload = this.getWsjtxLaunchPayload();
                const params = new URLSearchParams({
                    rigName: payload.rigName || 'OM0RX-WSJT-Z',
                    lines: String(lines),
                });
                const response = await fetch(`/api/wsjtx/launch-logs?${params.toString()}`);
                const data = await response.json();
                if (!response.ok || data.success === false) {
                    throw new Error(this.formatWsjtxCommandError(data, 'WSJT launch logs unavailable'));
                }
                this.wsjtxLaunchLogs = data;
                return data;
            } catch (error) {
                this.wsjtxHealthMessage = {
                    type: 'error',
                    text: `WSJT launch logs unavailable: ${error.message}`,
                };
                throw error;
            } finally {
                this.wsjtxLaunchLogsLoading = false;
            }
        },

        formatWsjtxCommandError(data, fallback) {
            const detail = data && data.detail;
            if (typeof detail === 'string') return detail;
            if (detail && typeof detail === 'object') {
                return detail.error || detail.message || JSON.stringify(detail);
            }
            return (data && (data.message || data.error)) || fallback;
        },

        getWsjtxLaunchPayload() {
            return {
                engine: 'wsjtz',
                rigName: 'OM0RX-WSJT-Z',
                configName: 'OM0RX-WSJT-Z',
                testMode: false,
            };
        },

        getWsjtzLaunchPayload() {
            return this.getWsjtxLaunchPayload();
        },

        async runWsjtxLaunchPreflight(options = {}) {
            const response = await fetch('/api/wsjtx/launch-preflight', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.getWsjtxLaunchPayload()),
            });
            const data = await response.json();
            this.wsjtxPreflight = data;
            if (data.health) {
                this.wsjtxHealth = data.health;
            }
            if (!response.ok || data.success === false) {
                throw new Error(this.formatWsjtxCommandError(data, 'WSJT-Z launch self-test failed'));
            }
            if (options.requireReady && !data.ready) {
                throw new Error(`Critical launch checks failed: ${this.formatWsjtxPreflightSummary()}`);
            }
            return data;
        },

        async runWsjtzLaunchPreflight(options = {}) {
            return this.runWsjtxLaunchPreflight(options);
        },

        async launchPatchedWsjtxEngine() {
            this.wsjtxLaunchLoading = true;
            this.wsjtxHealthMessage = null;
            this.wsjtxLaunchResult = null;
            this.wsjtxLaunchLogs = null;
            try {
                this.wsjtxPreflightLoading = true;
                const preflight = await this.runWsjtxLaunchPreflight({ requireReady: true });
                this.wsjtxPreflightLoading = false;
                this.wsjtxHealthMessage = {
                    type: 'success',
                    text: `WSJT-Z self-test passed: ${preflight.validation?.critical_ok || 0}/${preflight.validation?.critical_total || 0} critical checks ready.`,
                };
                const response = await fetch('/api/wsjtx/launch-patched-engine', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.getWsjtxLaunchPayload()),
                });
                const data = await response.json();
                if (!response.ok || data.success === false) {
                    throw new Error(this.formatWsjtxCommandError(data, 'OM0RX WSJT-Z launch failed'));
                }
                this.wsjtxLaunchResult = data;
                this.wsjtxHealthMessage = {
                    type: 'success',
                    text: data.message || 'OM0RX WSJT-Z launch command completed.',
                };
            } catch (error) {
                const preflightBlocked = String(error.message || '').includes('Critical launch checks failed');
                this.wsjtxHealthMessage = {
                    type: preflightBlocked ? 'warning' : 'error',
                    text: `${preflightBlocked ? 'OM0RX WSJT-Z start blocked' : 'OM0RX WSJT-Z launch failed'}: ${error.message}`,
                };
            } finally {
                this.wsjtxPreflightLoading = false;
                this.wsjtxLaunchLoading = false;
                setTimeout(() => this.loadWsjtxHealth({ preserveMessage: true }), 1500);
            }
        },

        async launchWsjtzEngine() {
            return this.launchPatchedWsjtxEngine();
        },

        async testWsjtxLaunchPreflight() {
            this.wsjtxPreflightLoading = true;
            try {
                await this.runWsjtxLaunchPreflight({ requireReady: false });
            } finally {
                this.wsjtxPreflightLoading = false;
            }
        },

        async loadWsjtxHealth(options = {}) {
            await this.loadDigitalEngineStatus();
            if (this.mshvOwnsDigitalPlanner) return;
            this.wsjtxHealthLoading = true;
            if (!options.preserveMessage) {
                this.wsjtxHealthMessage = null;
            }
            try {
                const response = await fetch('/api/wsjtx/health');
                const data = await response.json();
                this.wsjtxHealth = data;
                if (!response.ok || data.success === false) {
                    this.wsjtxHealthMessage = {
                        type: 'error',
                        text: data.message || data.detail || 'WSJT health check failed',
                    };
                }
            } catch (error) {
                this.wsjtxHealthMessage = {
                    type: 'error',
                    text: 'WSJT health check failed: ' + error.message,
                };
            } finally {
                this.wsjtxHealthLoading = false;
            }
        },

        async haltWsjtxTx() {
            this.wsjtxHealthLoading = true;
            this.wsjtxHealthMessage = null;
            try {
                const response = await fetch('/api/wsjtx/halt-tx', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ autoOnly: false }),
                });
                const data = await response.json();
                if (!response.ok || data.success === false) {
                    throw new Error(this.formatWsjtxCommandError(data, 'Halt TX command failed'));
                }
                this.wsjtxHealthMessage = { type: 'success', text: 'Halt TX command sent to WSJT client.' };
            } catch (error) {
                this.wsjtxHealthMessage = { type: 'error', text: 'Halt TX failed: ' + error.message };
            } finally {
                this.wsjtxHealthLoading = false;
                this.loadWsjtxHealth({ preserveMessage: true });
            }
        },

        async testWsjtxPrepareCommand() {
            this.wsjtxHealthLoading = true;
            this.wsjtxHealthMessage = null;
            const payload = {
                callsign: 'EA1TEST',
                frequency_mhz: 14.074,
                mode: 'FT8',
                grid: 'IN80',
                call_status: 'New Band',
                dxcc_status: 'Confirmed',
                score: 75,
                enableTx: false,
            };
            try {
                const response = await fetch('/api/wsjtx/prepare-target-from-spot', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const data = await response.json();
                if (!response.ok || data.success === false) {
                    throw new Error(this.formatWsjtxCommandError(data, 'Prepare command failed'));
                }
                this.wsjtxHealthMessage = { type: 'success', text: 'Prepare command reached the WSJT client without arming TX.' };
            } catch (error) {
                this.wsjtxHealthMessage = { type: 'error', text: 'Prepare test failed: ' + error.message };
            } finally {
                this.wsjtxHealthLoading = false;
                this.loadWsjtxHealth({ preserveMessage: true });
            }
        },

        async sendWsjtxAutoCqTest() {
            const text = String(this.configData.WSJTX_AUTO_CQ_TEXT || '').trim();
            if (!text) {
                this.wsjtxHealthMessage = { type: 'error', text: 'Auto CQ text is empty.' };
                return;
            }
            this.wsjtxHealthLoading = true;
            this.wsjtxHealthMessage = null;
            try {
                const response = await fetch('/api/wsjtx/free-text', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text,
                        send: !!this.configData.WSJTX_AUTO_CQ_SEND,
                    }),
                });
                const data = await response.json();
                if (!response.ok || data.success === false) {
                    throw new Error(this.formatWsjtxCommandError(data, 'Auto CQ command failed'));
                }
                this.wsjtxHealthMessage = {
                    type: 'success',
                    text: this.configData.WSJTX_AUTO_CQ_SEND
                        ? 'Auto CQ text was sent to WSJT with send enabled.'
                        : 'Auto CQ text was loaded into WSJT without arming TX.',
                };
            } catch (error) {
                this.wsjtxHealthMessage = { type: 'error', text: 'Auto CQ command failed: ' + error.message };
            } finally {
                this.wsjtxHealthLoading = false;
                this.loadWsjtxHealth({ preserveMessage: true });
            }
        },

        async sendWsjtxAutoAnswerTest() {
            const message = String(this.configData.WSJTX_AUTO_ANSWER_TEST_MESSAGE || '').trim();
            const call = String(this.configData.WSJTX_AUTO_ANSWER_TEST_CALL || '').trim();
            const grid = String(this.configData.WSJTX_AUTO_ANSWER_TEST_GRID || '').trim();
            const deltaFrequency = Number(this.configData.WSJTX_AUTO_ANSWER_TEST_DF || 1500);
            if (!message || !call) {
                this.wsjtxHealthMessage = { type: 'error', text: 'Auto Answer test needs a CQ message and call.' };
                return;
            }
            this.wsjtxHealthLoading = true;
            this.wsjtxHealthMessage = null;
            try {
                const response = await fetch('/api/wsjtx/reply', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        time: '000000',
                        snr: 0,
                        deltaTime: 0,
                        deltaFrequency: Number.isFinite(deltaFrequency) ? Math.max(200, Math.min(3000, Math.round(deltaFrequency))) : 1500,
                        mode: 'FT8',
                        message,
                        call,
                        grid,
                    }),
                });
                const data = await response.json();
                if (!response.ok || data.success === false) {
                    throw new Error(this.formatWsjtxCommandError(data, 'Auto Answer reply command failed'));
                }
                this.wsjtxHealthMessage = {
                    type: 'success',
                    text: `Auto Answer reply path was processed for ${call}.`,
                };
            } catch (error) {
                this.wsjtxHealthMessage = { type: 'error', text: 'Auto Answer test failed: ' + error.message };
            } finally {
                this.wsjtxHealthLoading = false;
                this.loadWsjtxHealth({ preserveMessage: true });
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
                        this.configData = { ...this.configData, ...data.config };
                        this.captureConfiguredSecrets(data.config);
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
