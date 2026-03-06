"""
External Feeds — pull real-world signals and inject scoped SYSTEM events.

Current feeds (no API key required):
- USGS earthquakes (global), filtered by area bounding box
- Open-Meteo weather (area center point)
"""

from __future__ import annotations

import json
import logging
import threading
import time
from urllib.request import urlopen
from urllib.error import URLError

from shared_state import bulletin

logger = logging.getLogger(__name__)


AREAS = {
    "stockholm": {
        "name": "Stockholm",
        "lat": 59.3293,
        "lon": 18.0686,
        "bbox": (17.7, 59.1, 18.5, 59.5),  # min_lon, min_lat, max_lon, max_lat
    },
    "sweden": {
        "name": "Sweden",
        "lat": 62.0,
        "lon": 15.0,
        "bbox": (11.0, 55.0, 24.5, 69.5),
    },
    "iran": {
        "name": "Iran",
        "lat": 32.0,
        "lon": 53.0,
        "bbox": (44.0, 25.0, 64.0, 40.0),
    },
}


class ExternalFeedRunner:
    def __init__(self, area_key: str = "stockholm", interval: int = 120):
        self.area_key = area_key if area_key in AREAS else "stockholm"
        self.area = AREAS[self.area_key]
        self.interval = max(30, int(interval))
        self._running = False
        self._thread: threading.Thread | None = None
        self._seen_quakes: set[str] = set()
        self._seen_eonet: set[str] = set()
        self._last_weather_level = 0
        self._last_weather_status = 0.0

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="external-feeds")
        self._thread.start()
        bulletin.post(
            source="EXT_FEED",
            event_type="EXTERNAL_FEEDS_ONLINE",
            domain="SYSTEM",
            severity="INFO",
            source_layer="SYSTEM",
            payload={
                "message": f"External feeds enabled for {self.area['name']}",
                "area": self.area_key,
                "interval_sec": self.interval,
            },
            tags=["external", "feeds"],
        )

    def stop(self):
        self._running = False

    def _loop(self):
        # Poll immediately, then on interval
        while self._running:
            self._poll_cycle_summary("start")
            self._poll_earthquakes()
            self._poll_eonet_hazards()
            self._poll_weather()
            self._poll_cycle_summary("end")
            for _ in range(self.interval):
                if not self._running:
                    return
                time.sleep(1)

    def _poll_cycle_summary(self, phase: str):
        bulletin.post(
            source="EXT_FEED",
            event_type="EXTERNAL_POLL",
            domain="SYSTEM",
            severity="INFO",
            source_layer="API",
            payload={
                "message": f"External feed poll {phase} ({self.area['name']})",
                "area": self.area_key,
                "interval_sec": self.interval,
            },
            tags=["external", "feeds", "poll", self.area_key],
        )

    def _fetch_json(self, url: str) -> dict | None:
        try:
            with urlopen(url, timeout=8) as r:
                return json.loads(r.read().decode("utf-8"))
        except (URLError, TimeoutError, ValueError) as e:
            logger.warning(f"[EXT_FEED] fetch failed: {e}")
            return None

    def _in_bbox(self, lon: float, lat: float) -> bool:
        min_lon, min_lat, max_lon, max_lat = self.area["bbox"]
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

    def _poll_earthquakes(self):
        data = self._fetch_json(
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
        )
        if not data:
            return
        features = data.get("features", [])
        for f in features:
            quake_id = f.get("id")
            if not quake_id or quake_id in self._seen_quakes:
                continue

            coords = ((f.get("geometry") or {}).get("coordinates") or [None, None])
            lon, lat = coords[0], coords[1]
            if lon is None or lat is None or not self._in_bbox(float(lon), float(lat)):
                continue

            self._seen_quakes.add(quake_id)
            mag = float((f.get("properties") or {}).get("mag") or 0.0)
            place = (f.get("properties") or {}).get("place", "nearby region")
            sev = "LOW"
            if mag >= 6.0:
                sev = "CRITICAL"
            elif mag >= 5.0:
                sev = "HIGH"
            elif mag >= 4.0:
                sev = "MEDIUM"

            bulletin.post(
                source="EXT_FEED",
                event_type="SEISMIC_ACTIVITY",
                domain="SYSTEM",
                severity=sev,
                source_layer="SENSOR",
                payload={
                    "message": f"Earthquake M{mag:.1f} detected in scoped area ({place}).",
                    "magnitude": mag,
                    "place": place,
                    "area": self.area_key,
                },
                tags=["external", "seismic", self.area_key],
            )

    def _poll_weather(self):
        lat = self.area["lat"]
        lon = self.area["lon"]
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=precipitation,wind_speed_10m,wind_gusts_10m,temperature_2m"
            "&timezone=auto"
        )
        data = self._fetch_json(url)
        if not data:
            return
        cur = data.get("current", {})
        precip = float(cur.get("precipitation") or 0.0)
        wind = float(cur.get("wind_speed_10m") or 0.0)
        gust = float(cur.get("wind_gusts_10m") or 0.0)
        temp = float(cur.get("temperature_2m") or 0.0)

        # Always emit periodic weather status so external input is visible.
        now = time.time()
        if now - self._last_weather_status >= max(60, self.interval):
            self._last_weather_status = now
            bulletin.post(
                source="EXT_FEED",
                event_type="WEATHER_STATUS",
                domain="SYSTEM",
                severity="INFO",
                source_layer="SENSOR",
                payload={
                    "message": (
                        f"Weather status {self.area['name']}: precip={precip} mm, "
                        f"wind={wind} km/h, gust={gust} km/h, temp={temp}°C."
                    ),
                    "precipitation_mm": precip,
                    "wind_speed_kmh": wind,
                    "wind_gust_kmh": gust,
                    "temperature_c": temp,
                    "area": self.area_key,
                },
                tags=["external", "weather", "status", self.area_key],
            )

        # 0=normal, 1=watch, 2=alert
        level = 0
        if precip >= 6 or gust >= 50:
            level = 2
        elif precip >= 2 or gust >= 35 or wind >= 30:
            level = 1

        if level == 0 or level == self._last_weather_level:
            self._last_weather_level = level
            return

        self._last_weather_level = level
        sev = "HIGH" if level == 2 else "MEDIUM"
        bulletin.post(
            source="EXT_FEED",
            event_type="WEATHER_ALERT",
            domain="SYSTEM",
            severity=sev,
            source_layer="SENSOR",
            payload={
                "message": (
                    f"Weather alert for {self.area['name']}: precipitation={precip} mm, "
                    f"wind={wind} km/h, gust={gust} km/h, temp={temp}°C."
                ),
                "precipitation_mm": precip,
                "wind_speed_kmh": wind,
                "wind_gust_kmh": gust,
                "temperature_c": temp,
                "area": self.area_key,
            },
            tags=["external", "weather", self.area_key],
        )

    def _poll_eonet_hazards(self):
        """NASA EONET open natural hazard events (wildfires, storms, floods, volcano, etc.)."""
        data = self._fetch_json("https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=30&limit=200")
        if not data:
            return

        for e in data.get("events", []):
            eid = str(e.get("id") or "")
            if not eid or eid in self._seen_eonet:
                continue

            geoms = e.get("geometry") or []
            in_area = False
            last_lat = None
            last_lon = None
            for g in geoms:
                coords = g.get("coordinates")
                # Point = [lon, lat], Polygon-ish arrays ignored for now.
                if isinstance(coords, list) and len(coords) >= 2 and isinstance(coords[0], (int, float)):
                    lon = float(coords[0])
                    lat = float(coords[1])
                    last_lon, last_lat = lon, lat
                    if self._in_bbox(lon, lat):
                        in_area = True
                        break

            if not in_area:
                continue

            self._seen_eonet.add(eid)
            title = e.get("title", "Hazard event")
            cats = [c.get("title", "") for c in (e.get("categories") or [])]
            cat_str = ", ".join([c for c in cats if c]) or "Hazard"
            sev = "MEDIUM"
            if any(k in cat_str.lower() for k in ("volcano", "wildfires", "severe storms")):
                sev = "HIGH"

            bulletin.post(
                source="EXT_FEED",
                event_type="NATURAL_HAZARD_EVENT",
                domain="SYSTEM",
                severity=sev,
                source_layer="API",
                payload={
                    "message": f"NASA EONET hazard in scoped area: {title} ({cat_str}).",
                    "hazard_id": eid,
                    "categories": cats,
                    "lat": last_lat,
                    "lon": last_lon,
                    "area": self.area_key,
                },
                tags=["external", "eonet", "hazard", self.area_key],
            )
