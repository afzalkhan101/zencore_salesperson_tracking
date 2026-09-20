
(function () {
    "use strict";
    function navigateWithSalesman(salesmanId) {
        var cfg = document.getElementById('dash-config');
        var period = cfg ? cfg.dataset.period : 'today';
        var url;
        if (period === 'custom' && cfg && cfg.dataset.dateFrom && cfg.dataset.dateTo) {
            url = '/salesperson/dashboard?date_from=' + cfg.dataset.dateFrom + '&date_to=' + cfg.dataset.dateTo;
        } else {
            url = '/salesperson/dashboard?period=' + period;
        }
        if (salesmanId) { url += '&salesman_id=' + salesmanId; }
        window.location.href = url;
    }

    function openTracker(trackerId) {

        var url = '/web#model=salesperson.tracker&view_type=form&id=' + trackerId;
        if (window.parent && window.parent !== window) {
            window.parent.location.href = url;
        } else {
            window.location.href = url;
        }
    }

    window.openTracker = openTracker;

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
            if (ev.key === 'Escape') { closeList(); input.blur(); }
        });

        options.forEach(function (opt) {
            opt.addEventListener('click', function () {
                navigateWithSalesman(opt.dataset.id || '');
            });
        });

        document.addEventListener('click', function (ev) {
            if (!wrap.contains(ev.target)) { closeList(); }
        });
    }

    function initLiveMap() {
        var cfg = document.getElementById('dash-config');
        if (!cfg || cfg.dataset.isLive !== '1') return;
        var mapEl = document.getElementById('live-map');
        if (!mapEl || typeof L === 'undefined') return;

        var map = L.map('live-map', { zoomControl: true }).setView([23.7808875, 90.2792371], 12);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors', maxZoom: 19
        }).addTo(map);

        setTimeout(function () { map.invalidateSize(); }, 200);

        var salesmanMarkers = {};
        var customerMarkers = {};
        var bounds = [];
        var fitted = false;

        function pinIcon(html, w, h) {
            return L.divIcon({ className: 'x-marker', html: html, iconSize: [w, h], iconAnchor: [w / 2, h] });
        }
        function salesmanHtml(s) {
            var pulse = (s.status === 'moving' || s.status === 'at_customer') ? ' pulse' : '';
            return '<div class="map-pin">' +
                   '<div class="map-pin-label">' + s.name + '</div>' +
                   '<div class="map-pin-dot' + pulse + '" style="background:' + s.status_color + '"></div>' +
                   '</div>';
        }

        function render(data) {
            (data.trackers || []).forEach(function (s) {
                if (!s.lat || !s.lng) return;
                var latlng = [s.lat, s.lng];
                bounds.push(latlng);
                if (salesmanMarkers[s.id]) {
                    salesmanMarkers[s.id].setLatLng(latlng);
                    salesmanMarkers[s.id].setIcon(pinIcon(salesmanHtml(s), 90, 46));
                } else {
                    salesmanMarkers[s.id] = L.marker(latlng, { icon: pinIcon(salesmanHtml(s), 90, 46) }).addTo(map);
                }
                var row = document.querySelector('tr[data-tracker-id="' + s.id + '"]');
                var cell = row ? row.querySelector('.rep-status-cell') : null;
                if (cell) {
                    cell.querySelector('.status-dot').style.background = s.status_color;
                    cell.querySelector('span:last-child').textContent = s.status_label;
                }
            });
            (data.customers || []).forEach(function (c) {
                if (!c.lat || !c.lng) return;
                var latlng = [c.lat, c.lng];
                bounds.push(latlng);
                if (!customerMarkers[c.id]) {
                    var icon = pinIcon('<div class="cust-pin" title="' + c.name + '"></div>', 11, 11);
                    customerMarkers[c.id] = L.marker(latlng, { icon: icon }).bindTooltip(c.name).addTo(map);
                }
            });
            if (bounds.length && !fitted) {
                
                var MIN_FIT_ZOOM = 11;
                var idealZoom = map.getBoundsZoom(L.latLngBounds(bounds), false, [40, 40]);
                if (idealZoom < MIN_FIT_ZOOM) {
                    map.setView(bounds[0], MIN_FIT_ZOOM);
                } else {
                    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
                }
                fitted = true;
            }
        }

        function poll() {
            var salesmanId = cfg.dataset.salesmanId || '';
            var url = '/salesperson/dashboard/data';
            if (salesmanId) { url += '?salesman_id=' + salesmanId; }
            fetch(url).then(function (r) { return r.json(); }).then(function (data) {
                if (data.ok) { render(data); }
            }).catch(function (err) { console.error('[Dashboard] live poll failed:', err); });
        }
        poll();
        setInterval(poll, 8000);
    }

    function initAll() {
        initSalesmanSearch();
        initLiveMap();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
