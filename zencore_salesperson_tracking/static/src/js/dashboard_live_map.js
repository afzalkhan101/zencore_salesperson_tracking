(function () {
    "use strict";

    var liveState = {
        map: null,
        salesmanMarkers: {},
        customerMarkers: {},
        firstFitDone: false,
        lastPayload: null,
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
        if (!marker || !liveState.map) return;
        liveState.map.setView(marker.getLatLng(), 16, { animate: true });
        marker.openPopup();
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
    async function openVisitDetails(salesmanId) {
        var overlay = document.getElementById('visit-details-overlay');
        var content = document.getElementById('visit-details-content');
        overlay.style.display = 'block';
        content.textContent = 'Loading visits…';
        var params = new URLSearchParams(window.location.search);
        var from = params.get('date_from'), to = params.get('date_to');
        if (!from || !to) {
            var now = new Date();
            var local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
            var today = local.toISOString().slice(0, 10);
            var period = params.get('period') || 'today';
            var start = new Date(local);
            if (period === 'yesterday') start.setDate(start.getDate() - 1);
            else if (period === 'weekly') start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
            else if (period === 'monthly') start.setDate(1);
            from = start.toISOString().slice(0, 10);
            to = period === 'yesterday' ? from : today;
        }
        try {
            var url = '/salesperson/dashboard/visit_details?' + new URLSearchParams({salesman_id: String(salesmanId), date_from: from, date_to: to});
            var response = await fetch(url, {credentials:'same-origin'});
            if (!response.ok) throw new Error('Request failed');
            var data = await response.json();
            if (!data.ok) throw new Error(data.error || 'Unable to load visits');
            document.getElementById('visit-details-heading').textContent = 'Visit Details – ' + (data.salesman || 'Salesperson');
            document.getElementById('visit-details-summary').textContent = from + ' to ' + to + ' | Planned: ' + data.total + ' | Completed: ' + data.completed.length + ' | Remaining: ' + data.incomplete.length;
            content.innerHTML = visitTable('Completed Visits', data.completed, true) + visitTable('Pending / Missed Visits', data.incomplete, false);
        } catch (err) { content.textContent = 'Could not load visit details: ' + err.message; }
    }
    window.openVisitDetails = openVisitDetails;
    window.closeVisitDetails = closeVisitDetails;
    window.openTracker = openTracker;
    window.openMovementMap = openMovementMap;
    window.focusSalesman = focusSalesman;

    function initSalesmanSearch() {
        var wrap = document.getElementById('salesman-search');
        var input = document.getElementById('salesman-search-input');
        var list = document.getElementById('salesman-search-list');
        if (!wrap || !input || !list) return;

        var options = Array.prototype.slice.call(list.querySelectorAll('.salesman-search-option'));
        function openList() { list.classList.add('open'); }
        function closeList() { list.classList.remove('open'); }
        function filterOptions() {
            var q = input.value.trim().toLowerCase();
            options.forEach(function (opt) {
                var text = opt.textContent.trim().toLowerCase();
                opt.classList.toggle('hidden', q.length > 0 && text.indexOf(q) === -1);
            });
        }

        input.addEventListener('focus', function () {
            input.select();
            filterOptions();
            openList();
        });
        input.addEventListener('input', function () {
            filterOptions();
            openList();
        });
        input.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape') {
                closeList();
                input.blur();
            }
            if (ev.key === 'Enter') {
                var visible = options.find(function (opt) { return !opt.classList.contains('hidden'); });
                if (visible) {
                    ev.preventDefault();
                    navigateWithSalesman(visible.dataset.id || '');
                }
            }
        });
        options.forEach(function (opt) {
            opt.addEventListener('click', function () {
                navigateWithSalesman(opt.dataset.id || '');
            });
        });
        document.addEventListener('click', function (ev) {
            if (!wrap.contains(ev.target)) closeList();
        });
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

    function salesmanHtml(s) {
        var pulse = (s.status === 'moving' || s.status === 'at_customer') ? ' pulse' : '';
        return '<div class="map-pin">' +
               '<div class="map-pin-label">' + escapeHtml(s.name) + '</div>' +
               '<div class="map-pin-dot' + pulse + '" style="background:' + escapeHtml(s.status_color) + '"></div>' +
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
        var trackers = data.trackers || [];
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
            var icon = pinIcon(salesmanHtml(s), 104, 48);
            var marker = liveState.salesmanMarkers[key];
            if (!marker) {
                marker = L.marker(latlng, { icon: icon }).addTo(liveState.map);
                liveState.salesmanMarkers[key] = marker;
            } else {
                marker.setLatLng(latlng);
                marker.setIcon(icon);
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
        if (el) el.textContent = value;
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
    }

    function updateRows(rows) {
        (rows || []).forEach(function (r) {
            var row = document.querySelector('tr[data-tracker-id="' + r.id + '"]');
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

        function poll() {
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
                    if (el) el.textContent = 'Refresh failed';
                });
        }

        poll();
        setInterval(poll, 10000);
        setInterval(updateRelativeTimes, 5000);
    }

    function initAll() {
        initSalesmanSearch();
        initLiveDashboard();
        updateRelativeTimes();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
