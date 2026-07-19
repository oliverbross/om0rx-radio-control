(function bootstrapRotorCompass() {
    const canvas = document.getElementById('rotorCompassCanvas');
    const azimuthEl = document.getElementById('rotorCompassAzimuth');
    const gridEl = document.getElementById('rotorCompassGrid');
    const zoomEl = document.getElementById('rotorCompassZoom');
    const stateEl = document.getElementById('rotorCompassState');
    const zoomOutBtn = document.getElementById('rotorCompassZoomOut');
    const zoomResetBtn = document.getElementById('rotorCompassZoomReset');
    const zoomInBtn = document.getElementById('rotorCompassZoomIn');
    const graylineBtn = document.getElementById('rotorCompassGrayline');
    const ctx = canvas.getContext('2d');

    const state = {
        countries: [],
        azimuth: 0,
        connected: false,
        homeGrid: 'JN88TQ',
        homeLat: 48.17,
        homeLon: 17.08,
        zoom: 1,
        minZoom: 1,
        maxZoom: 7,
        graylineEnabled: false,
        worldReady: false,
        drawPending: false,
        statusTimer: null,
        configTimer: null,
        resizeObserver: null,
    };

    const toRad = value => (Number(value) * Math.PI) / 180;
    const toDeg = value => (Number(value) * 180) / Math.PI;
    const normalizeDeg = value => ((Math.round(Number(value) || 0) % 360) + 360) % 360;
    const normalizeFloatDeg = value => ((Number(value) % 360) + 360) % 360;
    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
    const bearingToCanvasAngle = bearing => toRad(Number(bearing) - 90);

    function setStatus(text, type = '') {
        stateEl.textContent = text;
        stateEl.className = `rotor-compass-state ${type}`.trim();
    }

    function updateZoomDisplay() {
        if (zoomEl) zoomEl.textContent = `${state.zoom.toFixed(1)}x`;
        if (graylineBtn) graylineBtn.classList.toggle('active', state.graylineEnabled);
    }

    function setZoom(value) {
        const nextZoom = clamp(Number(value) || state.minZoom, state.minZoom, state.maxZoom);
        if (Math.abs(nextZoom - state.zoom) < 0.01) return;
        state.zoom = nextZoom;
        updateZoomDisplay();
        queueDraw();
    }

    function handleZoomWheel(event) {
        event.preventDefault();
        const factor = event.deltaY < 0 ? 1.18 : 1 / 1.18;
        setZoom(state.zoom * factor);
    }

    function maidenheadToLatLon(grid) {
        const value = String(grid || '').trim().toUpperCase();
        if (!/^[A-R]{2}[0-9]{2}([A-X]{2})?([0-9]{2})?$/.test(value)) return null;

        let lon = -180 + (value.charCodeAt(0) - 65) * 20;
        let lat = -90 + (value.charCodeAt(1) - 65) * 10;
        let lonSize = 20;
        let latSize = 10;

        if (value.length >= 4) {
            lon += Number(value[2]) * 2;
            lat += Number(value[3]);
            lonSize = 2;
            latSize = 1;
        }
        if (value.length >= 6) {
            lon += (value.charCodeAt(4) - 65) / 12;
            lat += (value.charCodeAt(5) - 65) / 24;
            lonSize = 1 / 12;
            latSize = 1 / 24;
        }
        if (value.length >= 8) {
            lon += Number(value[6]) / 120;
            lat += Number(value[7]) / 240;
            lonSize = 1 / 120;
            latSize = 1 / 240;
        }

        return {
            lat: lat + latSize / 2,
            lon: lon + lonSize / 2,
        };
    }

    async function fetchJson(url) {
        const response = await fetch(url, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
    }

    async function loadWorld() {
        const topo = await fetchJson('/api/country/data');
        state.countries = convertTopoJsonToFeatures(topo, 'countries');
        state.worldReady = true;
        queueDraw();
    }

    function convertTopoJsonToFeatures(topo, objectName) {
        const object = topo.objects?.[objectName] || Object.values(topo.objects || {})[0];
        if (!object || !Array.isArray(topo.arcs)) return [];

        const scale = topo.transform?.scale || [1, 1];
        const translate = topo.transform?.translate || [0, 0];
        const arcs = topo.arcs.map(arc => {
            let x = 0;
            let y = 0;
            return arc.map(point => {
                x += point[0];
                y += point[1];
                return [x * scale[0] + translate[0], y * scale[1] + translate[1]];
            });
        });

        function resolveArc(index) {
            if (index >= 0) return arcs[index] || [];
            const reversed = arcs[~index] || [];
            return reversed.slice().reverse();
        }

        function stitchRing(ring) {
            const points = [];
            ring.forEach((arcIndex, index) => {
                const arc = resolveArc(arcIndex);
                if (index === 0) {
                    points.push(...arc);
                } else {
                    points.push(...arc.slice(1));
                }
            });
            return points;
        }

        function convertGeometry(geometry) {
            if (!geometry) return null;
            if (geometry.type === 'Polygon') {
                return {
                    type: 'Polygon',
                    coordinates: (geometry.arcs || []).map(stitchRing),
                };
            }
            if (geometry.type === 'MultiPolygon') {
                return {
                    type: 'MultiPolygon',
                    coordinates: (geometry.arcs || []).map(polygon => polygon.map(stitchRing)),
                };
            }
            return null;
        }

        const geometries = object.type === 'GeometryCollection' ? object.geometries : [object];
        return geometries
            .map(geometry => ({
                type: 'Feature',
                id: geometry.id,
                properties: geometry.properties || {},
                geometry: convertGeometry(geometry),
            }))
            .filter(feature => feature.geometry);
    }

    async function loadRotorConfig() {
        try {
            const data = await fetchJson('/api/rotor/auto/status');
            const grid = String(data.home_grid || state.homeGrid || 'JN88TQ').trim().toUpperCase();
            const fromGrid = maidenheadToLatLon(grid);
            const lat = Number(data.home_lat);
            const lon = Number(data.home_lon);

            state.homeGrid = grid;
            state.homeLat = Number.isFinite(lat) ? lat : (fromGrid ? fromGrid.lat : state.homeLat);
            state.homeLon = Number.isFinite(lon) ? lon : (fromGrid ? fromGrid.lon : state.homeLon);

            gridEl.textContent = state.homeGrid;
            queueDraw();
        } catch (error) {
            const fallback = maidenheadToLatLon(state.homeGrid);
            if (fallback) {
                state.homeLat = fallback.lat;
                state.homeLon = fallback.lon;
            }
            setStatus('config unavailable', 'warn');
        }
    }

    async function updateRotorStatus() {
        try {
            const data = await fetchJson('/api/rotor/status?fresh=1');
            state.connected = !!data.enabled && data.azimuth !== null && data.azimuth !== undefined;
            if (state.connected) {
                state.azimuth = normalizeDeg(data.azimuth);
                azimuthEl.textContent = `${String(state.azimuth).padStart(3, '0')}\u00b0`;
                setStatus('live', 'ok');
            } else if (data.enabled) {
                setStatus('no azimuth', 'warn');
            } else {
                setStatus('rotor off', 'off');
            }
            queueDraw();
        } catch (error) {
            state.connected = false;
            setStatus('status lost', 'off');
            queueDraw();
        }
    }

    function resizeCanvas() {
        const rect = canvas.getBoundingClientRect();
        const dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
        const width = Math.max(1, Math.round(rect.width * dpr));
        const height = Math.max(1, Math.round(rect.height * dpr));
        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }
        return { width: rect.width, height: rect.height, dpr };
    }

    function angularDistanceAndBearing(lon, lat) {
        const lambda1 = toRad(state.homeLon);
        const phi1 = toRad(state.homeLat);
        const lambda2 = toRad(lon);
        const phi2 = toRad(lat);
        const deltaLambda = lambda2 - lambda1;
        const sinPhi1 = Math.sin(phi1);
        const cosPhi1 = Math.cos(phi1);
        const sinPhi2 = Math.sin(phi2);
        const cosPhi2 = Math.cos(phi2);
        const cosDistance = clamp(
            sinPhi1 * sinPhi2 + cosPhi1 * cosPhi2 * Math.cos(deltaLambda),
            -1,
            1,
        );
        const distance = Math.acos(cosDistance);
        const y = Math.sin(deltaLambda) * cosPhi2;
        const x = cosPhi1 * sinPhi2 - sinPhi1 * cosPhi2 * Math.cos(deltaLambda);
        return {
            distance,
            bearing: Math.atan2(y, x),
        };
    }

    function project(lon, lat, layout) {
        const point = angularDistanceAndBearing(Number(lon), Number(lat));
        const radius = layout.mapRadius * state.zoom * (point.distance / Math.PI);

        return {
            x: layout.cx + Math.sin(point.bearing) * radius,
            y: layout.cy - Math.cos(point.bearing) * radius,
            visible: radius <= layout.mapRadius * 1.02,
        };
    }

    function drawSegmentedLine(points, layout, closePath = false) {
        let drawing = false;
        let visibleCount = 0;
        points.forEach(point => {
            const projected = project(point[0], point[1], layout);
            if (!projected.visible) {
                drawing = false;
                return;
            }
            if (!drawing) {
                ctx.moveTo(projected.x, projected.y);
                drawing = true;
            } else {
                ctx.lineTo(projected.x, projected.y);
            }
            visibleCount += 1;
        });
        if (closePath && visibleCount > 2) ctx.closePath();
        return visibleCount;
    }

    function drawGraticule(layout) {
        ctx.save();
        ctx.strokeStyle = 'rgba(52, 93, 102, 0.25)';
        ctx.lineWidth = 1;

        for (let lat = -60; lat <= 60; lat += 30) {
            ctx.beginPath();
            const points = [];
            for (let lon = -180; lon <= 180; lon += 3) points.push([lon, lat]);
            drawSegmentedLine(points, layout);
            ctx.stroke();
        }

        for (let lon = -180; lon < 180; lon += 30) {
            ctx.beginPath();
            const points = [];
            for (let lat = -90; lat <= 90; lat += 3) points.push([lon, lat]);
            drawSegmentedLine(points, layout);
            ctx.stroke();
        }
        ctx.restore();
    }

    function getSunSubpoint(date = new Date()) {
        const julianDay = date.getTime() / 86400000 + 2440587.5;
        const n = julianDay - 2451545.0;
        const meanLongitude = normalizeFloatDeg(280.460 + 0.9856474 * n);
        const meanAnomaly = toRad(normalizeFloatDeg(357.528 + 0.9856003 * n));
        const eclipticLongitude = toRad(normalizeFloatDeg(
            meanLongitude + 1.915 * Math.sin(meanAnomaly) + 0.020 * Math.sin(2 * meanAnomaly),
        ));
        const obliquity = toRad(23.439 - 0.0000004 * n);
        const rightAscension = toDeg(Math.atan2(
            Math.cos(obliquity) * Math.sin(eclipticLongitude),
            Math.cos(eclipticLongitude),
        ));
        const declination = Math.asin(Math.sin(obliquity) * Math.sin(eclipticLongitude));
        const gmst = normalizeFloatDeg(280.46061837 + 360.98564736629 * n);

        return {
            lat: toDeg(declination),
            lon: normalizeFloatDeg(rightAscension - gmst + 180) - 180,
        };
    }

    function solarAltitudeSin(lon, lat, sun) {
        return (
            Math.sin(toRad(lat)) * Math.sin(toRad(sun.lat)) +
            Math.cos(toRad(lat)) * Math.cos(toRad(sun.lat)) * Math.cos(toRad(lon - sun.lon))
        );
    }

    function drawSunMarker(layout, sun) {
        const projected = project(sun.lon, sun.lat, layout);
        if (!projected.visible) return;

        const radius = Math.max(4, layout.mapRadius * 0.018);
        ctx.save();
        ctx.beginPath();
        ctx.arc(projected.x, projected.y, radius * 1.8, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 220, 95, 0.22)';
        ctx.fill();
        ctx.beginPath();
        ctx.arc(projected.x, projected.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = '#ffd447';
        ctx.fill();
        ctx.strokeStyle = 'rgba(68, 42, 0, 0.55)';
        ctx.lineWidth = 1.4;
        ctx.stroke();
        ctx.restore();
    }

    function drawGrayline(layout) {
        if (!state.graylineEnabled) return;

        const sun = getSunSubpoint();
        const step = state.zoom > 3 ? 3 : 4;

        ctx.save();
        ctx.beginPath();
        ctx.arc(layout.cx, layout.cy, layout.mapRadius, 0, Math.PI * 2);
        ctx.clip();

        for (let lat = -88; lat < 88; lat += step) {
            for (let lon = -180; lon < 180; lon += step) {
                const corners = [
                    [lon, lat],
                    [lon + step, lat],
                    [lon + step, lat + step],
                    [lon, lat + step],
                ];
                const projected = corners.map(point => project(point[0], point[1], layout));
                if (!projected.some(point => point.visible)) continue;

                const centerLon = lon + step / 2;
                const centerLat = lat + step / 2;
                const light = solarAltitudeSin(centerLon, centerLat, sun);
                const alpha = light < 0
                    ? clamp(0.08 + Math.abs(light) * 0.20, 0.08, 0.26)
                    : clamp(light * 0.035, 0, 0.03);
                if (alpha <= 0.005) continue;

                ctx.beginPath();
                projected.forEach((point, index) => {
                    if (index === 0) ctx.moveTo(point.x, point.y);
                    else ctx.lineTo(point.x, point.y);
                });
                ctx.closePath();
                ctx.fillStyle = light < 0
                    ? `rgba(7, 11, 24, ${alpha})`
                    : `rgba(255, 225, 128, ${alpha})`;
                ctx.fill();
            }
        }

        drawSunMarker(layout, sun);
        ctx.restore();
    }

    function drawWorld(layout) {
        const radius = layout.mapRadius;
        ctx.save();
        ctx.beginPath();
        ctx.arc(layout.cx, layout.cy, radius, 0, Math.PI * 2);
        const ocean = ctx.createRadialGradient(
            layout.cx - radius * 0.18,
            layout.cy - radius * 0.24,
            radius * 0.08,
            layout.cx,
            layout.cy,
            radius,
        );
        ocean.addColorStop(0, '#d6f1f8');
        ocean.addColorStop(0.58, '#9fc5d0');
        ocean.addColorStop(1, '#5f8795');
        ctx.fillStyle = ocean;
        ctx.fill();
        ctx.clip();

        drawGraticule(layout);

        ctx.fillStyle = '#e3e4df';
        ctx.strokeStyle = 'rgba(76, 85, 83, 0.52)';
        ctx.lineWidth = Math.max(0.7, radius / 420);

        state.countries.forEach(feature => {
            const geometry = feature.geometry || {};
            const polygons = geometry.type === 'Polygon'
                ? [geometry.coordinates]
                : geometry.type === 'MultiPolygon'
                    ? geometry.coordinates
                    : [];
            polygons.forEach(polygon => {
                ctx.beginPath();
                let visible = 0;
                polygon.forEach(ring => {
                    visible += drawSegmentedLine(ring, layout, true);
                });
                if (visible > 2) {
                    ctx.fill();
                    ctx.stroke();
                }
            });
        });
        drawGrayline(layout);
        ctx.restore();
    }

    function drawCompassTicks(layout) {
        ctx.save();
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.lineCap = 'round';

        for (let degree = 0; degree < 360; degree += 2) {
            const major = degree % 30 === 0;
            const medium = degree % 10 === 0;
            const inner = layout.ringRadius - (major ? 23 : medium ? 16 : 8);
            const outer = layout.ringRadius - 1;
            const theta = toRad(degree);
            const sx = layout.cx + Math.sin(theta) * inner;
            const sy = layout.cy - Math.cos(theta) * inner;
            const ex = layout.cx + Math.sin(theta) * outer;
            const ey = layout.cy - Math.cos(theta) * outer;

            ctx.beginPath();
            ctx.moveTo(sx, sy);
            ctx.lineTo(ex, ey);
            ctx.strokeStyle = major ? 'rgba(255, 255, 255, 0.9)' : medium ? 'rgba(230, 236, 240, 0.64)' : 'rgba(215, 225, 232, 0.34)';
            ctx.lineWidth = major ? 2 : medium ? 1.35 : 0.75;
            ctx.stroke();
        }

        ctx.font = `900 ${Math.max(10, Math.min(15, layout.mapRadius * 0.04))}px ui-monospace, SFMono-Regular, Consolas, monospace`;
        ctx.lineWidth = 3;
        ctx.strokeStyle = 'rgba(0, 0, 0, 0.74)';
        ctx.fillStyle = 'rgba(248, 250, 252, 0.96)';
        for (let degree = 0; degree < 360; degree += 15) {
            const label = degree === 0 ? '360' : String(degree);
            const theta = toRad(degree);
            const r = layout.ringRadius - 38;
            const x = layout.cx + Math.sin(theta) * r;
            const y = layout.cy - Math.cos(theta) * r;
            ctx.strokeText(label, x, y);
            ctx.fillText(label, x, y);
        }
        ctx.restore();
    }

    function drawBeam(layout) {
        const az = normalizeDeg(state.azimuth);
        const beamWidth = 260;
        const half = beamWidth / 2;
        const start = bearingToCanvasAngle(az - half);
        const end = bearingToCanvasAngle(az + half);
        const radius = layout.ringRadius - 16;

        ctx.save();
        ctx.beginPath();
        ctx.arc(layout.cx, layout.cy, layout.ringRadius - 8, start, end, false);
        ctx.strokeStyle = state.connected ? '#dc2626' : '#777';
        ctx.lineWidth = Math.max(10, layout.mapRadius * 0.042);
        ctx.lineCap = 'round';
        ctx.stroke();

        const theta = toRad(az);
        const beamEndX = layout.cx + Math.sin(theta) * (layout.mapRadius * 0.98);
        const beamEndY = layout.cy - Math.cos(theta) * (layout.mapRadius * 0.98);
        ctx.beginPath();
        ctx.moveTo(layout.cx, layout.cy);
        ctx.lineTo(beamEndX, beamEndY);
        ctx.strokeStyle = state.connected ? '#ef1f1f' : '#888';
        ctx.lineWidth = Math.max(3.5, layout.mapRadius * 0.02);
        ctx.lineCap = 'round';
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(layout.cx, layout.cy, Math.max(6, layout.mapRadius * 0.04), 0, Math.PI * 2);
        ctx.fillStyle = state.connected ? '#dc2626' : '#777';
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.72)';
        ctx.stroke();

        ctx.fillStyle = state.connected ? '#ff4d4d' : '#aaa';
        ctx.font = `900 ${Math.max(24, Math.min(46, layout.mapRadius * 0.14))}px ui-monospace, SFMono-Regular, Consolas, monospace`;
        ctx.textAlign = 'right';
        ctx.textBaseline = 'top';
        ctx.fillText(`${String(az).padStart(3, '0')}\u00b0`, layout.cx + layout.ringRadius - 4, layout.cy - layout.ringRadius + 8);
        ctx.restore();
    }

    function drawHomeMarker(layout) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(layout.cx, layout.cy, Math.max(3, layout.mapRadius * 0.018), 0, Math.PI * 2);
        ctx.fillStyle = '#111';
        ctx.fill();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.78)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();
    }

    function draw() {
        const { width, height } = resizeCanvas();
        ctx.clearRect(0, 0, width, height);

        const bottomReserve = Math.min(78, Math.max(52, height * 0.14));
        const size = Math.max(120, Math.min(width, height - bottomReserve) * 0.94);
        const radius = size / 2;
        const layout = {
            cx: width / 2,
            cy: Math.max(radius + 8, (height - bottomReserve) / 2),
            mapRadius: radius * 0.78,
            ringRadius: radius * 0.98,
        };

        ctx.save();
        ctx.shadowColor = 'rgba(0, 0, 0, 0.38)';
        ctx.shadowBlur = Math.max(12, radius * 0.04);
        ctx.shadowOffsetY = Math.max(4, radius * 0.018);
        drawWorld(layout);
        ctx.restore();

        ctx.save();
        ctx.beginPath();
        ctx.arc(layout.cx, layout.cy, layout.ringRadius, 0, Math.PI * 2);
        ctx.strokeStyle = '#9aa1a3';
        ctx.lineWidth = Math.max(2, radius * 0.008);
        ctx.stroke();
        ctx.restore();

        drawBeam(layout);
        drawCompassTicks(layout);
        drawHomeMarker(layout);
    }

    function queueDraw() {
        if (state.drawPending) return;
        state.drawPending = true;
        requestAnimationFrame(() => {
            state.drawPending = false;
            draw();
        });
    }

    async function start() {
        state.resizeObserver = new ResizeObserver(queueDraw);
        state.resizeObserver.observe(canvas);
        window.addEventListener('resize', queueDraw);
        canvas.addEventListener('wheel', handleZoomWheel, { passive: false });
        zoomOutBtn?.addEventListener('click', () => setZoom(state.zoom / 1.35));
        zoomResetBtn?.addEventListener('click', () => setZoom(1));
        zoomInBtn?.addEventListener('click', () => setZoom(state.zoom * 1.35));
        graylineBtn?.addEventListener('click', () => {
            state.graylineEnabled = !state.graylineEnabled;
            updateZoomDisplay();
            queueDraw();
        });
        updateZoomDisplay();

        await Promise.allSettled([loadWorld(), loadRotorConfig()]);
        await updateRotorStatus();
        state.statusTimer = setInterval(updateRotorStatus, 750);
        state.configTimer = setInterval(loadRotorConfig, 30000);
        queueDraw();
    }

    window.addEventListener('beforeunload', () => {
        if (state.statusTimer) clearInterval(state.statusTimer);
        if (state.configTimer) clearInterval(state.configTimer);
        if (state.resizeObserver) state.resizeObserver.disconnect();
    });

    start().catch(error => {
        console.error('Rotor compass failed to start:', error);
        setStatus('startup failed', 'off');
        queueDraw();
    });
})();
