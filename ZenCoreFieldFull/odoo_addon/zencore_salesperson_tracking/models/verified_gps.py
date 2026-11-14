"""Server counterpart of prepareMapSegments in static/src/js/templates.js.
Only measured, corroborated GPS movement contributes to the distance.
"""
import math


def _meters(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2-p1, math.radians(b[1]-a[1])
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 12742000 * math.atan2(math.sqrt(max(0, h)), math.sqrt(max(0, 1-h)))


def verified_distance_km(rows):
    """Rows are (latitude, longitude, accuracy, tracked_at), ascending by time."""
    segments, segment, pending = [], [], None
    previous_time = None
    def flush():
        nonlocal segment
        if segment:
            segments.append(segment)
        segment = []
    for lat, lng, acc, stamp in rows:
        lat, lng, acc = float(lat or 0), float(lng or 0), float(acc or 0)
        if not (math.isfinite(lat) and math.isfinite(lng) and math.isfinite(acc)
                and abs(lat) <= 90 and abs(lng) <= 180 and (lat or lng)
                and 0 < acc <= 20):
            continue
        p = (lat, lng, acc, stamp)
        if previous_time is not None and stamp is not None and stamp <= previous_time:
            flush()
            pending = None
        previous_time = stamp or previous_time
        if not segment:
            if pending and stamp and pending[3]:
                dt = (stamp-pending[3]).total_seconds()
                dist = _meters(pending, p)
                if 0 < dt <= 90 and dist <= 80 and dist/dt <= 18:
                    segment.append(pending)
                    if dist >= 18:
                        segment.append(p)
                    pending = None
                    continue
            pending = p
            continue
        last = segment[-1]
        dt = (stamp-last[3]).total_seconds() if stamp and last[3] else 0
        dist = _meters(last, p)
        if dt <= 0 or dt > 90:
            flush()
            pending = p
            continue
        noise = min(35, max(18, math.hypot(last[2] or 20, acc)*1.15))
        if dist < noise:
            pending = None
            continue
        if dist > 180 or dist/dt > 18:
            if pending and stamp and pending[3]:
                pd = (stamp-pending[3]).total_seconds()
                pm = _meters(pending, p)
                if 0 < pd <= 90 and pm <= 80 and pm/pd <= 18:
                    flush()
                    segment.append(pending)
                    if pm >= 18:
                        segment.append(p)
                    pending = None
                    continue
            pending = p
            continue
        pending = None
        segment.append(p)
    flush()
    return sum(_meters(a, b) for seg in segments for a, b in zip(seg, seg[1:])) / 1000.0
