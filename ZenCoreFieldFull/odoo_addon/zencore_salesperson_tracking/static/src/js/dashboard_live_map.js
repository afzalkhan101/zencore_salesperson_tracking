(function () {
    "use strict";

    var liveState = {
        map: null,
        salesmanMarkers: {},
        customerMarkers: {},
        firstFitDone: false,
        lastPayload: null,
        mapFilter: 'all',
        selectedUserId: null,
        pollRunning: false,
    };

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function dashboardUrlWithSalesman(salesmanId) {
        var cfg = document.getElementById('dash-config');
        var period = cfg ? cfg.dataset.period : 'today';
        var url;
        if (period === 'custom' && cfg && cfg.dataset.dateFrom && cfg.dataset.dateTo) {
            url = '/salesperson/dashboard?date_from=' + encodeURIComponent(cfg.dataset.dateFrom) +
                  '&date_to=' + encodeURIComponent(cfg.dataset.dateTo);
        } else {
            url = '/salesperson/dashboard?period=' + encodeURIComponent(period || 'today');
        }
        if (salesmanId) {
            url += '&salesman_id=' + encodeURIComponent(salesmanId);
        }
        return url;
    }

    function navigateWithSalesman(salesmanId) {
        window.location.href = dashboardUrlWithSalesman(salesmanId);
    }

    function openTracker(trackerId) {
        var url = '/web#model=salesperson.tracker&view_type=form&id=' + encodeURIComponent(trackerId);
        if (window.parent && window.parent !== window) {
            window.parent.location.href = url;
        } else {
            window.location.href = url;
        }
    }

    function openMovementMap(trackerId) {
        window.location.href = '/salesperson_tracking/moving_map/' + encodeURIComponent(trackerId) + '?_=' + Date.now();
    }

    function focusSalesman(trackerId) {
        var marker = liveState.salesmanMarkers[String(trackerId)] || liveState.salesmanMarkers[trackerId];
        if (!marker || !liveState.map) return false;
        var data = liveState.lastPayload;
        var found = data && (data.trackers || []).find(function(r) { return String(r.id) === String(trackerId); });
        if (found) liveState.selectedUserId = String(found.user_id);
        liveState.map.setView(marker.getLatLng(), 16, { animate: true, duration: .6 });
        marker.openPopup();
        return true;
    }

    function closeVisitDetails() {
        document.getElementById('visit-details-overlay').style.display = 'none';
    }
    function visitEscape(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
            return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
        });
    }
    function visitTable(title, rows, completed) {
        var head = '<div style="background:' + (completed ? '#ecfdf5' : '#fff1f2') + ';padding:14px;border-radius:10px 10px 0 0;font-weight:700;color:' + (completed ? '#047857' : '#be123c') + '">' + title + ' (' + rows.length + ')</div>';
        var content = rows.length ? rows.map(function (v) {
            return '<div style="padding:12px;border-bottom:1px solid #e2e8f0">' +
                '<strong>' + visitEscape(v.customer) + '</strong> <small style="color:#64748b">' + visitEscape(v.date) + '</small>' +
                '<div style="font-size:12px;color:#64748b;margin-top:4px">' + visitEscape(v.address) + '</div>' +
                (completed ? '<div style="font-size:12px;margin-top:5px">In: ' + visitEscape(v.checkin || '—') + ' | Out: ' + visitEscape(v.checkout || '—') + ' | ' + visitEscape(v.duration) + ' min</div>' : '<div style="font-size:12px;margin-top:5px;color:#be123c">' + visitEscape(v.status) + '</div>') +
                '</div>';
        }).join('') : '<p style="padding:15px;color:#64748b">No visits found.</p>';
        return '<section style="border:1px solid #e2e8f0;border-radius:10px;overflow:hidden">' + head + content + '</section>';
    }
    async function openVisitDetails(trackerId) {
        var overlay = document.getElementById('visit-details-overlay');
        var content = document.getElementById('visit-details-content');
        if (!overlay || !content) return;
        overlay.style.display = 'block';
        content.textContent = 'Loading visits…';
        // The server-rendered dashboard dates are authoritative, including custom ranges.
        var config = document.querySelector('[data-date-from][data-date-to]');
        var from = config && config.dataset.dateFrom;
        var to = config && config.dataset.dateTo;
        if (!from || !to) {
            content.textContent = 'Dashboard date filters are unavailable. Please refresh the page.';
            return;
        }
        try {
            var url = '/salesperson/dashboard/visit_details?' + new URLSearchParams({tracker_id: String(trackerId), date_from: from, date_to: to});
            var response = await fetch(url, {credentials:'same-origin'});
            if (!response.ok) throw new Error('Request failed');
            var data = await response.json();
            if (!data.ok) throw new Error(data.error || 'Unable to load visits');
            document.getElementById('visit-details-heading').textContent = 'Visit Details – ' + (data.salesman || 'Salesperson');
            document.getElementById('visit-details-summary').textContent = from + ' to ' + to + ' | Planned: ' + data.total + ' | Completed: ' + data.completed.length + ' | Remaining: ' + data.incomplete.length;
            content.innerHTML = visitTable('Completed Visits', data.completed, true) + visitTable('Pending / Missed Visits', data.incomplete, false);
        } catch (err) { content.textContent = 'Could not load visit details: ' + err.message; }
    }
    // Delegated click handler works after dashboard refreshes and avoids inline JS scope issues.
    document.addEventListener('click', function (event) {
        var button = event.target.closest('.visit-details-trigger');
        if (button) {
            event.preventDefault();
            openVisitDetails(button.dataset.trackerId);
        }
    });
    window.openVisitDetails = openVisitDetails;
    window.closeVisitDetails = closeVisitDetails;
    window.openTracker = openTracker;
    window.openMovementMap = openMovementMap;
    window.focusSalesman = focusSalesman;

    function initDashboardDateMode() {
        var form = document.getElementById('zc-date-form');
        var mode = document.getElementById('zc-date-mode');
        if (!form || !mode) return;
        var from = form.querySelector('[name="date_from"]');
        var to = form.querySelector('[name="date_to"]');
        var separator = document.getElementById('zc-date-separator');
        if (!from || !to) return;
        function syncMode() {
            var single = mode.value === 'single';
            to.hidden = single;
            to.disabled = single;
            if (separator) separator.hidden = single;
        }
        mode.addEventListener('change', syncMode);
        form.addEventListener('submit', function(e) {
            if (mode.value === 'single') {
                to.disabled = false;
                to.value = from.value;
            }
            if (!from.value || !to.value || from.value > to.value) {
                e.preventDefault();
                // Keep the UI editable: invalid ranges are not sent to Odoo.
                to.disabled = mode.value === 'single';
                from.setCustomValidity('Choose a valid date range');
                from.reportValidity();
            }
        });
        from.addEventListener('input', function() { from.setCustomValidity(''); });
        to.addEventListener('input', function() { from.setCustomValidity(''); });
        syncMode();
    }

    function filteredMarkers() {
        var payload = liveState.lastPayload || {};
        return (payload.trackers || []).filter(function(s) {
            return liveState.mapFilter === 'all' ||
                (liveState.mapFilter === 'active' ? s.status !== 'offline' : s.status === 'offline');
        });
    }

    function initMapSearch() {
        var input = document.getElementById('map-salesperson-search');
        var list = document.getElementById('map-salesperson-suggestions');
        if (!input || !list) return;
        function fill() {
            var q = input.value.trim().toLowerCase();
            var payload = liveState.lastPayload || {};
            var rows = (payload.rows || []).filter(function(s) {
                return q && String(s.name || '').toLowerCase().includes(q);
            }).slice(0, 12);
            list.innerHTML = '';
            rows.forEach(function(s) {
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'map-suggestion-item';
                btn.textContent = s.name + ' · ' + (s.status === 'offline' ? 'Inactive' : 'Active');
                btn.onclick = function() { focusUser(s); list.innerHTML = ''; input.value = s.name; };
                list.appendChild(btn);
            });
            if (q && !rows.length) {
                var none = document.createElement('div');
                none.className = 'map-no-result';
                none.textContent = 'No matching salesperson in selected scope';
                list.appendChild(none);
            }
        }
        input.addEventListener('input', fill);
        input.addEventListener('focus', fill);
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') list.innerHTML = '';
            if (e.key === 'Enter' && list.querySelector('button')) {
                e.preventDefault(); list.querySelector('button').click();
            }
        });
        document.addEventListener('click', function(e) { if (!e.target.closest('.map-search-wrap')) list.innerHTML = ''; });
        document.querySelectorAll('[data-map-filter]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                liveState.mapFilter = btn.dataset.mapFilter;
                document.querySelectorAll('[data-map-filter]').forEach(function(b) {
                    b.classList.toggle('selected', b === btn);
                });
                if (liveState.lastPayload) renderMap(liveState.lastPayload);
                fill();
            });
        });
    }

    function focusUser(s) {
        liveState.selectedUserId = String(s.user_id);
        var payload = liveState.lastPayload || {};
        var markerRow = (payload.trackers || []).find(function(t) { return String(t.user_id) === String(s.user_id); });
        var notice = document.getElementById('map-search-feedback');
        if (!markerRow || !focusSalesman(markerRow.id)) {
            if (notice) notice.textContent = s.name + ': location unavailable';
            return;
        }
        // Keep searched-for marker visible even if a status filter was active.
        liveState.mapFilter = 'all';
        document.querySelectorAll('[data-map-filter]').forEach(function(b) {
            b.classList.toggle('selected', b.dataset.mapFilter === 'all');
        });
        renderMap(payload);
        focusSalesman(markerRow.id);
        if (notice) notice.textContent = s.name + ' · Last recorded position';
    }

    function relativeTime(epoch) {
        epoch = Number(epoch || 0);
        if (!epoch) return '—';
        var diff = Math.max(0, Math.floor((Date.now() - epoch) / 1000));
        if (diff < 10) return 'just now';
        if (diff < 60) return diff + ' sec ago';
        var mins = Math.floor(diff / 60);
        if (mins < 60) return mins + ' min ago';
        var hrs = Math.floor(mins / 60);
        if (hrs < 24) return hrs + 'h ago';
        return Math.floor(hrs / 24) + 'd ago';
    }

    function pinIcon(html, w, h) {
        return L.divIcon({
            className: 'x-marker',
            html: html,
            iconSize: [w, h],
            iconAnchor: [w / 2, h],
        });
    }

    // The server's five-minute GPS freshness rule is authoritative for status.
    // Display-only animation never changes a tracking/session state.
    function isLiveSalesperson(s) {
        return Boolean(s && s.status && s.status !== 'offline');
    }

    function salesmanHtml(s) {
        var active = isLiveSalesperson(s);
        var cls = active ? 'zc-walker-active' : 'zc-walker-inactive';
        var label = active ? 'Active' : 'Inactive';
        // Shared marker asset is identical to Movement Map and Mobile Map.
        // CSS applies green pulse only to active staff; inactive stays static gray.
        var walker = '<img class="zc-walker-svg" src="/zencore_salesperson_tracking/static/src/img/walking_salesperson_briefcase.svg" ' +
            'width="48" height="72" alt="Walking salesperson with small hand-held briefcase" />';
        return '<div class="zc-walker-marker ' + cls + '" role="img" aria-label="' +
            escapeHtml(s.name) + ', ' + label + '" title="' + escapeHtml(s.name) + ' — ' + label + '">' +
            '<div class="zc-walker-name">' + escapeHtml(s.name) + '</div>' +
            '<div class="zc-walker-stage"><span class="zc-walker-pulse"></span>' + walker + '</div>' +
            '</div>';
    }

    function popupHtml(s) {
        var speed = Number(s.speed_kmh || 0).toFixed(1) + ' km/h';
        var accuracy = Number(s.accuracy || 0) > 0 ? Number(s.accuracy).toFixed(0) + ' m' : '—';
        var distance = Number(s.distance_km || 0).toFixed(1) + ' km';
        var visits = Number(s.covered || 0) + ' / ' + Number(s.total || 0);
        var location = s.location && s.location !== '—' ? s.location : 'Location name not available';
        return '<div class="map-popup">' +
            '<div class="map-popup-name">' + escapeHtml(s.name) + '</div>' +
            '<div class="map-popup-status"><i style="background:' + escapeHtml(s.status_color) + '"></i>' + escapeHtml(s.status_label) + '</div>' +
            '<div class="map-popup-grid">' +
                '<span>Speed</span><b>' + escapeHtml(speed) + '</b>' +
                '<span>Last update</span><b>' + escapeHtml(relativeTime(s.last_seen_epoch)) + '</b>' +
                '<span>Distance</span><b>' + escapeHtml(distance) + '</b>' +
                '<span>Visits</span><b>' + escapeHtml(visits) + '</b>' +
                '<span>Accuracy</span><b>' + escapeHtml(accuracy) + '</b>' +
                '<span>GPS health</span><b style="color:' + escapeHtml(s.gps_health_color) + '">' + escapeHtml(s.gps_health) + '</b>' +
            '</div>' +
            '<div class="map-popup-location">' + escapeHtml(location) + '</div>' +
            '<div class="map-popup-actions">' +
                '<button class="map-popup-btn primary" onclick="openMovementMap(' + Number(s.id) + ')">Movement Map</button>' +
                '<button class="map-popup-btn" onclick="openTracker(' + Number(s.id) + ')">Details</button>' +
            '</div>' +
        '</div>';
    }

    function renderMap(data) {
        if (!liveState.map) return;
        var trackers = filteredMarkers();
        var customers = data.customers || [];
        var seenTrackers = {};
        var seenCustomers = {};
        var trackerBounds = [];

        trackers.forEach(function (s) {
            if (!s.lat || !s.lng) return;
            var key = String(s.id);
            var latlng = [Number(s.lat), Number(s.lng)];
            trackerBounds.push(latlng);
            seenTrackers[key] = true;
            var live = isLiveSalesperson(s);
            var iconKey = [s.name, live ? "active" : "inactive"].join("|");
            var icon = pinIcon(salesmanHtml(s), 112, 91);
            var marker = liveState.salesmanMarkers[key];
            if (!marker) {
                marker = L.marker(latlng, { icon: icon, keyboard: true }).addTo(liveState.map);
                marker._zcIconKey = iconKey;
                liveState.salesmanMarkers[key] = marker;
            } else {
                var oldPos = marker.getLatLng();
                if (oldPos.lat !== latlng[0] || oldPos.lng !== latlng[1]) {
                    marker.setLatLng(latlng);
                }
                // Do not recreate every icon at each 10-second poll: Leaflet
                // replaces the DOM and would restart pulses and close popups.
                if (marker._zcIconKey !== iconKey) {
                    marker.setIcon(icon);
                    marker._zcIconKey = iconKey;
                }
            }
            marker.bindPopup(popupHtml(s), { maxWidth: 300 });
        });

        Object.keys(liveState.salesmanMarkers).forEach(function (key) {
            if (!seenTrackers[key]) {
                liveState.map.removeLayer(liveState.salesmanMarkers[key]);
                delete liveState.salesmanMarkers[key];
            }
        });

        customers.forEach(function (c) {
            if (!c.lat || !c.lng) return;
            var key = String(c.id);
            seenCustomers[key] = true;
            var css = c.visited ? 'visited' : 'pending';
            var icon = pinIcon('<div class="cust-pin ' + css + '" title="' + escapeHtml(c.name) + '"></div>', 12, 12);
            var marker = liveState.customerMarkers[key];
            if (!marker) {
                marker = L.marker([Number(c.lat), Number(c.lng)], { icon: icon })
                    .bindTooltip(escapeHtml(c.name))
                    .addTo(liveState.map);
                liveState.customerMarkers[key] = marker;
            } else {
                marker.setLatLng([Number(c.lat), Number(c.lng)]);
                marker.setIcon(icon);
            }
        });

        Object.keys(liveState.customerMarkers).forEach(function (key) {
            if (!seenCustomers[key]) {
                liveState.map.removeLayer(liveState.customerMarkers[key]);
                delete liveState.customerMarkers[key];
            }
        });

        // Fit only around salesperson positions. Customer pins can be widely spread
        // and should not force the manager map to zoom out to an unusable country view.
        if (!liveState.firstFitDone && trackerBounds.length) {
            if (trackerBounds.length === 1) {
                liveState.map.setView(trackerBounds[0], 15);
            } else {
                liveState.map.fitBounds(L.latLngBounds(trackerBounds), { padding: [55, 55], maxZoom: 15 });
            }
            liveState.firstFitDone = true;
        }
    }

    function setText(id, value) {
        var el = document.getElementById(id);
        if (el && el.textContent !== String(value)) {
            el.textContent = value;
            el.classList.remove('metric-changed');
            void el.offsetWidth;
            el.classList.add('metric-changed');
        }
    }

    function updateKpis(summary) {
        if (!summary) return;
        setText('kpi-total-reps', summary.total_reps);
        setText('kpi-active', summary.active_count);
        setText('kpi-at-customer', summary.at_customer_count);
        setText('kpi-moving', summary.moving_count);
        setText('kpi-idle', summary.idle_count);
        setText('kpi-offline', summary.offline_count);
        setText('kpi-total-visits', summary.total_planned);
        setText('kpi-completed', summary.total_covered);
        setText('kpi-visit-rate', summary.visit_rate);
        setText('kpi-missed', summary.missed_count);
        setText('kpi-distance', Number(summary.total_distance || 0).toFixed(1));
        setText('map-active-count', summary.active_count);
        setText('map-inactive-count', summary.inactive_count);
    }

    function syncRosterRows(rows) {
        var body = document.getElementById('rep-table-body');
        if (!body) return;
        var currentIds = Array.prototype.map.call(body.querySelectorAll('tr[data-user-id]'), function(el) {
            return String(el.dataset.userId) + ':' + String(el.dataset.trackerId);
        }).sort().join(',');
        var nextIds = rows.map(function(r) { return String(r.user_id) + ':' + String(r.id); }).sort().join(',');
        if (currentIds === nextIds) return; // Avoid DOM replacement on every GPS poll.
        body.innerHTML = rows.map(function(r, i) {
            var id = Number(r.id || 0), uid = Number(r.user_id);
            var safeName = escapeHtml(r.name), safeInitials = escapeHtml(r.initials);
            return '<tr data-user-id="' + uid + '" data-tracker-id="' + id + '">' +
                '<td class="row-number">' + (i + 1) + '</td>' +
                '<td><div class="rep-cell"><div class="rep-avatar" style="background:linear-gradient(135deg,#08639C,#28A745)">' + safeInitials + '</div><div><div class="rep-name">' + safeName + '</div><div class="rep-location">' + escapeHtml(r.location) + '</div></div></div></td>' +
                '<td class="cell-planned">' + Number(r.total || 0) + '</td>' +
                '<td class="cell-visited positive">' + Number(r.covered || 0) + '</td>' +
                '<td class="cell-missed negative">' + Number(r.missed || 0) + '</td>' +
                '<td><div class="visit-rate-bar"><span class="cell-pct">' + Number(r.pct || 0) + '%</span><div class="vr-track"><div class="vr-fill" style="width:' + Number(r.pct || 0) + '%"></div></div></div></td>' +
                '<td class="cell-distance">' + escapeHtml(r.distance) + '</td>' +
                '<td class="cell-tracking-time">' + escapeHtml(r.tracking_time) + '</td>' +
                '<td class="cell-first-start">' + escapeHtml(r.first_start) + '</td>' +
                '<td><span class="cell-last-update" data-epoch="' + Number(r.last_seen_epoch || 0) + '">' + escapeHtml(r.last_update) + '</span></td>' +
                '<td><span class="gps-health-pill"><i></i><span class="gps-health-text">' + escapeHtml(r.gps_health) + '</span></span></td>' +
                '<td><span class="status-pill rep-status-cell"><i class="status-dot"></i><span>' + escapeHtml(r.status_label) + '</span></span></td>' +
                '<td><div class="row-actions">' +
                (id ? '<button type="button" class="action-btn primary" data-focus-tracker="' + id + '">Live</button><button type="button" class="action-btn" data-open-route="' + id + '">Route</button><button type="button" class="action-btn visit-details-trigger" data-tracker-id="' + id + '">Details</button>' : '') +
                '</div></td></tr>';
        }).join('');
        var count = document.getElementById('table-row-count');
        if (count) count.textContent = rows.length;
    }

    function updateRows(rows) {
        syncRosterRows(rows || []);
        (rows || []).forEach(function (r) {
            var row = document.querySelector('tr[data-user-id="' + r.user_id + '"]');
            if (!row) return;
            var set = function (selector, value) {
                var el = row.querySelector(selector);
                if (el) el.textContent = value;
            };
            set('.cell-planned', r.total);
            set('.cell-visited', r.covered);
            set('.cell-missed', r.missed);
            set('.cell-pct', String(r.pct) + '%');
            var fill = row.querySelector('.vr-fill');
            if (fill) fill.style.width = String(r.pct) + '%';
            set('.cell-distance', r.distance);
            set('.cell-tracking-time', r.tracking_time);
            set('.cell-first-start', r.first_start || '—');
            var last = row.querySelector('.cell-last-update');
            if (last) {
                last.dataset.epoch = r.last_seen_epoch || 0;
                last.textContent = relativeTime(r.last_seen_epoch);
            }
            set('.rep-location', r.location || '—');
            var statusCell = row.querySelector('.rep-status-cell');
            if (statusCell) {
                var dot = statusCell.querySelector('.status-dot');
                var text = statusCell.querySelector('span:last-child');
                if (dot) dot.style.background = r.status_color;
                if (text) text.textContent = r.status_label;
            }
            var gps = row.querySelector('.gps-health-pill');
            if (gps) {
                gps.style.setProperty('--gps-color', r.gps_health_color);
                var gpsText = gps.querySelector('.gps-health-text');
                if (gpsText) gpsText.textContent = r.gps_health;
            }
            var liveBtn = row.querySelector('.action-btn.primary');
            if (liveBtn) liveBtn.disabled = r.status === 'offline';
        });
    }

    function updateRelativeTimes() {
        document.querySelectorAll('.cell-last-update[data-epoch]').forEach(function (el) {
            el.textContent = relativeTime(el.dataset.epoch);
        });
    }

    function updateActivities(activities) {
        var wrap = document.getElementById('activity-list');
        if (!wrap) return;
        if (!activities || !activities.length) {
            wrap.innerHTML = '<div class="side-empty">No recent activities yet.</div>';
            return;
        }
        wrap.innerHTML = activities.map(function (a) {
            return '<div class="activity-item">' +
                '<div class="activity-icon" style="background:' + escapeHtml(a.color) + '">' + escapeHtml(a.icon) + '</div>' +
                '<div class="activity-time">' + escapeHtml(a.time) + '</div>' +
                '<div class="activity-text">' + escapeHtml(a.text) + '</div>' +
            '</div>';
        }).join('');
    }

    function updateAlerts(alerts) {
        var wrap = document.getElementById('alert-list');
        if (!wrap) return;
        if (!alerts || !alerts.length) {
            wrap.innerHTML = '<div class="alert-item success"><span class="alert-icon">✓</span>' +
                '<div><strong>No tracking alerts</strong><small>Everything looks normal right now.</small></div></div>';
            return;
        }
        wrap.innerHTML = alerts.map(function (a) {
            return '<div class="alert-item ' + escapeHtml(a.level) + '">' +
                '<span class="alert-icon">' + escapeHtml(a.icon) + '</span>' +
                '<div><strong>' + escapeHtml(a.text) + '</strong><small>' + escapeHtml(a.detail) + '</small></div>' +
            '</div>';
        }).join('');
    }

    function updateRefreshMeta() {
        var el = document.getElementById('last-refresh-text');
        if (!el) return;
        var now = new Date();
        el.textContent = 'Last updated: ' + now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function initLiveDashboard() {
        var cfg = document.getElementById('dash-config');
        if (!cfg || cfg.dataset.isLive !== '1') return;
        var mapEl = document.getElementById('live-map');
        if (!mapEl || typeof L === 'undefined') return;

        liveState.map = L.map('live-map', { zoomControl: true, preferCanvas: true }).setView([23.8103, 90.4125], 12);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors',
            maxZoom: 19,
        }).addTo(liveState.map);
        setTimeout(function () { liveState.map.invalidateSize(); }, 150);

        initMapSearch();
        function poll() {
            if (liveState.pollRunning) return;
            liveState.pollRunning = true;
            var salesmanId = cfg.dataset.salesmanId || '';
            var url = '/salesperson/dashboard/data';
            if (salesmanId) url += '?salesman_id=' + encodeURIComponent(salesmanId);
            fetch(url, { cache: 'no-store' })
                .then(function (response) {
                    if (!response.ok) throw new Error('HTTP ' + response.status);
                    return response.json();
                })
                .then(function (data) {
                    if (!data.ok) return;
                    liveState.lastPayload = data;
                    renderMap(data);
                    updateKpis(data.summary || {});
                    updateRows(data.rows || []);
                    updateActivities(data.activities || []);
                    updateAlerts(data.alerts || []);
                    updateRefreshMeta();
                })
                .catch(function (err) {
                    console.error('[Dashboard] live poll failed:', err);
                    var el = document.getElementById('last-refresh-text');
                    if (el) el.textContent = 'Connection unavailable · showing last update';
                })
                .finally(function() { liveState.pollRunning = false; });
        }

        poll();
        setInterval(poll, 10000);
        setInterval(updateRelativeTimes, 5000);
    }

    function initAll() {
        document.addEventListener('click', function(e) {
            var focus = e.target.closest('[data-focus-tracker]');
            var route = e.target.closest('[data-open-route]');
            if (focus) focusSalesman(focus.dataset.focusTracker);
            if (route) openMovementMap(route.dataset.openRoute);
        });
        initDashboardDateMode();
        initLiveDashboard();
        updateRelativeTimes();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
