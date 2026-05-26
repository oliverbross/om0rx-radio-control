// Shared Wavelog QSO field normalisation for legacy table views.

console.log('✅ Loading wavelog-qso-normalizer.js module...');

(function () {
    function splitDateTime(value) {
        const raw = String(value || '').trim();
        if (!raw) {
            return { date: '', time: '' };
        }

        if (/^\d{8}$/.test(raw)) {
            return { date: raw, time: '' };
        }

        const parts = raw.replace('T', ' ').split(' ');
        const date = (parts[0] || '').replaceAll('-', '');
        const time = (parts[1] || '').replaceAll(':', '').slice(0, 6);
        return { date, time };
    }

    function normaliseFrequency(value) {
        if (value === null || value === undefined || value === '') {
            return '';
        }

        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : '';
    }

    function isConfirmed(value) {
        return value === true || String(value || '').trim().toUpperCase() === 'Y';
    }

    function toLocalLogQso(entry) {
        const qso = entry || {};
        const timeOn = splitDateTime(qso.time_on || qso.qso_date || '');
        const mode = qso.submode || qso.mode || '';

        return {
            id: qso.id || qso.primary_key || '',
            call: (qso.call || qso.callsign || '').toUpperCase(),
            callsign: (qso.callsign || qso.call || '').toUpperCase(),
            qso_date: qso.qso_date || timeOn.date,
            time_on: qso.time_on_adif || (qso.time_on && /^\d{6}$/.test(String(qso.time_on)) ? qso.time_on : timeOn.time),
            frequency: normaliseFrequency(qso.frequency || qso.freq),
            band: qso.band || '',
            mode,
            rst_sent: qso.rst_sent || '',
            rst_rcvd: qso.rst_rcvd || qso.rst_received || '',
            lotw_qsl: qso.lotw_qsl || (isConfirmed(qso.lotw_rcvd) ? 'Y' : 'N'),
            lotw_sent: qso.lotw_sent || '',
            lotw_rcvd: qso.lotw_rcvd || '',
            country: qso.country || '',
            dxcc: qso.dxcc || '',
            name: qso.name || '',
            qth: qso.qth || '',
            gridsquare: qso.gridsquare || qso.grid || '',
            pota_ref: qso.pota_ref || '',
            sota_ref: qso.sota_ref || '',
            wwff_ref: qso.wwff_ref || '',
            iota: qso.iota || '',
            comment: qso.comment || ''
        };
    }

    function toLocalLogQsos(entries) {
        return (Array.isArray(entries) ? entries : [])
            .map(toLocalLogQso)
            .filter(qso => qso.call);
    }

    function buildWorkedMap(entries) {
        const worked = {};

        toLocalLogQsos(entries).forEach(qso => {
            const call = qso.call.toUpperCase();
            const band = String(qso.band || '').toUpperCase();
            const mode = String(qso.mode || '').toUpperCase();

            if (!call || !band || !mode) {
                return;
            }

            const key = `${call}-${band}-${mode}`;
            if (!worked[key]) {
                worked[key] = {
                    qso_date: qso.qso_date || '',
                    time_on: qso.time_on || ''
                };
            }
        });

        return worked;
    }

    window.WavelogQsoNormalizer = {
        toLocalLogQso,
        toLocalLogQsos,
        buildWorkedMap
    };
})();
