// Country Information Modal
// Displays country details with map visualization

console.log('✅ Loading country-modal.js module...');

const CountryModal = {
    // Cache for country data
    countryCache: {},
    topoData: null,
    
    /**
     * Calculate Maidenhead grid square from coordinates
     */
    calculateMaidenhead(lat, lon) {
        // Normalize coordinates
        lon = ((lon + 180) % 360) - 180;
        lat = Math.max(-90, Math.min(90, lat));
        
        const letters = 'ABCDEFGHIJKLMNOPQRSTUVWX';
        const digits = '0123456789';
        
        // Field (20° x 10°)
        let field_lon = Math.floor((lon + 180) / 20);
        let field_lat = Math.floor((lat + 90) / 10);
        let grid = letters[field_lon] + letters[field_lat];
        
        // Square (2° x 1°)
        let square_lon = Math.floor(((lon + 180) % 20) / 2);
        let square_lat = Math.floor(((lat + 90) % 10) / 1);
        grid += digits[square_lon] + digits[square_lat];
        
        // Subsquare (5' x 2.5') - optional for precision
        let subsquare_lon = Math.floor(((lon * 60 + 180 * 60) % (2 * 60)) / (2 * 60 / 24));
        let subsquare_lat = Math.floor(((lat * 60 + 90 * 60) % (1 * 60)) / (1 * 60 / 24));
        grid += letters[subsquare_lon].toLowerCase() + letters[subsquare_lat].toLowerCase();
        
        return grid;
    },
    
    /**
     * Get country code/abbreviation - Try multiple sources
     */
    getCountryCode(dxccId) {
        // Common DXCC abbreviations
        const codeMap = {
            'UNITED STATES': 'USA',
            'UNITED STATES OF AMERICA': 'USA',
            'CANADA': 'CAN',
            'MEXICO': 'MEX',
            'GERMANY': 'DEU',
            'FEDERAL REPUBLIC OF GERMANY': 'DEU',
            'FRANCE': 'FRA',
            'UNITED KINGDOM': 'GBR',
            'JAPAN': 'JPN',
            'AUSTRALIA': 'AUS',
            'NEW ZEALAND': 'NZL',
            'CHINA': 'CHN',
            'RUSSIA': 'RUS',
            'INDIA': 'IND',
            'BRAZIL': 'BRA',
        };
        
        // Try exact match
        if (dxccId && codeMap[dxccId.toUpperCase()]) {
            return codeMap[dxccId.toUpperCase()];
        }
        
        // Try first word (works for most countries)
        if (dxccId) {
            const firstWord = dxccId.split(' ')[0];
            if (firstWord && firstWord.length <= 3) {
                return firstWord.toUpperCase();
            }
            // Use first 3 letters as fallback
            return dxccId.substring(0, 3).toUpperCase();
        }
        
        return '???';
    },
    
    /**
     * Initialize country modal
     */
    init() {
        console.log('🌍 Initializing Country Modal...');
        this.loadTopoData();
        
        // Set up close button event listeners (not relying on Vue directives)
        const closeBtn = document.querySelector('.country-modal-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.hideModal();
            });
        }
        
        // Set up modal backdrop click handler
        const modal = document.querySelector('.country-info-modal');
        if (modal) {
            modal.addEventListener('click', (e) => {
                // Only close if clicking on the modal backdrop (not the content)
                if (e.target === modal) {
                    this.hideModal();
                }
            });
        }
    },
    
    /**
     * Load topology data from backend
     */
    async loadTopoData() {
        try {
            const response = await fetch('/api/country/data');
            if (response.ok) {
                this.topoData = await response.json();
                console.log('✅ Topology data loaded:', this.topoData.objects ? 'TopoJSON' : 'GeoJSON');
            }
        } catch (error) {
            console.error('❌ Failed to load topology data:', error);
        }
    },
    
    /**
     * Convert TopoJSON to GeoJSON using topojson-client
     */
    topoToGeo(topo) {
        if (!topo.objects) return topo; // Already GeoJSON
        
        try {
            // Use topojson-client library for proper decompression
            if (window.topojson && window.topojson.feature) {
                const features = [];
                const objects = topo.objects.countries;
                
                if (objects && objects.geometries) {
                    objects.geometries.forEach((geom, idx) => {
                        try {
                            // Use topojson-client to convert individual geometry
                            const featureCollection = window.topojson.feature(topo, geom);
                            if (featureCollection && featureCollection.geometry) {
                                features.push({
                                    type: 'Feature',
                                    properties: geom.properties || { id: idx },
                                    geometry: featureCollection.geometry
                                });
                            }
                        } catch (e) {
                            console.warn(`Failed to decompress geometry ${idx}:`, e);
                        }
                    });
                }
                
                return { type: 'FeatureCollection', features };
            } else {
                console.warn('topojson-client library not loaded');
                return topo;
            }
        } catch (error) {
            console.error('TopoJSON conversion error:', error);
            return topo;
        }
    },
    
    /**
     * Get country feature by name
     */
    async getCountryFeature(countryName) {
        if (!countryName) return null;
        
        if (this.countryCache[countryName]) {
            return this.countryCache[countryName];
        }
        
        try {
            const response = await fetch(`/api/country/by-name/${encodeURIComponent(countryName)}`);
            if (response.ok) {
                let feature = await response.json();
                
                // Decompress TopoJSON geometry if needed
                if (feature.arcs && feature.objects && window.topojson) {
                    try {
                        console.log('🗜️ Decompressing TopoJSON geometry for:', countryName);
                        
                        // Create a proper TopoJSON structure for decompression
                        const topoData = {
                            type: 'Topology',
                            arcs: feature.arcs,
                            objects: feature.objects,
                            bbox: feature.bbox,
                            transform: feature.transform  // IMPORTANT: Include transform!
                        };
                        
                        console.log('📦 TopoJSON structure:', {
                            hasArcs: !!topoData.arcs,
                            hasObjects: !!topoData.objects,
                            hasTransform: !!topoData.transform,
                            transform: topoData.transform
                        });
                        
                        // Get the country name from properties (needed for object reference)
                        const countryPropName = feature.properties?.name;
                        
                        // Decompress the geometry using topojson-client
                        if (window.topojson.feature && countryPropName) {
                            try {
                                console.log('🔍 Looking for object:', `topoData.objects.countries exists = ${!!topoData.objects.countries}`);
                                
                                // Create a feature from the entire countries object collection
                                const countriesFeature = window.topojson.feature(topoData, topoData.objects.countries);
                                
                                console.log('📋 Countries feature result:', {
                                    type: countriesFeature.type,
                                    featureCount: countriesFeature.features?.length || 0
                                });
                                
                                // Find the matching country in the features
                                if (countriesFeature.features) {
                                    const matchedFeature = countriesFeature.features.find(f => 
                                        f.properties?.name === countryPropName
                                    );
                                    if (matchedFeature && matchedFeature.geometry) {
                                        feature.geometry = matchedFeature.geometry;
                                        console.log('✅ Geometry decompressed successfully:', feature.geometry.type);
                                        
                                        // Debug: Show coordinate counts and SAMPLE VALUES
                                        if (feature.geometry.type === 'Polygon' && feature.geometry.coordinates) {
                                            const ringCount = feature.geometry.coordinates.length;
                                            const coordCount = feature.geometry.coordinates[0]?.length || 0;
                                            console.log(`📊 Polygon rings: ${ringCount}, coordinates in first ring: ${coordCount}`);
                                            if (coordCount > 0) {
                                                const firstCoord = feature.geometry.coordinates[0][0];
                                                const lastCoord = feature.geometry.coordinates[0][coordCount-1];
                                                console.log(`   First coord: [${firstCoord[0].toFixed(2)}, ${firstCoord[1].toFixed(2)}]`);
                                                console.log(`   Last coord: [${lastCoord[0].toFixed(2)}, ${lastCoord[1].toFixed(2)}]`);
                                                console.log(`   ✓ Coordinates look valid (lon in [-180,180], lat in [-90,90])`);
                                            }
                                        }
                                    } else {
                                        console.warn(`⚠️ Country not found in decompressed features. Looking for: "${countryPropName}"`);
                                        console.log('Available countries:', countriesFeature.features?.map(f => f.properties?.name).slice(0, 5));
                                    }
                                }
                            } catch (e) {
                                console.error('❌ Decompression error:', e.message);
                                console.error('   Error details:', e);
                            }
                        }
                    } catch (e) {
                        console.warn('Failed to decompress geometry:', e);
                        // Continue with original feature if decompression fails
                    }
                }
                
                this.countryCache[countryName] = feature;
                return feature;
            }
        } catch (error) {
            console.error(`Failed to fetch country '${countryName}':`, error);
        }
        
        return null;
    },
    
    /**
     * Calculate bounding box of geometry
     */
    getBounds(geometry) {
        let minLat = 90, maxLat = -90, minLon = 180, maxLon = -180;
        
        const processCoords = (coords) => {
            if (!Array.isArray(coords)) return;
            
            if (typeof coords[0] === 'number') {
                // [lon, lat]
                const [lon, lat] = coords;
                minLon = Math.min(minLon, lon);
                maxLon = Math.max(maxLon, lon);
                minLat = Math.min(minLat, lat);
                maxLat = Math.max(maxLat, lat);
            } else {
                coords.forEach(processCoords);
            }
        };
        
        processCoords(geometry.coordinates);
        
        return { minLat, maxLat, minLon, maxLon };
    },
    
    /**
     * Simple equirectangular projection (better for small areas)
     */
    projectEquirectangular(lon, lat, width, height, bounds) {
        const { minLon, maxLon, minLat, maxLat } = bounds;
        
        const lonRange = maxLon - minLon;
        const latRange = maxLat - minLat;
        
        // Equirectangular projection (simpler and better for small countries)
        const x = ((lon - minLon) / lonRange) * width;
        const y = height - ((lat - minLat) / latRange) * height;
        
        return { x, y };
    },
    
    /**
     * Draw map on canvas
     */
    drawMap(canvas, countryFeature, userLat, userLon, canvas2d, options = {}) {
        if (!canvas2d) return;
        
        const width = canvas.width;
        const height = canvas.height;
        
        // Get bounds
        const bounds = this.getBounds(countryFeature.geometry);
        
        // Ensure we have valid bounds
        if (bounds.minLon >= bounds.maxLon || bounds.minLat >= bounds.maxLat) {
            console.warn('Invalid bounds:', bounds);
            return;
        }
        
        // Add padding with aspect ratio correction
        const lonRange = bounds.maxLon - bounds.minLon;
        const latRange = bounds.maxLat - bounds.minLat;
        const maxRange = Math.max(lonRange, latRange);
        const padding = 0.15;
        
        bounds.minLon -= maxRange * padding;
        bounds.maxLon += maxRange * padding;
        bounds.minLat -= maxRange * padding;
        bounds.maxLat += maxRange * padding;
        
        // Clear canvas with dark background
        canvas2d.fillStyle = '#0b1220';
        canvas2d.fillRect(0, 0, width, height);
        
        // Draw subtle grid
        this.drawWorldBackground(canvas2d, width, height);
        
        // Draw country boundary
        this.drawGeometry(canvas2d, countryFeature.geometry, bounds, width, height);
        
        // Draw user marker
        if (userLat !== null && userLon !== null) {
            const projPoint = this.projectEquirectangular(userLon, userLat, width, height, bounds);
            
            // Only draw if within bounds
            if (projPoint.x >= 0 && projPoint.x <= width && projPoint.y >= 0 && projPoint.y <= height) {
                this.drawMarker(canvas2d, projPoint.x, projPoint.y);
            }
        }
    },
    
    /**
     * Draw world background (simplified)
     */
    drawWorldBackground(ctx, width, height) {
        // Draw subtle grid
        ctx.strokeStyle = '#1f2a37';
        ctx.lineWidth = 0.5;
        
        for (let i = 0; i < width; i += 50) {
            ctx.beginPath();
            ctx.moveTo(i, 0);
            ctx.lineTo(i, height);
            ctx.stroke();
        }
        
        for (let i = 0; i < height; i += 50) {
            ctx.beginPath();
            ctx.moveTo(0, i);
            ctx.lineTo(width, i);
            ctx.stroke();
        }
    },
    
    /**
     * Draw geometry (polygon)
     */
    drawGeometry(ctx, geometry, bounds, width, height) {
        const type = geometry.type;
        
        ctx.fillStyle = '#3b82f6';
        ctx.strokeStyle = '#93c5fd';
        ctx.lineWidth = 1.5;
        
        if (type === 'Polygon') {
            this.drawPolygon(ctx, geometry.coordinates, bounds, width, height);
        } else if (type === 'MultiPolygon') {
            geometry.coordinates.forEach(coords => {
                this.drawPolygon(ctx, coords, bounds, width, height);
            });
        } else if (type === 'LineString') {
            this.drawLineString(ctx, geometry.coordinates, bounds, width, height);
        }
    },
    
    /**
     * Draw polygon
     */
    drawPolygon(ctx, coords, bounds, width, height) {
        coords.forEach((ring, ringIndex) => {
            ctx.beginPath();
            
            ring.forEach((point, idx) => {
                const [lon, lat] = point;
                const projected = this.projectEquirectangular(lon, lat, width, height, bounds);
                
                if (idx === 0) {
                    ctx.moveTo(projected.x, projected.y);
                } else {
                    ctx.lineTo(projected.x, projected.y);
                }
            });
            
            ctx.closePath();
            
            if (ringIndex === 0) {
                ctx.fill();
                ctx.stroke();
            } else {
                ctx.stroke();
            }
        });
    },
    
    /**
     * Draw line string
     */
    drawLineString(ctx, coords, bounds, width, height) {
        ctx.beginPath();
        
        coords.forEach((point, idx) => {
            const [lon, lat] = point;
            const projected = this.projectEquirectangular(lon, lat, width, height, bounds);
            
            if (idx === 0) {
                ctx.moveTo(projected.x, projected.y);
            } else {
                ctx.lineTo(projected.x, projected.y);
            }
        });
        
        ctx.stroke();
    },
    
    /**
     * Draw marker (station location) - simple red pin without labels
     */
    drawMarker(ctx, x, y) {
        // Red pin marker
        const size = 8;
        
        // Outer circle (glow)
        ctx.fillStyle = 'rgba(255, 107, 107, 0.3)';
        ctx.beginPath();
        ctx.arc(x, y, size * 1.5, 0, Math.PI * 2);
        ctx.fill();
        
        // Middle circle
        ctx.fillStyle = 'rgba(239, 68, 68, 0.8)';
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fill();
        
        // Inner white dot
        ctx.fillStyle = '#ffffff';
        ctx.beginPath();
        ctx.arc(x, y, size * 0.5, 0, Math.PI * 2);
        ctx.fill();
    },
    
    /**
     * Show country modal
     */
    async showModal(countryName, continent, cqZone, dxccId, lat, lon, grid, bearing = null, countryTz = null) {
        const modal = document.querySelector('.country-info-modal');
        const canvas = document.getElementById('countryMapCanvas');
        
        if (!modal || !canvas) {
            console.error('Country modal elements not found');
            console.error('Modal:', !!modal, 'Canvas:', !!canvas);
            return;
        }
        
        try {
            // Get country feature
            const feature = await this.getCountryFeature(countryName);
            
            if (!feature) {
                console.warn(`Country feature not found for: ${countryName}`);
                return;
            }
            
            // Get user's callsign from various sources
            let callsign = '';
            if (window.userConfig?.callsign) {
                callsign = window.userConfig.callsign;
            } else if (localStorage.getItem('userCallsign')) {
                callsign = localStorage.getItem('userCallsign');
            } else if (window.coreData?.callsign) {
                callsign = window.coreData.callsign;
            }
            
            // Get country code from DXCC ID
            const countryCode = this.getCountryCode(dxccId);
            
            // Show modal (use visible class to ensure display:flex)
            modal.classList.add('visible');
            
            // Small delay to ensure DOM is updated
            setTimeout(() => {
                // Set up canvas with proper dimensions
                const container = canvas.parentElement;
                if (container) {
                    const width = container.offsetWidth;
                    const height = container.offsetHeight;
                    
                    console.log('Canvas dimensions:', width, 'x', height);
                    
                    canvas.width = width;
                    canvas.height = height;
                    
                    const ctx = canvas.getContext('2d');
                    if (!ctx) {
                        console.error('Could not get 2D context from canvas');
                        return;
                    }
                    
                    // Prepare drawing options
                    const drawOptions = {
                        countryCode: countryCode,
                        callsign: callsign
                    };
                    
                    // Draw map with options
                    this.drawMap(canvas, feature, lat, lon, ctx, drawOptions);
                    
                    // Update info text with bearing if available
                    this.updateInfoDisplay(modal, continent, cqZone, dxccId, lat, lon, grid, bearing, countryTz);
                    
                    console.log('✅ Country modal rendered successfully');
                }
            }, 50);
            
        } catch (error) {
            console.error('Error showing country modal:', error);
        }
    },
    
    /**
     * Update info display
     */
    updateInfoDisplay(modal, continent, cqZone, dxccId, lat, lon, grid, bearing = null, countryTz = null) {
        const info = modal.querySelector('.country-info-overlay');
        if (!info) return;
        
        // Calculate Maidenhead grid for the location
        let maidenheadGrid = '';
        if (lat !== null && lon !== null) {
            maidenheadGrid = this.calculateMaidenhead(lat, lon);
        }
        
        // Get current times
        const now = new Date();
        const utcTime = now.toLocaleTimeString('en-US', { timeZone: 'UTC', hour12: false });
        const localTime = now.toLocaleTimeString('en-US', { hour12: false });
        
        info.replaceChildren();
        const addRow = (label, value, monospace = false) => {
            const row = document.createElement('div');
            row.className = 'info-row';
            const name = document.createElement('span');
            name.textContent = `${label}:`;
            const content = document.createElement('strong');
            content.textContent = String(value ?? '—');
            if (monospace) content.style.cssText = 'font-family:monospace;letter-spacing:0.5px';
            row.append(name, content);
            info.appendChild(row);
        };
        addRow('Continent', continent || '—');
        addRow('CQ Zone', cqZone ?? '—');
        addRow('DXCC ID', dxccId ?? '—');
        if (Number.isFinite(Number(bearing))) addRow('Bearing', `${Math.round(Number(bearing))}°`);
        addRow('UTC Time', utcTime, true);
        addRow('Local Time', localTime, true);
        addRow('Latitude', Number.isFinite(Number(lat)) ? `${Number(lat).toFixed(2)}°` : '—');
        addRow('Longitude', Number.isFinite(Number(lon)) ? `${Number(lon).toFixed(2)}°` : '—');
        if (maidenheadGrid) addRow('Maidenhead', maidenheadGrid, true);
        if (grid) addRow('Grid (User)', grid);
    },
    
    /**
     * Hide modal
     */
    hideModal() {
        const modal = document.querySelector('.country-info-modal');
        if (modal) {
            modal.classList.remove('visible');
        }
    }
};

// Export for use in other modules
window.CountryModal = CountryModal;

console.log('✅ Country Modal module loaded');
