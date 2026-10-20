

(function() {
    if (!('serviceWorker' in navigator)) return;
    // Inline SW as a Blob — no separate file needed
    const swCode = [
        "self.addEventListener('message', function(e) {",
        "    if (e.data && e.data.type === 'PING') {",
        "        self.clients.matchAll().then(function(cs) {",
        "            cs.forEach(function(c) { c.postMessage({ type: 'PONG' }); });",
        "        });",
        "    }",
        "});",
        "function keepAlive() { setTimeout(keepAlive, 20000); }",
        "keepAlive();"
    ].join('\n');
    const blob = new Blob([swCode], { type: 'application/javascript' });
    const swUrl = URL.createObjectURL(blob);
    navigator.serviceWorker.register(swUrl, { scope: '/' }).then(function(reg) {
        console.log('[SW] Registered for background tracking');
    }).catch(function(e) {
        console.warn('[SW] Registration failed (non-critical):', e);
    });
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
})();





(function() {
    'use strict';

    const root = document.getElementById('trackingRoot');
    if (!root) return;

    const isOwner = root.dataset.isOwner === '1';
    const trackerId = root.dataset.trackerId;
    const isTrackingInit = root.dataset.isTracking === '1';

    const hasPushToken = root.dataset.hasPushToken === '1';

    // Parse customer pins for mini-map
    let liveCustomers = [];
    try {
        const raw = root.dataset.customers || '';
        if (raw) liveCustomers = JSON.parse(atob(raw));
    } catch(e) { console.warn('Failed to parse live customers:', e); }

    const state = {
        tracking: isTrackingInit && isOwner,
        sendIntervalId: null,
        timerIntervalId: null,
        trackingStart: null,
        lastLat: null,
        lastLng: null,
        totalDistance: parseFloat(root.dataset.distance || '0'),
        userMovedMap: false,
        mapInitialised: false,
        tickInFlight: false,
        browserFallbackActive: false,
        trackingSessionStartMs: 0,
        nativeWatchdogId: null,
    };

    // Position provider with GPS + IP fallback
    class PositionProvider {
        constructor() {
            this.hasGps = !!navigator.geolocation;
            this.isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        }

        async getPosition() {
            if (this.hasGps) {
                try {
                    return await this._getGpsPosition();
                } catch (e) {
                    console.warn('GPS failed, trying IP fallback:', e.message);
                }
            }
            return await this._getIpPosition();
        }

        _getGpsPosition() {
            return new Promise((resolve, reject) => {
                const timeout = setTimeout(() => reject(new Error('GPS timeout')), 10000);
                navigator.geolocation.getCurrentPosition(
                (pos) => { clearTimeout(timeout); resolve(pos); },
                (err) => { clearTimeout(timeout); reject(err); },
                { enableHighAccuracy: this.isMobile, timeout: 10000, maximumAge: 5000 }
                );
            });
        }

        async _getIpPosition() {
            const services = [
                'https://ipapi.co/json/',
                'https://ipwho.is/'
            ];
            for (const url of services) {
                try {
                    const res = await fetch(url);
                    const data = await res.json();
                    if (data.latitude && data.longitude) {
                        return {
                            coords: {
                                latitude: data.latitude,
                                longitude: data.longitude,
                                accuracy: 5000,
                                timestamp: Date.now()
                            }
                        };
                    }
                } catch (e) {}
            }
            throw new Error('No position available');
        }
    }

    const provider = new PositionProvider();

    // Helper functions
    const haversine = (lat1, lon1, lat2, lon2) => {
        const R = 6371, dLat = (lat2-lat1)*Math.PI/180, dLon = (lon2-lon1)*Math.PI/180;
        const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    };

    const postJson = async (url, payload) => {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload || {}),
            credentials: 'same-origin',
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    };

    const formatDuration = ms => {
        const s = Math.floor(ms / 1000);
        return `${String(Math.floor(s / 60)).padStart(2,'0')}:${String(s % 60).padStart(2,'0')}`;
    };

    const updateStatus = (message, type = 'info') => {
        const statusText = document.getElementById('statusText');
        const msgDiv = document.getElementById('statusMessage');
        const statusDot = document.getElementById('statusDot');
        if (statusText) statusText.textContent = message;
        if (msgDiv) msgDiv.className = 'status-message ' + type;
        if (statusDot) statusDot.className = 'status-dot ' + (state.tracking ? 'live' : 'offline');
    };

    // Map
    let liveMap = null, liveMarker = null, livePolyline = null, livePath = [];
    let liveCustomerLayer = null;

    function renderLiveCustomers(custList) {
        if (!liveMap) return;
        if (!liveCustomerLayer) {
            liveCustomerLayer = L.layerGroup().addTo(liveMap);
        }
        liveCustomerLayer.clearLayers();
        custList.forEach(c => {
            if (!c.lat || !c.lng) return;
            const color = c.visited ? '#15803d' : '#3b82f6';
            const label = c.visited ? '✓ Visited' : '○ Planned';
            L.circleMarker([c.lat, c.lng], {
                radius: 8, color: '#fff', fillColor: color, fillOpacity: 0.9, weight: 2,
            })
            .bindPopup('<b>' + c.name + '</b><br/>' + label)
            .addTo(liveCustomerLayer);
        });
    }

    function initMap() {
        if (state.mapInitialised || typeof L === 'undefined') return;
        const el = document.getElementById('liveMap');
        if (!el) return;
        liveMap = L.map('liveMap', { zoomControl: true }).setView([23.7701, 90.4254], 14);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '', maxZoom: 19,
        }).addTo(liveMap);
        liveMap.on('dragstart zoomstart zoom', () => { state.userMovedMap = true; });
        state.mapInitialised = true;
    }

    // Show/hide the "near customer" green banner above the map
    function showNearCustomerBanner(customerInfo) {
        let banner = document.getElementById('nearCustomerBanner');
        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'nearCustomerBanner';
            banner.style.cssText = 'background:#dcfce7;border-left:4px solid #16a34a;padding:10px 16px;margin:0 16px 8px;border-radius:12px;font-size:13px;color:#15803d;display:none;align-items:center;gap:8px;';
            const mapContainer = document.querySelector('.map-container');
            if (mapContainer) mapContainer.parentNode.insertBefore(banner, mapContainer);
        }
        if (customerInfo) {
            banner.style.display = 'flex';
            const visitedTag = customerInfo.visited ? ' &mdash; <strong style="color:#059669">&#10003; Visited</strong>' : '';
            banner.innerHTML = '<span style="font-size:18px">&#128205;</span><span>Near: <strong>' + customerInfo.name + '</strong> (' + customerInfo.distance_m + ' m)' + visitedTag + '</span>';
        } else {
            banner.style.display = 'none';
        }
    }

    function updateMap(lat, lng, firstFix, nearCustomerInfo) {
        if (!liveMap) initMap();
        if (!liveMap) return;
        // Green marker = near a planned customer; red = normal traveling
        const markerColor = nearCustomerInfo ? '#16a34a' : '#ef4444';
        livePath.push([lat, lng]);
        if (livePolyline) {
            livePolyline.addLatLng([lat, lng]);
        } else {
            livePolyline = L.polyline(livePath, { color: '#3b82f6', weight: 4 }).addTo(liveMap);
        }
        if (!liveMarker) {
            liveMarker = L.circleMarker([lat, lng], {
                radius: 10, color: '#fff', fillColor: markerColor, fillOpacity: 1, weight: 3,
            }).addTo(liveMap);
        } else {
            liveMarker.setLatLng([lat, lng]);
            liveMarker.setStyle({ fillColor: markerColor });
        }
        showNearCustomerBanner(nearCustomerInfo || null);
        if (firstFix && !state.userMovedMap) {
            liveMap.setView([lat, lng], 16, { animate: true });
        }
        setTimeout(() => liveMap.invalidateSize(), 100);
    }

    // Send position to server. A location only counts as a successful fix
    // after the server has accepted it. This prevents the UI/timer from saying
    // "Tracking Active" while no GPS row was actually saved.
    async function sendPosition(position, firstFix) {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        const acc = position.coords.accuracy || 0;

        let delta = 0;
        if (state.lastLat !== null) {
            delta = haversine(state.lastLat, state.lastLng, lat, lng);
        }

        try {
            const res = await postJson('/salesperson_tracking/update', {
                latitude: lat, longitude: lng, accuracy: acc,
                distance: delta, tracker_id: trackerId,
            });
            if (!res || res.ok === false) {
                throw new Error((res && res.error) || 'Server rejected location update');
            }

            // Only advance the local GPS/distance state after the server confirms
            // the point was stored. Otherwise a failed request could make the next
            // point calculate distance from a location that never reached Odoo.
            state.totalDistance += delta;
            state.lastLat = lat;
            state.lastLng = lng;

            const updateEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
            updateEl('latitudeValue', lat.toFixed(6));
            updateEl('longitudeValue', lng.toFixed(6));
            updateEl('lastSeenValue', res.last_seen || new Date().toLocaleTimeString());
            updateEl('accuracyValue', acc.toFixed(1) + ' m');
            if (res.total_distance_km != null) updateEl('kpiDistance', parseFloat(res.total_distance_km).toFixed(1));
            if (res.visited_count != null) updateEl('kpiCovered', res.visited_count);
            if (res.visited_rate != null) updateEl('kpiRate', res.visited_rate + '%');
            if (res.planned_count != null) updateEl('kpiPlan', res.planned_count);
            if (res.location_name && document.getElementById('locationNameValue'))
                document.getElementById('locationNameValue').textContent = res.location_name;

            updateMap(lat, lng, firstFix, res.near_customer || null);
            updateStatus('Tracking Active', 'info');
            return res;
        } catch (e) {
            console.error('Send failed:', e);
            updateStatus('Location send failed - retrying', 'error');
            throw e;
        }
    }

    // Main tracking loop. Guard against overlapping GPS requests: getCurrentPosition
    // can take up to 10 seconds, while the loop runs every 2 seconds.
    async function doTick() {
        if (!state.tracking || !isOwner || state.tickInFlight) return;
        state.tickInFlight = true;
        try {
            const pos = await provider.getPosition();
            await sendPosition(pos, state.lastLat === null);
        } catch (e) {
            updateStatus(`Location error: ${e.message || e}`, 'error');
        } finally {
            state.tickInFlight = false;
        }
    }

    function startLoop() {
        if (state.sendIntervalId) return;
        state.sendIntervalId = setInterval(doTick, 2000);
        doTick();
    }

    function stopLoop() {
        if (state.sendIntervalId) {
            clearInterval(state.sendIntervalId);
            state.sendIntervalId = null;
        }
        state.tickInFlight = false;
    }

    const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

    async function fetchTrackerStatus() {
        const res = await fetch(`/salesperson_tracking/status/${trackerId}`, {
            credentials: 'same-origin',
            cache: 'no-store',
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!data || !data.ok) throw new Error((data && data.error) || 'Status unavailable');
        return data;
    }

    async function waitForFreshNativeFix(startedAtMs, timeoutMs = 8000) {
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
            try {
                const data = await fetchTrackerStatus();
                if ((data.last_mobile_seen_epoch_ms || 0) >= (startedAtMs - 1000)) {
                    if (data.last_lat && data.last_lng) {
                        const firstFix = state.lastLat === null;
                        state.lastLat = data.last_lat;
                        state.lastLng = data.last_lng;
                        updateMap(data.last_lat, data.last_lng, firstFix, null);
                        const latEl = document.getElementById('latitudeValue');
                        const lngEl = document.getElementById('longitudeValue');
                        const seenEl = document.getElementById('lastSeenValue');
                        if (latEl) latEl.textContent = Number(data.last_lat).toFixed(6);
                        if (lngEl) lngEl.textContent = Number(data.last_lng).toFixed(6);
                        if (seenEl && data.last_seen) seenEl.textContent = data.last_seen;
                    }
                    return data;
                }
            } catch (e) {
                console.warn('[Tracking] Native status check failed:', e.message);
            }
            await sleep(1000);
        }
        throw new Error('Native GPS did not respond');
    }

    function stopNativeWatchdog() {
        if (state.nativeWatchdogId) {
            clearInterval(state.nativeWatchdogId);
            state.nativeWatchdogId = null;
        }
    }

    // If a stale Expo token exists, the server may believe the native app will
    // track even though the app/service is not actually running. When browser
    // fallback is active, watch for a genuine mobile GPS row and hand tracking
    // back to the app as soon as it appears, avoiding duplicate browser+mobile logs.
    function startNativeTakeoverWatch() {
        stopNativeWatchdog();
        if (!hasPushToken || !state.browserFallbackActive) return;
        state.nativeWatchdogId = setInterval(async () => {
            if (!state.tracking || !state.browserFallbackActive) {
                stopNativeWatchdog();
                return;
            }
            try {
                const data = await fetchTrackerStatus();
                if ((data.last_mobile_seen_epoch_ms || 0) >= (state.trackingSessionStartMs - 1000)) {
                    console.log('[Tracking] Native GPS is active; stopping browser fallback loop.');
                    stopLoop();
                    state.browserFallbackActive = false;
                    stopNativeWatchdog();
                    updateStatus('Tracking Active', 'info');
                }
            } catch (e) {
                // Keep browser fallback alive; next watchdog cycle will retry.
            }
        }, 5000);
    }

    // ── Background / Page Visibility handling ────────────────
    // When the page is hidden (mobile switches tab or locks screen),
    // the browser throttles setInterval.  We restart the loop on
    // visibilitychange so tracking resumes immediately when the
    // user returns, and we show a persistent notification while hidden.
    let bgNotification = null;

    function showBgNotification() {
        if (!('Notification' in window) || Notification.permission !== 'granted') return;
        if (bgNotification) return; // already showing
        bgNotification = new Notification('GPS Tracking Active', {
            body: 'ZenCore is tracking your location in the background.',
            tag: 'zencore-bg-track',
            renotify: false,
            silent: true,
        });
        bgNotification.onclick = function() { window.focus(); bgNotification = null; };
        bgNotification.onclose = function() { bgNotification = null; };
    }

    function dismissBgNotification() {
        if (bgNotification) { bgNotification.close(); bgNotification = null; }
    }

    document.addEventListener('visibilitychange', function() {
        if (!isOwner || !state.tracking) return;
        if (document.visibilityState === 'hidden') {
            // Page went to background — show persistent notification
            showBgNotification();
            // Restart loop immediately when we come back
        } else {
            // Page returned to foreground
            dismissBgNotification();
            // Ensure loop is running (it may have been throttled).
            // Skip if the phone app has push registered — GPS duty
            // belongs to it, and restarting the browser loop too
            // would double-count.
            if ((!hasPushToken || state.browserFallbackActive) && !state.sendIntervalId) {
                startLoop();
            }
        }
    });

    const tickTimer = () => {
        const el = document.getElementById('takingTimeValue');
        if (el && state.trackingStart) el.textContent = formatDuration(Date.now() - state.trackingStart);
    };

    // Start/Stop handlers
    let wakeLock = null;

    async function acquireWakeLock() {
        if (!('wakeLock' in navigator)) return;
        try {
            wakeLock = await navigator.wakeLock.request('screen');
            wakeLock.addEventListener('release', async () => {
                // Re-acquire if tracking still active (e.g. screen dimmed then re-lit)
                if (state.tracking && document.visibilityState === 'visible') {
                    await acquireWakeLock();
                }
            });
        } catch(e) { console.warn('[WakeLock] Could not acquire:', e.message); }
    }

    async function releaseWakeLock() {
        if (wakeLock) { try { await wakeLock.release(); } catch(e) {} wakeLock = null; }
    }

    async function startTracking() {
        if (state.tracking) return;

        const statusMsg = document.getElementById('statusText');
        const startBtn = document.getElementById('startButton');
        const stopBtn = document.getElementById('stopButton');

        if (startBtn) startBtn.disabled = true;
        if (stopBtn) stopBtn.disabled = true;
        if (statusMsg) statusMsg.textContent = 'Starting tracking...';

        let serverStarted = false;
        try {
            const result = await postJson('/salesperson_tracking/start', { tracker_id: trackerId });
            if (!result.ok) {
                throw new Error(result.error || 'Failed to start tracking');
            }

            serverStarted = true;
            state.tracking = true;
            state.trackingSessionStartMs = Date.now();
            state.browserFallbackActive = false;
            stopNativeWatchdog();

            // IMPORTANT: do not start the timer yet. First prove that at least
            // one real location reaches Odoo. This fixes the old behaviour where
            // time counted while LAT/LNG/LAST UPDATE stayed blank.
            updateStatus('Waiting for GPS location...', 'info');

            let firstFixSource = null;

            if (hasPushToken) {
                // Give the installed app a short chance to answer the silent push.
                // A stale token / killed background service is common on Android,
                // so browser GPS becomes the automatic fallback if it stays silent.
                try {
                    await waitForFreshNativeFix(state.trackingSessionStartMs, 8000);
                    firstFixSource = 'mobile';
                } catch (nativeError) {
                    console.warn('[Tracking] Native GPS unavailable; using browser fallback:', nativeError.message);
                    const pos = await provider.getPosition();
                    await sendPosition(pos, state.lastLat === null);
                    firstFixSource = 'browser';
                    state.browserFallbackActive = true;
                    startLoop();
                    startNativeTakeoverWatch();
                }
            } else {
                const pos = await provider.getPosition();
                await sendPosition(pos, state.lastLat === null);
                firstFixSource = 'browser';
                state.browserFallbackActive = true;
                startLoop();
            }

            // Only now is tracking genuinely active.
            state.trackingStart = Date.now();
            tickTimer();
            if (!state.timerIntervalId) {
                state.timerIntervalId = setInterval(tickTimer, 1000);
            }
            await acquireWakeLock();

            if (stopBtn) stopBtn.disabled = false;
            if (statusMsg) statusMsg.textContent = 'Tracking Active';
            const statusDiv = document.getElementById('statusMessage');
            if (statusDiv) statusDiv.className = 'status-message info';

            console.log('Tracking started successfully. GPS source:', firstFixSource, result);

        } catch (e) {
            console.error('Start tracking error:', e);

            // If Odoo already created a live session but no usable GPS fix could
            // be obtained, roll the session back. The timer therefore never runs
            // for a false/empty tracking session.
            if (serverStarted) {
                try {
                    await postJson('/salesperson_tracking/stop', { tracker_id: trackerId });
                } catch (rollbackError) {
                    console.error('Failed to rollback tracking session:', rollbackError);
                }
            }

            state.tracking = false;
            state.trackingStart = null;
            state.trackingSessionStartMs = 0;
            state.browserFallbackActive = false;
            stopLoop();
            stopNativeWatchdog();
            if (state.timerIntervalId) clearInterval(state.timerIntervalId);
            state.timerIntervalId = null;
            await releaseWakeLock();

            const msg = e && e.message ? e.message : String(e);
            if (statusMsg) statusMsg.textContent = `GPS not started: ${msg}`;
            const statusDiv = document.getElementById('statusMessage');
            if (statusDiv) statusDiv.className = 'status-message error';

            if (startBtn) startBtn.disabled = false;
            if (stopBtn) stopBtn.disabled = true;
        }
    }

    async function stopTracking() {
        if (!state.tracking) return;
        updateStatus('Stopping...', 'info');
        document.getElementById('stopButton').disabled = true;
        try {
            await postJson('/salesperson_tracking/stop', { tracker_id: trackerId });
            state.tracking = false;
            if (state.timerIntervalId) clearInterval(state.timerIntervalId);
            state.timerIntervalId = null;
            state.trackingStart = null;
            state.trackingSessionStartMs = 0;
            state.browserFallbackActive = false;
            stopNativeWatchdog();
            // stopLoop() is a safe no-op if the browser loop was never
            // started (GPS duty was handed to the phone app via a
            // silent push instead — see action_stop_tracking, called
            // by postJson above; it stops the app's background
            // service on its own, never opening it).
            stopLoop();
            await releaseWakeLock();
            dismissBgNotification();
            document.getElementById('startButton').disabled = false;
            updateStatus('Offline - Press Start', 'warning');
        } catch (e) {
            updateStatus(`Failed: ${e.message}`, 'error');
        }
        document.getElementById('stopButton').disabled = false;
    }

    // Cross-tab sync
    async function pollStatus() {
        try {
            const res = await fetch(`/salesperson_tracking/status/${trackerId}`);
            if (!res.ok) return;
            const data = await res.json();
            if (!data.ok) return;

            if (data.is_tracking !== state.tracking && isOwner) {
                if (data.is_tracking) {
                    state.tracking = true;
                    state.trackingStart = Date.now();
                    if (!state.timerIntervalId) state.timerIntervalId = setInterval(tickTimer, 1000);
                    // If another tab/device started the session, keep browser GPS as
                    // fallback unless a native app is actually producing fresh pings.
                    if (!hasPushToken) {
                        state.browserFallbackActive = true;
                        startLoop();
                    } else {
                        state.trackingSessionStartMs = Date.now();
                        setTimeout(async () => {
                            if (!state.tracking || state.sendIntervalId) return;
                            try {
                                const status = await fetchTrackerStatus();
                                const nativeFresh = (status.last_mobile_seen_epoch_ms || 0) >= (Date.now() - 15000);
                                if (!nativeFresh) {
                                    state.browserFallbackActive = true;
                                    startLoop();
                                    startNativeTakeoverWatch();
                                }
                            } catch (e) {
                                state.browserFallbackActive = true;
                                startLoop();
                                startNativeTakeoverWatch();
                            }
                        }, 3000);
                    }
                    document.getElementById('startButton').disabled = true;
                    document.getElementById('stopButton').disabled = false;
                } else {
                    state.tracking = false;
                    if (state.timerIntervalId) clearInterval(state.timerIntervalId);
                    state.timerIntervalId = null;
                    state.trackingSessionStartMs = 0;
                    state.browserFallbackActive = false;
                    stopNativeWatchdog();
                    stopLoop();
                    document.getElementById('startButton').disabled = false;
                    document.getElementById('stopButton').disabled = true;
                }
                updateStatus(state.tracking ? 'Tracking Active' : 'Offline', state.tracking ? 'info' : 'warning');
            }

            if (!isOwner && data.last_lat && data.last_lng) {
                updateMap(data.last_lat, data.last_lng, !state.mapInitialised, null);
                if (data.last_seen) document.getElementById('lastSeenValue').textContent = data.last_seen;
                if (data.location_name) document.getElementById('locationNameValue').textContent = data.location_name;
                document.getElementById('latitudeValue').textContent = data.last_lat.toFixed(6);
                document.getElementById('longitudeValue').textContent = data.last_lng.toFixed(6);
            }
            // Always re-render customer pins — trust server state fully
            if (data.customers && data.customers.length) {
                liveCustomers = data.customers;
                renderLiveCustomers(liveCustomers);
            }
        } catch (e) {}
    }

    function schedulePoll() {
        setTimeout(async () => { await pollStatus(); schedulePoll(); }, 5000);
    }

    // ── Camera functionality with front/back toggle ─────────────────────
    let stream = null;
    let currentFacingMode = 'environment';
    const cameraOverlay = document.getElementById('cameraOverlay');
    const selfieVideo = document.getElementById('selfieVideo');
    const selfieCanvas = document.getElementById('selfieCanvas');

    async function openCamera() {
        try {
            if (stream) {
                stream.getTracks().forEach(t => t.stop());
                stream = null;
            }

            // Make sure overlay is visible and on top
            const overlay = document.getElementById('cameraOverlay');
            overlay.style.display = 'flex';
            overlay.style.position = 'fixed';
            overlay.style.top = '0';
            overlay.style.left = '0';
            overlay.style.width = '100%';
            overlay.style.height = '100%';
            overlay.style.zIndex = '99999';

            const constraints = {
                video: { facingMode: currentFacingMode }
            };

            stream = await navigator.mediaDevices.getUserMedia(constraints);
            const video = document.getElementById('selfieVideo');
            video.srcObject = stream;
            await video.play();

            updateStatus('Camera ready - tap to capture', 'info');
        } catch (e) {
            console.error('Camera error:', e);
            updateStatus('Cannot access camera: ' + e.message, 'error');
            document.getElementById('cameraOverlay').style.display = 'none';
        }
    }

    function switchCamera() {
        currentFacingMode = currentFacingMode === 'environment' ? 'user' : 'environment';
        openCamera();
    }

    function closeCamera() {
        if (stream) {
            stream.getTracks().forEach(t => t.stop());
            stream = null;
        }
        if (selfieVideo) {
            selfieVideo.srcObject = null;
        }
        cameraOverlay.style.display = 'none';
        updateStatus('Camera closed', 'info');
    }

    async function capturePhoto() {
        if (!selfieVideo.videoWidth || !selfieVideo.videoHeight) {
            updateStatus('Camera not ready. Please wait.', 'error');
            return;
        }

        // Set canvas dimensions
        const videoWidth = selfieVideo.videoWidth;
        const videoHeight = selfieVideo.videoHeight;

        // Read actual track settings to get true dimensions before browser correction
        const track = stream.getVideoTracks()[0];
        const settings = track.getSettings();
        const trackWidth = settings.width || videoWidth;
        const trackHeight = settings.height || videoHeight;

        // If track reports landscape but video element shows portrait, rotation was applied by browser
        const browserRotated = (trackWidth > trackHeight) !== (videoWidth > videoHeight);
        const angle = screen.orientation ? screen.orientation.angle : (window.orientation || 0);

        selfieCanvas.width  = videoWidth;
        selfieCanvas.height = videoHeight;

        const ctx = selfieCanvas.getContext('2d');
        ctx.save();
        ctx.translate(selfieCanvas.width / 2, selfieCanvas.height / 2);

        if (browserRotated) {
            // Browser already rotated dimensions — just mirror
            ctx.scale(-1, 1);
        } else if (angle === 90 || angle === -90 || angle === 270) {
            ctx.rotate(-Math.PI / 2);
            ctx.scale(-1, 1);
        } else if (angle === 180) {
            ctx.rotate(Math.PI);
            ctx.scale(-1, 1);
        } else {
            ctx.scale(-1, 1);
        }

        ctx.drawImage(selfieVideo, -videoWidth / 2, -videoHeight / 2);
        ctx.restore();

        // Get image as JPEG
        const imageData = selfieCanvas.toDataURL('image/jpeg', 0.9);

        // Get current location. Don't trust state.lastLat/lastLng blindly —
        // it starts out null and only gets filled in by the background
        // tracking loop's next periodic fix, so a photo taken right after
        // opening the page (before that first fix lands) would otherwise
        // silently send lat=0, lng=0. Ask for a fresh fix now instead, and
        // only fall back to the cached background position if that fails.
        let lat = null;
        let lng = null;
        try {
            const pos = await provider.getPosition();
            lat = pos.coords.latitude;
            lng = pos.coords.longitude;
        } catch (e) {
            console.warn('capturePhoto: fresh GPS fix failed, using last known position:', e.message);
            lat = state.lastLat;
            lng = state.lastLng;
        }
        let locationName = document.getElementById('locationNameValue')?.textContent || '';

        // Show saving indicator
        const snapNotification = document.getElementById('snapNotification');
        if (snapNotification) {
            snapNotification.textContent = 'Saving photo...';
            snapNotification.style.display = 'block';
            snapNotification.style.background = '#3b82f6';
        }

        try {
            const response = await fetch('/salesperson_tracking/save_photo', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    id: Date.now(),
                    params: {
                        image_data: imageData,
                        filename: `photo_${Date.now()}.jpg`,
                        latitude: lat,
                        longitude: lng,
                        location_name: locationName
                    }
                })
            });

            const json = await response.json();
            const result = (json && json.result) ? json.result : json;

            if (result.success) {
                if (snapNotification) {
                    snapNotification.textContent = '✓ Photo saved!';
                    snapNotification.style.background = '#22c55e';
                    setTimeout(() => {
                        snapNotification.style.display = 'none';
                    }, 2000);
                }
                updateStatus('Photo saved successfully', 'info');
                closeCamera();
            } else {
                throw new Error(result.error || 'Failed to save photo');
            }
        } catch (err) {
            console.error('Save error:', err);
            if (snapNotification) {
                snapNotification.textContent = '✗ ' + (err.message || 'Save failed');
                snapNotification.style.background = '#ef4444';
                setTimeout(() => {
                    snapNotification.style.display = 'none';
                    snapNotification.style.background = '#22c55e';
                }, 3000);
            }
            updateStatus('Save failed: ' + err.message, 'error');
        }
    }

    // Camera button event listeners
    const openCameraBtn = document.getElementById('openCameraBtn');
    const captureBtn = document.getElementById('captureBtn');
    const closeCameraBtn = document.getElementById('closeCameraBtn');
    const switchCameraBtn = document.getElementById('switchCameraBtn');

    if (openCameraBtn) openCameraBtn.addEventListener('click', openCamera);
    if (captureBtn) captureBtn.addEventListener('click', capturePhoto);
    if (closeCameraBtn) closeCameraBtn.addEventListener('click', closeCamera);
    if (switchCameraBtn) switchCameraBtn.addEventListener('click', switchCamera);

    // Initialize
    initMap();
    renderLiveCustomers(liveCustomers);

    if (state.tracking && isOwner) {
        state.trackingStart = Date.now();
        state.trackingSessionStartMs = Date.now();
        state.timerIntervalId = setInterval(tickTimer, 1000);
        if (!hasPushToken) {
            state.browserFallbackActive = true;
            startLoop();
        } else {
            // Page reload while a session is live: do not trust the mere presence
            // of a push token. If no recent mobile GPS ping exists, restore the
            // browser loop automatically.
            setTimeout(async () => {
                if (!state.tracking || state.sendIntervalId) return;
                try {
                    const status = await fetchTrackerStatus();
                    const nativeFresh = (status.last_mobile_seen_epoch_ms || 0) >= (Date.now() - 15000);
                    if (!nativeFresh) {
                        state.browserFallbackActive = true;
                        startLoop();
                        startNativeTakeoverWatch();
                    }
                } catch (e) {
                    state.browserFallbackActive = true;
                    startLoop();
                    startNativeTakeoverWatch();
                }
            }, 3000);
        }
        document.getElementById('startButton').disabled = true;
        document.getElementById('stopButton').disabled = false;
    } else {
        document.getElementById('startButton').disabled = false;
        document.getElementById('stopButton').disabled = true;
    }

    document.getElementById('startButton')?.addEventListener('click', startTracking);
    document.getElementById('stopButton')?.addEventListener('click', stopTracking);
    document.getElementById('openCameraBtn')?.addEventListener('click', openCamera);
    document.getElementById('captureBtn')?.addEventListener('click', capturePhoto);
    document.getElementById('closeCameraBtn')?.addEventListener('click', closeCamera);

    // Full Map button — always open in a new tab so the live tracking
    // page (and GPS loop) keeps running. On mobile this prevents the
    // 1-minute-then-stop problem caused by navigating away from this page.
    const fullMapBtn = document.getElementById('fullMapBtn');
    if (fullMapBtn) {
        const mapUrl = '/salesperson_tracking/moving_map/' + trackerId;
        fullMapBtn.addEventListener('click', function(e) {
            e.preventDefault();
            const w = window.open(mapUrl, '_blank', 'noopener');
            if (!w) {
                // Pop-up blocked (common on mobile); fall back to same-tab
                // but warn the user that tracking will stop
                if (confirm('Open Full Map? (GPS tracking will pause while on that page)')) {
                    window.location.href = mapUrl;
                }
            }
        });
    }

    schedulePoll();
})();


(function() {
    'use strict';

    // ── Debug logger ──────────────────────────────────────────
    const DEBUG = true;
    const log  = DEBUG ? (...a) => console.log('[MovingMap]', ...a) : () => {};
    const warn = (...a) => console.warn('[MovingMap]', ...a);
    const err  = (...a) => console.error('[MovingMap]', ...a);

    const mapRoot = document.getElementById('mapRoot');

    if (!mapRoot) {
        return;
    }

    // Always return to the Live Tracking card action, not browser history.
    // History may point outside Odoo when the map was opened in a new tab.
    const mapBackBtn = document.getElementById('mapBackBtn');
    if (mapBackBtn) {
        mapBackBtn.addEventListener('click', function (event) {
            if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) {
                return; // Preserve normal browser open-in-new-tab behavior.
            }
            event.preventDefault();
            const targetUrl = mapBackBtn.href;
            try {
                // When embedded, navigate the Odoo client instead of the map iframe.
                if (window.parent && window.parent !== window) {
                    window.parent.location.assign(targetUrl);
                } else {
                    window.location.assign(targetUrl);
                }
            } catch (error) {
                window.location.assign(targetUrl);
            }
        });
    }

    const pointsB64  = mapRoot.getAttribute('data-points')    || '';
    const custB64    = mapRoot.getAttribute('data-customers') || '';
    const initStatus = mapRoot.getAttribute('data-status')    || 'offline';
    const trackerId  = parseInt(
        mapRoot.getAttribute('data-tracker-id') || '0',
        10
    );

    let points    = [];
    let customers = [];
    try { points    = JSON.parse(atob(pointsB64)); } catch(e) { warn('points parse error', e); }
    try { customers = JSON.parse(atob(custB64)); }   catch(e) { warn('customers parse error', e); }

    log('Init — trackerId=%d initStatus=%s points=%d customers=%d',
    trackerId, initStatus, points.length, customers.length);

    // ── Map init ──────────────────────────────────────────────
    const map = L.map('map').setView([23.7701, 90.4254], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
    }).addTo(map);

    // Customer layer rendered FIRST → sits below path and salesperson marker
    const customerLayer = L.layerGroup().addTo(map);

    let trackPolylines = [];
    let reconnectLines = [];
    let startMarker    = null;
    let currentMarker  = null;
    let allLatLngs     = [];

    // ── Helpers ───────────────────────────────────────────────
    function calcDistKm(pts) {
        const R = 6371; let d = 0;
        for (let i = 1; i < pts.length; i++) {
            const dLat = (pts[i].lat - pts[i-1].lat) * Math.PI / 180;
            const dLng = (pts[i].lng - pts[i-1].lng) * Math.PI / 180;
            const a = Math.sin(dLat/2)**2
            + Math.cos(pts[i-1].lat * Math.PI/180)
            * Math.cos(pts[i].lat * Math.PI/180)
            * Math.sin(dLng/2)**2;
            d += R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        }
        return d;
    }

    // Route statistics always use the same validated segments as the blue map.
    // Raw server totals can include GPS jumps and must never replace this value.
    function updateStats(pts, distanceKm = 0, breakCount = 0, dropped = 0) {
        document.getElementById('distanceVal').textContent = distanceKm.toFixed(2) + ' km';
        document.getElementById('pointsVal').textContent = pts.length;
        document.getElementById('logCount').textContent = pts.length;
        const note = document.getElementById('distanceQualityNote');
        if (note) {
            note.textContent = breakCount
                ? `${breakCount} GPS gap${breakCount === 1 ? '' : 's'} excluded · ${dropped} filtered`
                : `${dropped} noisy GPS point${dropped === 1 ? '' : 's'} filtered`;
            note.title = 'Verified GPS movement only. Unrecorded travel cannot be calculated from missing samples. Road distance is not claimed without a reliable route.';
        }
    }

    // Fix 2: only live / offline — no idle
    function updateStatus(status, label) {
        // Treat any truthy is_tracking as "live"
        const resolved = (status === 'live') ? 'live' : 'offline';
        const badge = document.getElementById('statusBadge');
        const dot   = badge ? badge.querySelector('.status-dot') : null;
        const lbl   = document.getElementById('statusLabel');
        if (badge) badge.className = 'status-pill ' + resolved;
        if (dot)   dot.className   = 'status-dot '  + resolved;
        if (lbl)   lbl.textContent = resolved === 'live' ? 'Live' : 'Offline';
        log('Status updated → %s', resolved);
    }

    // ── Fix 1: Parse localized time string for gap detection ──
    // Server sends "2026-05-12 14:39:58" (localized). JS Date needs ISO:
    function parseTime(t) {
        if (!t) return 0;
        // Replace space with T; add Z only if no offset present
        const iso = t.trim().replace(' ', 'T');
        const ms  = new Date(iso).getTime();
        return isNaN(ms) ? 0 : ms;
    }

    // Display-only GPS cleanup. Source logs, totals, APIs and reports are unchanged.
    // Never invent a route across a network outage or GPS jump.
    const MAP_MAX_ACCURACY_M = 20;
    const MAP_GAP_SECONDS = 90;
    // Urban tracking: reject physically implausible motion and do not draw long
    // straight links between sparse observations (e.g. app background/network).
    const MAP_MAX_SPEED_MPS = 18;       // 64.8 km/h
    const MAP_MAX_DRAW_STEP_M = 180;   // never draw a long blind straight line
    const MAP_STATIONARY_RADIUS_M = 18;
    const MAP_REACQUIRE_RADIUS_M = 80;

    function distanceMeters(a, b) {
        const R = 6371000;
        const p1 = a.lat * Math.PI / 180, p2 = b.lat * Math.PI / 180;
        const dp = p2 - p1, dl = (b.lng - a.lng) * Math.PI / 180;
        const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
        return 2 * R * Math.atan2(Math.sqrt(h), Math.sqrt(Math.max(0, 1 - h)));
    }

    function prepareMapSegments(rawPoints) {
        const segments = [];
        let segment = [];
        let pending = null;  // wait for a second nearby fix before adopting a jump
        let rejected = 0;
        let previousRawTime = 0;
        function flush() {
            if (segment.length) segments.push(segment);
            segment = [];
        }
        function addPoint(p) {
            segment.push(p);
        }
        for (const entry of rawPoints) {
            const p = { ...entry, lat: Number(entry.lat), lng: Number(entry.lng) };
            const accuracy = Number(p.accuracy || 0);
            const time = parseTime(p.time);
            const valid = Number.isFinite(p.lat) && Number.isFinite(p.lng)
                && Math.abs(p.lat) <= 90 && Math.abs(p.lng) <= 180
                && !(p.lat === 0 && p.lng === 0)
                && Number.isFinite(accuracy) && accuracy > 0 && accuracy <= MAP_MAX_ACCURACY_M;
            if (!valid) { rejected++; continue; }
            if (previousRawTime && time && time <= previousRawTime) {
                flush();
                pending = null;
            }
            previousRawTime = time || previousRawTime;
            if (!segment.length) {
                if (pending) {
                    // A GPS jump is only trusted when a subsequent fix confirms
                    // the new area. Isolated remote points are never displayed.
                    const pendingDt = (time - pending.timeMs) / 1000;
                    const pendingDist = distanceMeters(pending.point, p);
                    if (pendingDt > 0 && pendingDt <= MAP_GAP_SECONDS
                        && pendingDist <= MAP_REACQUIRE_RADIUS_M
                        && pendingDist / pendingDt <= MAP_MAX_SPEED_MPS) {
                        addPoint(pending.point);
                        if (pendingDist >= MAP_STATIONARY_RADIUS_M) addPoint(p);
                        pending = null;
                        continue;
                    }
                    rejected++;
                }
                pending = { point: p, timeMs: time };
                continue;
            }
            const last = segment[segment.length - 1];
            const lastTime = parseTime(last.time);
            const dt = time && lastTime ? (time - lastTime) / 1000 : 0;
            const meters = distanceMeters(last, p);
            if (dt <= 0 || dt > MAP_GAP_SECONDS) {
                flush();
                pending = { point: p, timeMs: time };
                continue;
            }
            // The effective stationary radius grows with the uncertainty of
            // both fixes. A device drifting 20 m while standing still must not
            // add fake travel. Movement can still accumulate against the last
            // *accepted* anchor, so a slow walker is not permanently ignored.
            const lastAccuracy = Number(last.accuracy) || MAP_MAX_ACCURACY_M;
            const accuracyNoiseM = Math.min(35, Math.max(
                MAP_STATIONARY_RADIUS_M,
                Math.hypot(lastAccuracy, accuracy) * 1.15
            ));
            if (meters < accuracyNoiseM) {
                pending = null;
                continue;
            }
            if (meters > MAP_MAX_DRAW_STEP_M || meters / dt > MAP_MAX_SPEED_MPS) {
                // Do not connect an untrusted new position to the prior route.
                // If the GPS returns to its previous position, this jump simply
                // disappears. Two consecutive fixes in the new area establish
                // a separate segment without a fictional bridging line.
                if (pending) {
                    const pendingDt = (time - pending.timeMs) / 1000;
                    const pendingDist = distanceMeters(pending.point, p);
                    if (pendingDt > 0 && pendingDt <= MAP_GAP_SECONDS
                        && pendingDist <= MAP_REACQUIRE_RADIUS_M
                        && pendingDist / pendingDt <= MAP_MAX_SPEED_MPS) {
                        flush();
                        addPoint(pending.point);
                        if (pendingDist >= MAP_STATIONARY_RADIUS_M) addPoint(p);
                        pending = null;
                        continue;
                    }
                    rejected++;
                }
                pending = { point: p, timeMs: time };
                continue;
            }
            pending = null;
            addPoint(p);
        }
        flush();
        // Preserve a meaningful current marker for a tracker with just one fix.
        if (!segments.length && rawPoints.length === 1 && pending) segments.push([pending.point]);
        // A lone uncorroborated jump must not replace an established route.
        log('Map GPS cleanup: %d source points, %d rejected, %d disconnected segments',
            rawPoints.length, rejected + (pending ? 1 : 0), segments.length);
        prepareMapSegments.quality = {
            raw: rawPoints.length,
            accepted: segments.reduce((sum, seg) => sum + seg.length, 0),
            breaks: Math.max(0, segments.length - 1),
        };
        return segments;
    }

    // ── Fix 3+4: renderPath — correct marker sizes/colors, live path ──
    // Live (is_tracking=true)  → current pos marker is GREEN
    // Offline (stopped)        → current pos marker is RED
    // Path colour: blue (#3b82f6)
    // Visited customer: dark green (#15803d)
    // Planned (not yet visited): blue (#3b82f6)
    // Skipped: yellow (#eab308)
    function renderPath(pts, isLive) {
        log('renderPath: %d points, isLive=%s', pts.length, isLive);

        trackPolylines.forEach(p => map.removeLayer(p));
        trackPolylines = [];
        reconnectLines.forEach(l => map.removeLayer(l));
        reconnectLines = [];
        if (startMarker)   { map.removeLayer(startMarker);   startMarker   = null; }
        if (currentMarker) { map.removeLayer(currentMarker); currentMarker = null; }

        if (!pts.length) { warn('renderPath: no points'); updateStats([]); return; }

        const segs = prepareMapSegments(pts);
        const clean = segs.flat();
        allLatLngs = clean.map(p => [p.lat, p.lng]);

        // Draw only actually recorded, reliable continuous paths.
        // Never run OSRM route() over missing GPS history: it creates a long
        // fictitious line when the phone loses internet or tracking is off.
        for (const seg of segs) {
            if (seg.length > 1) {
                const poly = L.polyline(seg.map(p => [p.lat, p.lng]), {
                    color: '#3288ee', weight: 5, opacity: 0.95,
                    smoothFactor: 1.2, lineCap: 'round', lineJoin: 'round',
                }).addTo(map);
                trackPolylines.push(poly);
            }
        }
        // Visual continuity only: bridge verified segment endpoints after a GPS/network
        // interruption. Orange is the unknown (unrecorded) portion, not a measured route.
        // Keep identical weight/opacity to the blue track; do not count it as distance.
        for (let i = 1; i < segs.length; i++) {
            const before = segs[i - 1];
            const after = segs[i];
            if (!before.length || !after.length) continue;
            const from = before[before.length - 1];
            const to = after[0];
            const bridge = L.polyline([[from.lat, from.lng], [to.lat, to.lng]], {
                color: '#f59e0b', weight: 5, opacity: 0.95,
                smoothFactor: 1.2, lineCap: 'round', lineJoin: 'round',
            }).bindTooltip('GPS/network gap — connecting last and next recorded points; actual route unknown');
            bridge.addTo(map);
            reconnectLines.push(bridge);
        }
        if (!clean.length) {
            updateStats([]);
            return;
        }

        // Start marker — small green dot
        startMarker = L.circleMarker([clean[0].lat, clean[0].lng], {
            radius: 5, color: '#fff', fillColor: '#22c55e', fillOpacity: 1, weight: 2,
            pane: 'markerPane',
        }).bindTooltip('Start').addTo(map);

        // ── Fix 3: Current position marker ───────────────────
        // Small (radius 8), green when live, red when offline
        const last        = clean[clean.length - 1];
        const markerColor = isLive ? '#22c55e' : '#ef4444';
        const tipLabel    = isLive ? '● Live' : '● Last seen';
        const tooltip     = `${tipLabel}${last.time ? '\n' + last.time : ''}${last.accuracy ? '\nAccuracy: ' + last.accuracy.toFixed(0) + ' m' : ''}`;

        currentMarker = L.circleMarker([last.lat, last.lng], {
            radius: 8, color: '#fff', fillColor: markerColor, fillOpacity: 1, weight: 2,
            pane: 'markerPane',
        }).bindTooltip(tooltip, { permanent: false, sticky: false }).addTo(map);

        if (currentMarker.bringToFront) currentMarker.bringToFront();

        log('renderPath: currentMarker lat=%.6f lng=%.6f color=%s', last.lat, last.lng, markerColor);

        // Distance excludes unrecorded gaps (which are deliberately not linked).
        const visibleDistance = segs.reduce((total, seg) => total + calcDistKm(seg), 0);
        const quality = prepareMapSegments.quality || {raw: pts.length, accepted: clean.length, breaks: 0};
        updateStats(clean, visibleDistance, quality.breaks,
            Math.max(0, quality.raw - quality.accepted));

        // Fit bounds only on the FIRST render (initialFitDone=false).
        // After that, never move the map — the user controls zoom/pan freely.
        if (!renderPath.initialFitDone) {
            const allBounds = [...allLatLngs];
            if (allBounds.length === 1) {
                map.setView(allBounds[0], 16);
            } else if (allBounds.length > 1) {
                map.fitBounds(L.latLngBounds(allBounds), { padding: [50, 50] });
            }
            renderPath.initialFitDone = true;
            log('renderPath: initial fitBounds done — auto-zoom disabled for subsequent polls');
        }
        setTimeout(() => map.invalidateSize(), 200);
    }
    renderPath.initialFitDone = false;   // reset on page load

    // ── Fix 3: Customer pins — correct colors ─────────────────
    // visited  → dark green #15803d
    // planned  → blue       #3b82f6
    // (skipped would be yellow but we don't have that field yet → remains blue)
    function renderCustomers(custList) {
        customerLayer.clearLayers();
        let drawn = 0;
        custList.forEach(c => {
            if (!c.lat || !c.lng) { warn('Customer "%s" missing coords — skip', c.name); return; }
            const color   = c.visited ? '#15803d' : '#3b82f6';
            const label   = c.visited ? '✓ Visited' : '○ Planned';
            L.circleMarker([c.lat, c.lng], {
                radius: 8, color: '#fff', fillColor: color, fillOpacity: 0.9, weight: 2,
            })
            .bindPopup(`<b>${c.name}</b><br/>${label}`)
            .addTo(customerLayer);
            drawn++;
            log('Customer pin: "%s" lat=%.6f lng=%.6f color=%s', c.name, c.lat, c.lng, color);
        });
        log('renderCustomers: %d pins drawn', drawn);
    }

    // ── Initial render ────────────────────────────────────────
    const isLiveInit = initStatus === 'live';
    renderCustomers(customers);
    renderPath(points, isLiveInit);

    // ── Fix 4: Live polling — re-render on every new point ────
    let knownPointCount = points.length;
    let currentStatus   = initStatus;
    let currentIsLive   = isLiveInit;
    let pollErrors      = 0;

    async function pollMap() {
        try {
            const res  = await fetch(`/salesperson_tracking/moving_map_data/${trackerId}`);
            if (!res.ok) { warn('pollMap HTTP %d', res.status); pollErrors++; return; }
            const data = await res.json();
            if (!data.ok) { warn('pollMap ok=false', data); return; }
            pollErrors = 0;

            const newIsLive = !!data.is_tracking;
            const newStatus = newIsLive ? 'live' : 'offline';

            log('pollMap: status=%s points=%d last_lat=%s', newStatus, data.points.length, data.last_lat);

            const statusChanged = newStatus !== currentStatus;
            if (statusChanged) {
                currentStatus = newStatus;
                currentIsLive = newIsLive;
                updateStatus(newStatus, newIsLive ? 'Live' : 'Offline');
            }

            // Re-render path whenever point count or status changes
            if (data.points.length !== knownPointCount || statusChanged) {
                log('pollMap: re-rendering (was %d pts → %d pts, statusChanged=%s)',
                knownPointCount, data.points.length, statusChanged);
                knownPointCount = data.points.length;
                await renderPath(data.points, newIsLive);
                if (currentMarker?.bringToFront) currentMarker.bringToFront();
            }

            // Always re-render customer pins on every poll.
            // Comparing counts is unreliable — a customer can flip visited→blue
            // if current_checkin_id clears between polls. Always trust server state.
            if (data.customers && data.customers.length) {
                customers = data.customers;
                renderCustomers(customers);
                log('pollMap: customer pins synced — total=%d visited=%d',
                customers.length, customers.filter(c => c.visited).length);
            }
        } catch(e) {
            pollErrors++;
            err('pollMap error (consecutive=%d):', pollErrors, e);
        }
    }

    let pollTimeoutId = null;

    function schedulePoll() {
        // Poll every 2s when live (to catch each GPS fix), 10s when offline
        const interval = currentStatus === 'live' ? 2000 : 10000;
        pollTimeoutId = setTimeout(async () => { await pollMap(); schedulePoll(); }, interval);
    }

    // Resume polling immediately when tab becomes visible again
    // (browser may have suspended setTimeout while tab was hidden)
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            if (pollTimeoutId) { clearTimeout(pollTimeoutId); pollTimeoutId = null; }
            pollMap().then(schedulePoll);
            log('Tab became visible — poll restarted');
        }
    });

    schedulePoll();
    log('Polling started. Status=%s interval=%s', currentStatus, currentStatus === 'live' ? '2s' : '10s');

})();
