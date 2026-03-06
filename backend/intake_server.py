"""
Intake Server — citizen field report intake for MACS.

Serves a mobile-friendly web form and a POST /report endpoint that runs
submissions through the Verifier before posting to the bulletin board.

Endpoints:
  GET  /        → mobile HTML form (judges scan QR → open this)
  POST /report  → JSON submission → verifier → bulletin board
  GET  /qr      → QR code PNG pointing to this server's form
  GET  /status  → health check + bulletin stats
"""

import io
import json
import logging
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from dataclasses import asdict
from urllib.parse import urlparse, parse_qs
from typing import Optional

from shared_state import bulletin
from verifier import Verifier

logger = logging.getLogger(__name__)

INTAKE_PORT = 8766
CONTROL_TOKEN = os.getenv("MACS_CONTROL_TOKEN", "")
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_API_KEY", "")
CONTROL_AGENTS = {}
WORLD_STATE_MGR = None
PHOTO_STORE = {}         # {evt_id: base64_jpeg_string}
VALIDATION_STORE = {}    # {evt_id: {reporter_ids: set, count: int}}

# ── HTML ──────────────────────────────────────────────────────────────────────

FORM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>MACS Field Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0e17;color:#e5e7eb;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:20px 16px;
     background-image:radial-gradient(ellipse at top,rgba(6,182,212,0.03) 0%,transparent 50%)}
.hdr{display:flex;align-items:center;gap:12px;width:100%;max-width:520px;margin-bottom:16px}
.logo{font-size:22px;font-weight:800;color:#f0f0f0;letter-spacing:-0.5px;display:flex;align-items:center;gap:8px}
.badge{font-size:10px;padding:3px 10px;border-radius:9999px;background:rgba(5,46,22,0.6);
       color:#4ade80;border:1px solid rgba(22,101,52,0.5);letter-spacing:1.5px;font-weight:600}
.notif-bar{width:100%;max-width:520px;background:rgba(26,26,46,0.5);border:1px solid rgba(22,33,62,0.5);
           border-radius:10px;padding:12px 16px;margin-bottom:14px;display:flex;
           align-items:center;gap:10px;font-size:12px;cursor:pointer;transition:all .25s;backdrop-filter:blur(8px)}
.notif-bar:hover{border-color:rgba(6,182,212,0.5);background:rgba(26,26,46,0.7)}
.notif-bar .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot-off{background:#6b7280}.dot-on{background:#4ade80;box-shadow:0 0 8px #4ade80}
.tabs{display:flex;width:100%;max-width:520px;gap:0;margin-bottom:14px}
.tab{flex:1;padding:12px;text-align:center;font-size:11px;font-weight:600;
     letter-spacing:1px;cursor:pointer;background:rgba(17,24,39,0.5);border:1px solid rgba(31,41,55,0.6);
     color:#6b7280;transition:all .25s;text-transform:uppercase;position:relative;
     display:flex;align-items:center;justify-content:center;gap:6px}
.tab:first-child{border-radius:10px 0 0 10px}.tab:last-child{border-radius:0 10px 10px 0}
.tab.active{background:rgba(31,41,55,0.8);color:#06B6D4;border-color:rgba(6,182,212,0.5)}
.tab:hover:not(.active){background:rgba(31,41,55,0.4)}
.tab .pulse{position:absolute;top:6px;right:8px;width:8px;height:8px;
            border-radius:50%;background:#ef4444;display:none}
.tab .pulse.show{display:block;animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.4)}}
.panel{width:100%;max-width:520px;display:none}.panel.active{display:block}
label{font-size:10px;color:#6b7280;letter-spacing:1px;text-transform:uppercase;
      display:block;margin-bottom:4px}
input,textarea,select{width:100%;background:rgba(17,24,39,0.6);border:1px solid rgba(31,41,55,0.7);
  border-radius:10px;color:#e5e7eb;font-family:'Inter',-apple-system,sans-serif;font-size:14px;
  padding:12px 14px;outline:none;transition:all 0.25s;-webkit-appearance:none}
input:focus,textarea:focus,select:focus{border-color:#06B6D4;box-shadow:0 0 0 3px rgba(6,182,212,0.1)}
textarea{resize:vertical;min-height:110px;line-height:1.5}
select option{background:#111827}
.field{margin-bottom:16px}
.btn{background:linear-gradient(135deg,#06B6D4,#0891B2);color:#fff;border:none;border-radius:10px;padding:14px;
     font-family:'Inter',-apple-system,sans-serif;font-size:14px;font-weight:700;
     letter-spacing:0.5px;cursor:pointer;width:100%;transition:all 0.25s;
     box-shadow:0 4px 14px rgba(6,182,212,0.25);display:flex;align-items:center;justify-content:center;gap:8px}
.btn:hover{background:linear-gradient(135deg,#22D3EE,#06B6D4);transform:translateY(-1px);box-shadow:0 6px 20px rgba(6,182,212,0.35)}
.btn:disabled{background:#374151;color:#6b7280;cursor:not-allowed;box-shadow:none;transform:none}
.warn{background:rgba(28,10,10,0.5);border:1px solid rgba(127,29,29,0.4);border-radius:10px;
      padding:12px 14px;font-size:11px;color:#f87171;line-height:1.6;margin-bottom:14px;
      display:flex;align-items:flex-start;gap:8px}
.warn svg{flex-shrink:0;margin-top:1px}
.note{font-size:10px;color:#4b5563;text-align:center;line-height:1.6;margin-top:14px}
.photo-area{border:2px dashed rgba(31,41,55,0.7);border-radius:12px;padding:24px;text-align:center;
            cursor:pointer;transition:all .25s;margin-bottom:16px;position:relative;background:rgba(17,24,39,0.2);overflow:hidden}
.photo-area:hover{border-color:rgba(6,182,212,0.5);background:rgba(17,24,39,0.4)}
.photo-area img{max-width:100%;max-height:200px;border-radius:8px;margin-top:10px;object-fit:contain;display:block;margin-left:auto;margin-right:auto}
.photo-area .ph-label{color:#6b7280;font-size:12px;margin-top:4px}
.photo-area .ph-icon{margin-bottom:4px;line-height:1}
.photo-remove{position:absolute;top:8px;right:10px;background:rgba(127,29,29,0.8);color:#fff;
              border:none;border-radius:50%;width:28px;height:28px;cursor:pointer;
              display:none;align-items:center;justify-content:center}
/* Feed */
.feed-empty{text-align:center;padding:40px 16px;color:#4b5563;font-size:12px}
.report-card{background:rgba(17,24,39,0.5);border:1px solid rgba(31,41,55,0.5);border-radius:12px;
             padding:16px;margin-bottom:12px;transition:all .25s;backdrop-filter:blur(8px)}
.report-card:hover{border-color:rgba(6,182,212,0.15)}
.report-card.needs-val{border-color:rgba(245,158,11,0.5);animation:glow 2s infinite}
@keyframes glow{0%,100%{box-shadow:none}50%{box-shadow:0 0 8px rgba(6,182,212,.2)}}
.rc-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.rc-id{font-size:10px;color:#6b7280}.rc-domain{font-size:11px;font-weight:700;
  padding:2px 8px;border-radius:9999px;letter-spacing:.5px}
.d-MEDICAL{background:#1a0a0a;color:#f87171;border:1px solid #7f1d1d}
.d-LOGISTICS{background:#0a1a1a;color:#5eead4;border:1px solid #115e59}
.d-POWER{background:#1a1a0a;color:#fbbf24;border:1px solid #78350f}
.d-COMMS{background:#0a0a1a;color:#818cf8;border:1px solid #3730a3}
.d-EVACUATION{background:#0d1a0a;color:#86efac;border:1px solid #166534}
.d-SYSTEM{background:#111;color:#9ca3af;border:1px solid #374151}
.rc-msg{font-size:12px;line-height:1.6;color:#d1d5db;margin-bottom:8px}
.rc-photo{width:100%;height:180px;object-fit:cover;border-radius:6px;margin-bottom:8px;background:#111827}
.rc-meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px;font-size:10px}
.rc-meta span{padding:2px 6px;border-radius:4px}
.conf-high{background:#052e16;color:#4ade80}.conf-med{background:#1c1a05;color:#fbbf24}
.conf-low{background:#1c0a0a;color:#f87171}
.corr-yes{background:#052e16;color:#4ade80}.corr-no{background:#1c0a0a;color:#f87171}
.val-badge{background:#1f2937;color:#e5e7eb}
.needs-tag{background:#78350f;color:#fbbf24;font-weight:700;animation:pulse 1.5s infinite}
.sev-CRITICAL{color:#ef4444}.sev-HIGH{color:#f59e0b}.sev-MEDIUM{color:#60a5fa}.sev-LOW{color:#9ca3af}
.validate-btn{width:100%;padding:12px;border-radius:8px;font-family:'Inter',-apple-system,sans-serif;
              font-size:12px;font-weight:600;cursor:pointer;letter-spacing:.3px;
              transition:all .25s;border:1px solid rgba(22,101,52,0.5);background:rgba(5,46,22,0.4);color:#4ade80;
              display:flex;align-items:center;justify-content:center;gap:6px}
.validate-btn:hover{background:#166534;color:#fff}
.validate-btn:disabled{background:#1f2937;color:#4b5563;border-color:#374151;cursor:default}
.validate-btn.done{background:#166534;color:#fff;border-color:#4ade80}
.success-overlay{position:fixed;inset:0;background:rgba(0,0,0,.85);display:flex;
                 flex-direction:column;align-items:center;justify-content:center;
                 z-index:100;padding:24px;text-align:center;backdrop-filter:blur(16px)}
.success-overlay .big{margin-bottom:20px}
.success-overlay .title{font-size:18px;font-weight:800;color:#4ade80;margin-bottom:8px}
.success-overlay .detail{font-size:12px;color:#6b7280;line-height:1.8}
.success-overlay a{color:#06B6D4;font-size:12px;text-decoration:none;margin-top:24px;display:block}
.loc-wrap{position:relative}
.loc-wrap .loc-icon{position:absolute;left:10px;top:50%;transform:translateY(-50%);pointer-events:none;z-index:1;display:flex;align-items:center}
#loc{padding-left:30px}
.minimap{width:100%;height:140px;border-radius:8px;border:1px solid #1f2937;margin-top:6px;display:none;overflow:hidden}
.minimap-feed{width:100%;height:100px;border-radius:6px;margin-bottom:8px;background:#111827}
.pac-container{background:#111827!important;border:1px solid #1f2937!important;border-radius:0 0 10px 10px!important;
  font-family:'Inter',-apple-system,sans-serif!important;z-index:9999!important;margin-top:-1px!important}
.pac-item{background:#111827!important;color:#e5e7eb!important;border-top:1px solid #1f2937!important;
  padding:8px 12px!important;cursor:pointer!important;font-size:13px!important;line-height:1.4!important}
.pac-item:hover{background:#1f2937!important}
.pac-item-query{color:#06B6D4!important;font-weight:700!important}
.pac-icon{display:none!important}
.pac-matched{color:#06B6D4!important}
.loc-detected{font-size:10px;color:#4ade80;margin-top:4px;display:none}
</style>
<script>var __GMAPS_KEY__='%%GMAPS_KEY%%';</script>
<script src="https://maps.googleapis.com/maps/api/js?key=%%GMAPS_KEY%%&libraries=places&callback=initGMaps" async defer></script>
</head>
<body>
<div class="hdr">
  <div class="logo"><img src="/logo" alt="MACS" style="height:32px;border-radius:4px"></div>
  <div class="badge">FIELD REPORT</div>
</div>

<div class="notif-bar" id="notifBar" onclick="toggleNotif()">
  <div class="dot dot-off" id="notifDot"></div>
  <span id="notifText"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg> Enable live alerts to validate nearby reports</span>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('submit')" id="tabSubmit"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg> Submit</div>
  <div class="tab" onclick="showTab('feed')" id="tabFeed"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg> Live Feed <span class="pulse" id="feedPulse"></span></div>
</div>

<!-- ── SUBMIT PANEL ─────────────────────────────────────────── -->
<div class="panel active" id="panelSubmit">
  <form id="f">
    <div class="warn"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> Submit only verified field observations. False reports waste emergency resources.</div>

    <div class="photo-area" id="photoArea" onclick="document.getElementById('photoInput').click()">
      <div class="ph-icon"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#6b7280" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg></div>
      <div class="ph-label">Tap to add photo / video evidence</div>
      <img id="photoPreview" style="display:none;visibility:hidden" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" alt="">
      <button type="button" class="photo-remove" id="photoRemove" onclick="removePhoto(event)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
      <input type="file" id="photoInput" accept="image/*,video/*" capture="environment"
             style="display:none" onchange="handlePhoto(this)">
    </div>

    <div class="field">
      <label>What are you observing? *</label>
      <textarea id="msg" placeholder="Describe what you see &#8212; casualties, blocked routes, infrastructure damage, missing services..." required></textarea>
    </div>
    <div class="field">
      <label><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg> Location (auto-detected &#8226; type to search)</label>
      <div class="loc-wrap">
        <span class="loc-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#06B6D4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg></span>
        <input type="text" id="loc" placeholder="Detecting your location..." autocomplete="off">
      </div>
      <div class="loc-detected" id="locDetected"></div>
      <div class="minimap" id="minimap"></div>
    </div>
    <div class="field">
      <label>Urgency</label>
      <select id="urg">
        <option value="UNKNOWN">Unknown / not sure</option>
        <option value="LOW">Low &#8212; informational</option>
        <option value="MEDIUM">Medium &#8212; needs attention soon</option>
        <option value="HIGH">High &#8212; urgent response needed</option>
        <option value="CRITICAL">Critical &#8212; immediate life threat</option>
      </select>
    </div>
    <button class="btn" type="submit" id="btn">SUBMIT FIELD REPORT <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg></button>
    <div class="note">Reports are AI-verified and cross-referenced against sensor data.<br>
    Other citizens nearby can corroborate your report to boost confidence.</div>
  </form>
</div>

<!-- ── FEED PANEL ───────────────────────────────────────────── -->
<div class="panel" id="panelFeed">
  <div id="feedList"><div class="feed-empty">Loading reports...</div></div>
</div>

<script>
// ── Reporter ID (anonymous, persistent per device)
var RID = localStorage.getItem('macs_rid');
if(!RID){RID='R-'+Math.random().toString(36).substr(2,8);localStorage.setItem('macs_rid',RID)}
var validated = JSON.parse(localStorage.getItem('macs_validated')||'{}');
var seenIds = new Set();
var notifEnabled = false;
var photoB64 = null;
var photoMime = null;
var geoLat = null, geoLng = null;
var miniMap = null, miniMarker = null, placesAC = null;
var userLat = null, userLng = null; // continuously tracked position
var geoWatchId = null;
var NOTIFY_RADIUS_KM = 5; // proximity radius for notifications
var feedWs = null;
var feedWsRetry = 0;

// ── Inline SVG icons for dynamic content
var IC={
target:'<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="vertical-align:-1px"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
warn:'<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="vertical-align:-1px"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
link:'<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="vertical-align:-1px"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
check:'<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="vertical-align:-1px"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
eye:'<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="vertical-align:-1px"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
pin:'<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="vertical-align:-1px"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>',
shield:'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="vertical-align:-1px"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>',
arrow:'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="vertical-align:-2px"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>'
};
var SUBMIT_BTN='SUBMIT FIELD REPORT '+IC.arrow;

// ── Haversine distance (km) between two lat/lng pairs
function haversineKm(lat1,lon1,lat2,lon2){
  var R=6371;
  var dLat=(lat2-lat1)*Math.PI/180;
  var dLon=(lon2-lon1)*Math.PI/180;
  var a=Math.sin(dLat/2)*Math.sin(dLat/2)
    +Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)
    *Math.sin(dLon/2)*Math.sin(dLon/2);
  return R*2*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));
}

// ── Continuous geolocation tracking
function startGeoWatch(){
  if(!navigator.geolocation)return;
  if(geoWatchId!==null)return;
  // LOW accuracy first — fast & reliable on ALL devices (WiFi/cell)
  geoWatchId=navigator.geolocation.watchPosition(
    function(p){userLat=p.coords.latitude;userLng=p.coords.longitude;},
    function(){},
    {enableHighAccuracy:false,maximumAge:60000,timeout:20000}
  );
  // HIGH accuracy in parallel — upgrades position when GPS available
  navigator.geolocation.watchPosition(
    function(p){userLat=p.coords.latitude;userLng=p.coords.longitude;},
    function(){},
    {enableHighAccuracy:true,maximumAge:30000,timeout:30000}
  );
}
startGeoWatch();

// ── WebSocket for real-time event push
function connectFeedWs(){
  var proto=location.protocol==='https:'?'wss:':'ws:';
  var url=proto+'//'+location.host+'/ws';
  try{feedWs=new WebSocket(url)}catch(e){return}
  feedWs.onopen=function(){feedWsRetry=0;};
  feedWs.onmessage=function(msg){
    try{
      var data=JSON.parse(msg.data);
      // history batch on connect
      if(data.type==='history'&&Array.isArray(data.events)){
        data.events.forEach(function(evt){seenIds.add(evt.id)});
        return;
      }
      // single event broadcast
      var evt=data;
      if(!evt.id)return;
      if(seenIds.has(evt.id))return;
      seenIds.add(evt.id);
      // proximity notification for CROWD reports
      if(evt.source_layer==='CROWD'&&evt.event_type==='CITIZEN_INTEL'){
        handleProximityNotification(evt);
      }
      // also notify for nearby HIGH/CRITICAL sensor/system events
      if((evt.source_layer==='SENSOR'||evt.source_layer==='SYSTEM')
         &&(evt.severity==='CRITICAL'||evt.severity==='HIGH')){
        handleProximityNotification(evt);
      }
      // notify citizens when an agent responds near their location
      if(evt.source_layer==='AGENT'&&evt.event_type==='ACTION_TAKEN'){
        handleAgentResponseNotification(evt);
      }
      // pulse the feed tab or debounce feed reload
      if(!document.getElementById('panelFeed').classList.contains('active')){
        document.getElementById('feedPulse').classList.add('show');
      } else { debounceFeedReload(); }
    }catch(e){}
  };
  feedWs.onclose=function(){
    feedWs=null;
    var delay=Math.min(2000*Math.pow(2,feedWsRetry),30000);
    feedWsRetry++;
    setTimeout(connectFeedWs,delay);
  };
  feedWs.onerror=function(){if(feedWs)feedWs.close();};
}
connectFeedWs();

function handleProximityNotification(evt){
  if(!notifEnabled)return;
  var p=evt.payload||{};
  var geo=p.geo;
  // If no geo on event, still notify (could be non-geolocated report)
  if(geo&&geo.lat&&geo.lng&&userLat!==null){
    var dist=haversineKm(userLat,userLng,geo.lat,geo.lng);
    if(dist>NOTIFY_RADIUS_KM)return; // too far away
    sendNotification({
      id:evt.id,domain:evt.domain,severity:evt.severity,
      message:(p.message||'').substring(0,120),
      distance:dist,hasGeo:true,source_layer:evt.source_layer
    });
  } else if(!geo||!geo.lat){
    // No geo on report — send generic notification
    sendNotification({
      id:evt.id,domain:evt.domain,severity:evt.severity,
      message:(p.message||'').substring(0,120),
      distance:null,hasGeo:false,source_layer:evt.source_layer
    });
  }
}

// ── Google Maps initialization (called by script callback)
function initGMaps(){
  // Places Autocomplete
  var locInput = document.getElementById('loc');
  placesAC = new google.maps.places.Autocomplete(locInput, {
    types: ['geocode','establishment'],
    fields: ['formatted_address','geometry','name']
  });
  placesAC.addListener('place_changed', function(){
    var place = placesAC.getPlace();
    if(place.geometry){
      geoLat = place.geometry.location.lat();
      geoLng = place.geometry.location.lng();
      var name = place.name && place.name !== place.formatted_address
        ? place.name + ', ' + place.formatted_address : place.formatted_address;
      locInput.value = name;
      showLocDetected('\u2705 ' + name);
      showMiniMap(geoLat, geoLng, name);
    }
  });

  // Reverse-geocode GPS position
  function fillLocationFromGPS(lat,lng){
    geoLat=lat;geoLng=lng;
    var geocoder = new google.maps.Geocoder();
    geocoder.geocode({location:{lat:lat,lng:lng}}, function(results,status){
      if(status==='OK' && results[0]){
        var addr = results[0].formatted_address;
        locInput.value = addr;
        showLocDetected('\\uD83D\\uDCE1 GPS detected: ' + addr);
        showMiniMap(lat, lng, addr);
      } else {
        locInput.value = lat.toFixed(5)+', '+lng.toFixed(5);
        showLocDetected('\\uD83D\\uDCE1 GPS coordinates acquired');
        showMiniMap(lat, lng, 'Your location');
      }
    });
  }
  if(navigator.geolocation){
    // Check if watchPosition already acquired a fix (it started early)
    if(userLat!==null&&userLng!==null){
      fillLocationFromGPS(userLat,userLng);
    } else {
      // LOW accuracy first — works on ALL Android/iOS regardless of GPS setting
      navigator.geolocation.getCurrentPosition(function(p){
        fillLocationFromGPS(p.coords.latitude, p.coords.longitude);
      }, function(err){
        // getCurrentPosition failed — poll for watchPosition fix
        locInput.placeholder = 'Detecting location...';
        var _geoRetry=setInterval(function(){
          if(userLat!==null&&userLng!==null&&!geoLat){
            fillLocationFromGPS(userLat,userLng);
            clearInterval(_geoRetry);
          }
        },2000);
        setTimeout(function(){
          clearInterval(_geoRetry);
          if(!geoLat) locInput.placeholder='Type a location or address...';
        },30000);
      }, {enableHighAccuracy:false, timeout:10000, maximumAge:60000});
    }
  }
}

function showMiniMap(lat, lng, title){
  var el = document.getElementById('minimap');
  el.style.display = 'block';
  if(!miniMap){
    miniMap = new google.maps.Map(el, {
      zoom:15, center:{lat:lat,lng:lng},
      disableDefaultUI:true, zoomControl:true,
      styles:[{elementType:'geometry',stylers:[{color:'#0d1117'}]},
              {elementType:'labels.text.stroke',stylers:[{color:'#0d1117'}]},
              {elementType:'labels.text.fill',stylers:[{color:'#6b7280'}]},
              {featureType:'road',elementType:'geometry',stylers:[{color:'#1f2937'}]},
              {featureType:'water',elementType:'geometry',stylers:[{color:'#111827'}]},
              {featureType:'poi',elementType:'labels',stylers:[{visibility:'off'}]}]
    });
    miniMarker = new google.maps.Marker({position:{lat:lat,lng:lng}, map:miniMap,
      title:title, icon:{path:google.maps.SymbolPath.CIRCLE,scale:10,
        fillColor:'#06B6D4',fillOpacity:1,strokeColor:'#fff',strokeWeight:2}});
  } else {
    miniMap.setCenter({lat:lat,lng:lng});
    miniMarker.setPosition({lat:lat,lng:lng});
    miniMarker.setTitle(title);
  }
}

function showLocDetected(msg){
  var el=document.getElementById('locDetected');
  el.textContent=msg; el.style.display='block';
}

// ── Tabs
function showTab(t){
  document.getElementById('panelSubmit').classList.toggle('active',t==='submit');
  document.getElementById('panelFeed').classList.toggle('active',t==='feed');
  document.getElementById('tabSubmit').classList.toggle('active',t==='submit');
  document.getElementById('tabFeed').classList.toggle('active',t==='feed');
  if(t==='feed'){document.getElementById('feedPulse').classList.remove('show');loadFeed();}
}

// ── Photo handling
function handlePhoto(input){
  var file=input.files[0]; if(!file)return;
  photoMime=file.type;
  // Size guard: skip compression for very small files
  var MAX_FILE_MB=20;
  if(file.size>MAX_FILE_MB*1024*1024){
    alert('Photo too large (max '+MAX_FILE_MB+'MB). Please choose a smaller image.');
    input.value='';return;
  }
  if(file.type.startsWith('video/')){
    // For video, just store the file reference — we'll send a thumbnail
    var video=document.createElement('video');
    video.preload='metadata';
    video.onloadedmetadata=function(){
      video.currentTime=1;
    };
    video.onseeked=function(){
      var c=document.createElement('canvas');
      c.width=Math.min(video.videoWidth,640);
      c.height=c.width*(video.videoHeight/video.videoWidth);
      c.getContext('2d').drawImage(video,0,0,c.width,c.height);
      photoB64=c.toDataURL('image/jpeg',0.6);
      showPreview(photoB64);
    };
    video.src=URL.createObjectURL(file);
  } else {
    var reader=new FileReader();
    reader.onerror=function(){alert('Could not read photo. Try a different image.');};
    reader.onload=function(e){
      var img=new Image();
      img.onerror=function(){
        // Fallback: if Image() can't decode (HEIC etc), send raw base64
        photoB64=e.target.result;
        showPreview(photoB64);
      };
      img.onload=function(){
        var c=document.createElement('canvas');
        var maxW=800;
        var w=img.width,h=img.height;
        if(w>maxW){h=h*(maxW/w);w=maxW}
        c.width=w;c.height=h;
        c.getContext('2d').drawImage(img,0,0,w,h);
        photoB64=c.toDataURL('image/jpeg',0.5);
        // If still huge (>500KB b64), compress harder
        if(photoB64.length>500000){
          maxW=600;w=img.width;h=img.height;
          if(w>maxW){h=h*(maxW/w);w=maxW}
          c.width=w;c.height=h;
          c.getContext('2d').drawImage(img,0,0,w,h);
          photoB64=c.toDataURL('image/jpeg',0.35);
        }
        showPreview(photoB64);
      };
      img.src=e.target.result;
    };
    reader.readAsDataURL(file);
  }
}
function showPreview(src){
  var p=document.getElementById('photoPreview');
  p.onload=function(){p.style.display='block';p.style.visibility='visible';};
  p.src=src;
  document.getElementById('photoRemove').style.display='flex';
  document.querySelector('.ph-icon').style.display='none';
  document.querySelector('.ph-label').innerHTML='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2" stroke-linecap="round" style="vertical-align:-2px"><polyline points="20 6 9 17 4 12"/></svg> Photo attached';
}
function removePhoto(e){
  e.stopPropagation();photoB64=null;photoMime=null;
  var p=document.getElementById('photoPreview');
  p.style.display='none';p.style.visibility='hidden';
  p.src='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
  document.getElementById('photoRemove').style.display='none';
  document.getElementById('photoInput').value='';
  document.querySelector('.ph-icon').style.display='block';
  document.querySelector('.ph-label').textContent='Tap to add photo / video evidence';
}

// ── Notifications
function toggleNotif(){
  if(notifEnabled){notifEnabled=false;updateNotifUI();return}
  if(!('Notification' in window)){alert('Browser notifications not supported on this device');return}
  Notification.requestPermission().then(function(perm){
    if(perm==='granted'){
      notifEnabled=true;
      startGeoWatch();
      // Show confirmation notification
      try{new Notification('\\u2705 MACS Alerts Active',{
        body:"You will be notified when crisis reports appear within "+NOTIFY_RADIUS_KM+"km of your location.",
        icon:'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>\\u2B21</text></svg>',
        tag:'macs-confirm'
      })}catch(e){}
    } else {
      notifEnabled=false;
      alert('Please allow notifications to receive nearby crisis alerts.');
    }
    updateNotifUI();
  });
}
function updateNotifUI(){
  var dot=document.getElementById('notifDot');
  var txt=document.getElementById('notifText');
  var bar=document.getElementById('notifBar');
  if(notifEnabled){
    dot.className='dot dot-on';
    var locStatus=userLat!==null?' \\u2022 GPS active':'  \\u2022 GPS pending';
    txt.innerHTML='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2" stroke-linecap="round" style="vertical-align:-2px"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> Live alerts ON ('+NOTIFY_RADIUS_KM+'km radius)'+locStatus;
    bar.style.borderColor='#166534';
  } else {
    dot.className='dot dot-off';
    txt.innerHTML='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg> Enable live alerts to validate nearby reports';
    bar.style.borderColor='#16213e';
  }
}
// Refresh notification UI when GPS locks
var _notifUiTimer=setInterval(function(){if(notifEnabled)updateNotifUI()},5000);

function sendNotification(report){
  if(!notifEnabled)return;
  // Build title based on source layer
  var layerEmoji={'CROWD':'\\uD83D\\uDC64','SENSOR':'\\uD83D\\uDCE1','API':'\\uD83C\\uDF10','SYSTEM':'\\u26A1','AGENT':'\\uD83E\\uDD16'};
  var emoji=layerEmoji[report.source_layer]||'\\uD83D\\uDEA8';
  var sevEmoji={'CRITICAL':'\\uD83D\\uDD34','HIGH':'\\uD83D\\uDFE0','MEDIUM':'\\uD83D\\uDFE1','LOW':'\\uD83D\\uDFE2'};
  var sev=sevEmoji[report.severity]||'';
  var title=emoji+' '+sev+' '+report.domain+' — '+(report.source_layer==='CROWD'?'Citizen Report':'Alert');

  // Build body with distance if available
  var body=report.message;
  if(report.hasGeo&&report.distance!==null){
    var distStr=report.distance<1
      ? Math.round(report.distance*1000)+'m away'
      : report.distance.toFixed(1)+'km away';
    body='\\uD83D\\uDCCD '+distStr+'\\n'+body;
  }
  if(report.source_layer==='CROWD'){
    body+='\\n\\u2714\\uFE0F Tap to validate this report';
  }

  try{
    var n=new Notification(title,{
      body:body,
      icon:'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>\\u2B21</text></svg>',
      vibrate:[200,100,200,100,300],
      tag:'macs-'+report.id,
      requireInteraction:true,
      silent:false
    });
    n.onclick=function(){window.focus();showTab('feed');loadFeed();n.close()};
    // Auto-dismiss after 15s
    setTimeout(function(){n.close()},15000);
  }catch(e){}
}

// ── Agent Response Notifications (help is on the way)
var RESPONSE_LABELS={
  'MEDIC':'Medical team','LOGISTICS':'Supply convoy','POWER':'Power crew',
  'COMMS':'Comms relay','EVAC':'Evacuation unit'
};
var RESPONSE_ACTIONS={
  'MEDICAL':'Medical response dispatched to your area',
  'LOGISTICS':'Supply delivery being routed to your area',
  'POWER':'Power restoration crew en route',
  'COMMS':'Communications being restored in your area',
  'EVACUATION':'Evacuation assistance headed to your area'
};

function handleAgentResponseNotification(evt){
  if(!notifEnabled)return;
  var p=evt.payload||{};
  var geo=p.geo;
  if(!geo||!geo.lat||!geo.lng)return; // only notify if agent action has a location
  if(userLat===null)return;
  var dist=haversineKm(userLat,userLng,geo.lat,geo.lng);
  if(dist>NOTIFY_RADIUS_KM)return; // too far
  sendResponseNotification({
    id:evt.id,
    agent:evt.source,
    domain:evt.domain,
    severity:evt.severity,
    message:(p.message||'').substring(0,150),
    distance:dist
  });
}

function sendResponseNotification(info){
  if(!notifEnabled)return;
  var label=RESPONSE_LABELS[info.agent]||info.agent;
  var action=RESPONSE_ACTIONS[info.domain]||'Response in progress near you';
  var distStr=info.distance<1
    ? Math.round(info.distance*1000)+'m away'
    : info.distance.toFixed(1)+'km away';

  var title='\\u2705 '+label+' responding \\u2014 '+info.domain;
  var body='\\uD83D\\uDCCD '+distStr+'\\n'
    +action+'\\n\\n'
    +info.message.substring(0,100)
    +'\\n\\n\\u231B Status: Action confirmed \\u2014 help on the way';

  try{
    var n=new Notification(title,{
      body:body,
      icon:'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>\\u2705</text></svg>',
      vibrate:[100,50,100,50,200,100,300],
      tag:'macs-response-'+info.id,
      requireInteraction:true,
      silent:false
    });
    n.onclick=function(){window.focus();showTab('feed');loadFeed();n.close()};
    setTimeout(function(){n.close()},20000);
  }catch(e){}
}

// ── Form submission
document.getElementById('f').addEventListener('submit',async function(e){
  e.preventDefault();
  var btn=document.getElementById('btn');
  btn.textContent='VALIDATING...';btn.disabled=true;
  var payload={
    message:document.getElementById('msg').value,
    location:document.getElementById('loc').value||undefined,
    urgency:document.getElementById('urg').value,
    reporter_id:RID
  };
  if(geoLat!==null){payload.lat=geoLat;payload.lng=geoLng}
  if(photoB64){payload.photo=photoB64}
  try{
    var r=await fetch('/report',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)});
    var d=await r.json();
    if(d.accepted){
      var overlay=document.createElement('div');
      overlay.className='success-overlay';
      overlay.innerHTML='<div class="big"><svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></div>'
        +'<div class="title">REPORT ACCEPTED</div>'
        +'<div class="detail">'
        +'Domain: <span style="color:#e5e7eb">'+d.domain+'</span><br>'
        +'Severity: <span class="sev-'+d.severity+'">'+d.severity+'</span><br>'
        +'Confidence: <span style="color:#60a5fa">'+Math.round(d.confidence*100)+'%</span><br>'
        +(d.corroboration_score>0?'Corroboration: <span style="color:#4ade80">'+Math.round(d.corroboration_score*100)+'%</span><br>':'')
        +(d.event_id?'Event ID: <span style="color:#9ca3af">'+d.event_id+'</span>':'')
        +'</div>'
        +'<a href="javascript:void(0)" onclick="this.parentElement.remove()">&larr; Submit another report</a>'
        +'<a href="javascript:void(0)" onclick="this.parentElement.remove();showTab(\\'feed\\')" style="margin-top:8px">'
        +'View Live Feed &rarr;</a>';
      document.body.appendChild(overlay);
      document.getElementById('f').reset();photoB64=null;removePhoto({stopPropagation:function(){}});
      btn.innerHTML=SUBMIT_BTN;btn.disabled=false;
    } else {
      btn.innerHTML=SUBMIT_BTN;btn.disabled=false;
      alert('Not accepted: '+(d.reason||'Please add more detail and try again.'));
    }
  }catch(err){
    btn.innerHTML=SUBMIT_BTN;btn.disabled=false;
    alert('Connection error. Please try again.');
  }
});

// ── Live Feed
var feedTimer=null;
var _feedDebounce=null;
var _lastFeedIds='';
function debounceFeedReload(){
  if(_feedDebounce)clearTimeout(_feedDebounce);
  _feedDebounce=setTimeout(function(){_feedDebounce=null;loadFeed();},2000);
}
async function loadFeed(){
  try{
    var r=await fetch('/reports');
    var reports=await r.json();
    var container=document.getElementById('feedList');
    // Skip DOM update if the feed hasn't changed (prevents shaking)
    var idStr=reports.map(function(r){return r.id+':'+(r.validation_count||0)}).join(',');
    if(idStr===_lastFeedIds)return;
    _lastFeedIds=idStr;
    if(!reports.length){container.innerHTML='<div class="feed-empty"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#4b5563" stroke-width="1.5" stroke-linecap="round" style="display:block;margin:0 auto 8px"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg>No citizen reports yet. Be the first!</div>';return}
    var html='';
    reports.forEach(function(rpt){
      var p=rpt.payload||{};
      var conf=Math.round((p.confidence||0)*100);
      var confClass=conf>=80?'conf-high':conf>=60?'conf-med':'conf-low';
      var corrScore=p.corroboration_score||0;
      var corrClass=corrScore>0.3?'corr-yes':'corr-no';
      var needsVal=conf<80&&corrScore<0.3;
      var valCount=rpt.validation_count||0;
      var isValidated=validated[rpt.id]||false;
      seenIds.add(rpt.id);
      html+='<div class="report-card'+(needsVal?' needs-val':'')+'">'
        +'<div class="rc-head">'
        +'<span class="rc-id">'+rpt.id+' \\u2022 '+new Date(rpt.timestamp*1000).toLocaleTimeString()+'</span>'
        +'<span class="rc-domain d-'+rpt.domain+'">'+rpt.domain+'</span>'
        +'</div>';
      if(rpt.has_photo){html+='<img class="rc-photo" src="/photo/'+rpt.id+'" loading="lazy">';}
      html+='<div class="rc-msg">'+escHtml(p.message||p.original||'')+'</div>'
        +'<div class="rc-meta">'
        +'<span class="'+confClass+'">'+IC.target+' '+conf+'% confidence</span>'
        +'<span class="sev-'+rpt.severity+'">'+IC.warn+' '+rpt.severity+'</span>'
        +(corrScore>0?'<span class="'+corrClass+'">'+IC.link+' Corroborated '+Math.round(corrScore*100)+'%</span>':'')
        +'<span class="val-badge">'+IC.check+' '+valCount+' validation'+(valCount!==1?'s':'')+'</span>'
        +(needsVal?'<span class="needs-tag">'+IC.eye+' NEEDS VALIDATION</span>':'')
        +'</div>';
      if(p.location&&p.location!=='unknown'){
        html+='<div style="font-size:10px;color:#6b7280;margin-bottom:8px">'+IC.pin+' '+escHtml(p.location)+'</div>';
        // Static Google Map for geolocated reports
        if(p.geo&&p.geo.lat&&__GMAPS_KEY__){
          html+='<img class="minimap-feed" loading="lazy" src="https://maps.googleapis.com/maps/api/staticmap?center='
            +p.geo.lat+','+p.geo.lng+'&zoom=14&size=520x100&scale=2&maptype=roadmap'
            +'&style=element:geometry%7Ccolor:0x0d1117&style=element:labels.text.fill%7Ccolor:0x6b7280'
            +'&style=element:labels.text.stroke%7Ccolor:0x0d1117&style=feature:road%7Celement:geometry%7Ccolor:0x1f2937'
            +'&markers=color:0x06B6D4%7C'+p.geo.lat+','+p.geo.lng
            +'&key='+__GMAPS_KEY__+'">';
        }
      }
      if(!isValidated){
        html+='<button class="validate-btn" onclick="validateReport(\\''+rpt.id+'\\',this)">'
          +IC.shield+' I CAN CONFIRM THIS REPORT</button>';
      } else {
        html+='<button class="validate-btn done" disabled>'+IC.shield+' YOU VALIDATED THIS</button>';
      }
      html+='</div>';
    });
    container.innerHTML=html;
  }catch(e){console.error('Feed error',e)}
}

async function validateReport(id,btn){
  btn.disabled=true;btn.textContent='Validating...';
  try{
    var r=await fetch('/validate',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({report_id:id,reporter_id:RID})});
    var d=await r.json();
    if(d.ok){
      validated[id]=true;localStorage.setItem('macs_validated',JSON.stringify(validated));
      btn.className='validate-btn done';btn.innerHTML=IC.shield+' YOU VALIDATED THIS';
      loadFeed();
    } else {btn.innerHTML=IC.shield+' I CAN CONFIRM THIS REPORT';btn.disabled=false;
            if(d.reason)alert(d.reason)}
  }catch(e){btn.innerHTML=IC.shield+' I CAN CONFIRM THIS REPORT';btn.disabled=false}
}

function escHtml(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML}

// Auto-refresh feed when visible (debounced, WS handles real-time)
setInterval(function(){
  if(document.getElementById('panelFeed').classList.contains('active'))debounceFeedReload();
},8000);
// Initial feed load
setTimeout(function(){loadFeed()},1000);
</script>
</body>
</html>"""


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def generate_qr_png(url: str):
    """Returns PNG bytes or None if qrcode/Pillow not installed."""
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=8, border=4,
                           error_correction=0)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#e5e7eb", back_color="#0d1117")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()
    except Exception:
        return None


# ── HTTP handler ──────────────────────────────────────────────────────────────

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4, "UNKNOWN": 5}


class IntakeHandler(BaseHTTPRequestHandler):
    verifier: Optional[Verifier] = None

    def log_message(self, fmt, *args):
        pass  # suppress default stdout log

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/report"):
            html = FORM_HTML.replace("%%GMAPS_KEY%%", GOOGLE_MAPS_KEY)
            self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))

        elif path == "/qr":
            ip = get_local_ip()
            url = f"http://{ip}:{INTAKE_PORT}/"
            png = generate_qr_png(url)
            if png:
                self._send(200, "image/png", png)
            else:
                # Fallback: plain text with URL
                body = f"Install qrcode + Pillow for PNG.\nURL: {url}".encode()
                self._send(200, "text/plain", body)

        elif path == "/status":
            stats = bulletin.stats()
            self._send(200, "application/json", json.dumps(stats).encode())

        elif path == "/world-state":
            if WORLD_STATE_MGR is None:
                self._json({"error": "World state manager not initialized"})
            else:
                self._json(WORLD_STATE_MGR.snapshot())

        elif path == "/events":
            qs = parse_qs(urlparse(self.path).query)
            since = (qs.get("since") or [None])[0]
            limit = int((qs.get("limit") or ["100"])[0])
            etype = (qs.get("type") or [None])[0]
            domain = (qs.get("domain") or [None])[0]
            events = bulletin.read_since_limited(since, limit)
            if etype:
                events = [e for e in events if e.event_type == etype]
            if domain:
                events = [e for e in events if e.domain == domain.upper()]
            self._json([asdict(e) for e in events])

        elif path == "/agents":
            import time as _time
            now = _time.time()
            status = bulletin.agent_status()
            activity = bulletin.domain_last_active()
            result = {}
            for aid, agent in CONTROL_AGENTS.items():
                result[aid] = {
                    "status": status.get(aid, "unknown"),
                    "domain": getattr(agent, "domain", None),
                    "alive": agent.is_alive(),
                    "last_action": activity.get(aid),
                    "seconds_since_action": round(now - activity[aid], 1) if aid in activity else None,
                }
            self._json({"agents": result, "timestamp": now})

        elif path == "/layers":
            # Three-layer intelligence summary
            import time as _time
            from shared_state import SOURCE_LAYERS
            now = _time.time()
            recent = bulletin.snapshot(max_events=200)
            layer_stats = {layer: {"count": 0, "latest": None, "event_types": {}} for layer in SOURCE_LAYERS}
            for evt in recent:
                layer = evt.get("source_layer", "SYSTEM")
                if layer not in layer_stats:
                    layer_stats[layer] = {"count": 0, "latest": None, "event_types": {}}
                layer_stats[layer]["count"] += 1
                layer_stats[layer]["latest"] = evt.get("timestamp")
                etype = evt.get("event_type", "UNKNOWN")
                layer_stats[layer]["event_types"][etype] = layer_stats[layer]["event_types"].get(etype, 0) + 1
            # Corroboration stats from recent CROWD events
            crowd_events = [e for e in recent if e.get("source_layer") == "CROWD"]
            corroborated = sum(1 for e in crowd_events
                               if e.get("payload", {}).get("corroboration_score", 0) > 0.3)
            self._json({
                "layers": layer_stats,
                "pipeline": {
                    "total_events": len(recent),
                    "crowd_reports": len(crowd_events),
                    "corroborated": corroborated,
                    "corroboration_rate": round(corroborated / max(len(crowd_events), 1), 2),
                },
                "description": {
                    "SENSOR": "Ground truth — seismic, weather, environmental sensors",
                    "API": "Institutional truth — EONET, govt alerts, official feeds",
                    "CROWD": "Human truth — citizen field reports (corroborated by validator)",
                    "AGENT": "Derivative analysis — MAC agent reasoning and actions",
                    "SYSTEM": "System events — world state, control actions, lifecycle",
                },
                "timestamp": now,
            })

        elif path == "/reports":
            # Return CITIZEN_INTEL events enriched with photo + validation data
            events = [e for e in bulletin.read_since() if e.event_type == "CITIZEN_INTEL"]
            result = []
            for evt in reversed(events):  # newest first
                d = asdict(evt)
                d["has_photo"] = evt.id in PHOTO_STORE
                votes = VALIDATION_STORE.get(evt.id, {})
                d["validation_count"] = votes.get("count", 0)
                result.append(d)
            self._json(result)

        elif path.startswith("/photo/"):
            evt_id = path.split("/photo/", 1)[1]
            b64 = PHOTO_STORE.get(evt_id)
            if b64:
                # Detect MIME type from data URL prefix, default to jpeg
                content_type = "image/jpeg"
                if b64.startswith("data:"):
                    header = b64.split(",", 1)[0]  # e.g. data:image/png;base64
                    if "/" in header:
                        content_type = header.split(":")[1].split(";")[0]
                # Strip data URL prefix if present
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                import base64
                try:
                    img_bytes = base64.b64decode(b64)
                    self._send(200, content_type, img_bytes)
                except Exception:
                    self._send(404, "text/plain", b"Invalid photo data")
            else:
                self._send(404, "text/plain", b"No photo for this event")

        elif path == "/logo":
            logo_path = os.path.join(os.path.dirname(__file__), "..", "asset",
                                      "macs_logo_white.png")
            try:
                with open(logo_path, "rb") as f:
                    img_bytes = f.read()
                self._send(200, "image/png", img_bytes)
            except FileNotFoundError:
                self._send(404, "text/plain", b"Logo not found")

        else:
            self._send(404, "text/plain", b"Not found")

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/control":
            self._handle_control()
            return

        if path == "/validate":
            self._handle_validate()
            return

        if path != "/report":
            self._send(404, "text/plain", b"Not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json({"accepted": False, "reason": "Invalid JSON"})
            return

        message  = str(data.get("message", "")).strip()
        location = str(data.get("location", "")).strip()
        urgency  = str(data.get("urgency", "UNKNOWN")).upper()
        photo    = data.get("photo")  # base64 jpeg or None
        reporter = str(data.get("reporter_id", "")).strip()
        lat      = data.get("lat")
        lng      = data.get("lng")

        if not message:
            self._json({"accepted": False, "reason": "Empty message"})
            return

        if self.verifier is None:
          self._json({"accepted": False, "reason": "Verifier unavailable"})
          return

        context = bulletin.snapshot(max_events=20)
        result  = self.verifier.verify(message, location, context)

        if not result["credible"] or result["confidence"] < 0.50:
            reason = result.get("reject_reason") or "Could not verify — add more detail"
            logger.info(f"[INTAKE] Rejected: {reason}")
            self._json({"accepted": False, "reason": reason})
            return

        # Urgency hint can only raise severity, never lower it
        ai_sev  = result["severity"]
        if urgency in SEVERITY_ORDER and urgency != "UNKNOWN":
            if SEVERITY_ORDER[urgency] < SEVERITY_ORDER.get(ai_sev, 5):
                ai_sev = urgency

        event = bulletin.post(
            source="FIELD_REPORT",
            event_type="CITIZEN_INTEL",
            domain=result["domain"],
            severity=ai_sev,
            source_layer="CROWD",
            payload={
                "message":    result["message"],
                "original":   message,
                "location":   location or "unknown",
                "confidence": result["confidence"],
                "verified_by": "MACS-VALIDATOR",
                "corroborated_by": result.get("corroborated_by", []),
                "corroboration_score": result.get("corroboration_score", 0),
                "has_photo": bool(photo),
                "reporter_id": reporter or "anonymous",
                "geo": {"lat": lat, "lng": lng} if lat and lng else None,
            },
            tags=["citizen", "field-report", "verified"],
        )

        # Store photo separately (keep payload lightweight)
        if photo and event:
            PHOTO_STORE[event.id] = photo

        logger.info(
            f"[INTAKE] Accepted {result['domain']}/{ai_sev} "
            f"conf={result['confidence']}: {result['message'][:60]}"
        )
        self._json({
            "accepted":   True,
            "event_id":   event.id if event else None,
            "domain":     result["domain"],
            "severity":   ai_sev,
            "confidence": result["confidence"],
            "corroboration_score": result.get("corroboration_score", 0),
        })

    def _handle_control(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError:
            self._json({"ok": False, "reason": "Invalid JSON"})
            return

        token = str(data.get("token", ""))
        if CONTROL_TOKEN and token != CONTROL_TOKEN:
            self._json({"ok": False, "reason": "Unauthorized"})
            return

        action = str(data.get("action", "")).strip().lower()
        agent_id = str(data.get("agent", "")).strip().upper()

        if action == "list":
            self._json({
                "ok": True,
                "agents": sorted(list(CONTROL_AGENTS.keys())),
                "online": sorted([k for k, a in CONTROL_AGENTS.items() if a.is_alive()]),
            })
            return

        if action not in ("kill", "revive"):
            self._json({"ok": False, "reason": "Unsupported action. Use kill|revive|list"})
            return
        if agent_id not in CONTROL_AGENTS:
            self._json({"ok": False, "reason": f"Unknown agent: {agent_id}"})
            return

        agent = CONTROL_AGENTS[agent_id]
        if action == "kill":
            agent.stop()
            bulletin.post(
                source="SYSTEM",
                event_type="CONTROL_ACTION",
                domain="SYSTEM",
                severity="INFO",
                source_layer="SYSTEM",
                payload={"message": f"Remote control killed {agent_id}", "action": "kill", "agent": agent_id},
                tags=["control"],
            )
            self._json({"ok": True, "action": "kill", "agent": agent_id})
            return

        agent.start()
        bulletin.post(
            source="SYSTEM",
            event_type="CONTROL_ACTION",
            domain="SYSTEM",
            severity="INFO",
            source_layer="SYSTEM",
            payload={"message": f"Remote control revived {agent_id}", "action": "revive", "agent": agent_id},
            tags=["control"],
        )
        self._json({"ok": True, "action": "revive", "agent": agent_id})

    def _handle_validate(self):
        """Citizen cross-validation — another person confirms a report."""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body or b"{}")
        except json.JSONDecodeError:
            self._json({"ok": False, "reason": "Invalid JSON"})
            return

        report_id = str(data.get("report_id", "")).strip()
        reporter_id = str(data.get("reporter_id", "")).strip()

        if not report_id or not reporter_id:
            self._json({"ok": False, "reason": "Missing report_id or reporter_id"})
            return

        # Check the report exists
        found = [e for e in bulletin.read_since() if e.id == report_id and e.event_type == "CITIZEN_INTEL"]
        if not found:
            self._json({"ok": False, "reason": f"Report {report_id} not found"})
            return

        # Check for double-validation
        if report_id not in VALIDATION_STORE:
            VALIDATION_STORE[report_id] = {"reporters": set(), "count": 0}
        store = VALIDATION_STORE[report_id]

        if reporter_id in store["reporters"]:
            self._json({"ok": False, "reason": "You already validated this report"})
            return

        store["reporters"].add(reporter_id)
        store["count"] += 1

        # Post a CITIZEN_VALIDATION event to the bulletin
        bulletin.post(
            source="CROWD_VALIDATOR",
            event_type="CITIZEN_VALIDATION",
            domain=found[0].domain,
            severity="INFO",
            source_layer="CROWD",
            payload={
                "message": f"Citizen corroboration for {report_id} — "
                           f"now {store['count']} independent validation(s)",
                "validated_report": report_id,
                "validator_id": reporter_id,
                "total_validations": store["count"],
            },
            tags=["citizen", "validation", "crowd-corroboration"],
        )

        logger.info(f"[VALIDATE] {reporter_id} validated {report_id} (total: {store['count']})")
        self._json({
            "ok": True,
            "report_id": report_id,
            "validation_count": store["count"],
        })

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _send(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: dict):
        self._send(200, "application/json", json.dumps(data).encode())


# ── Entry point ───────────────────────────────────────────────────────────────

def start_intake_server(verifier: Verifier) -> threading.Thread:
    """Start the intake HTTP server in a background thread."""
    IntakeHandler.verifier = verifier
    server = ThreadingHTTPServer(("0.0.0.0", INTAKE_PORT), IntakeHandler)
    server.request_queue_size = 32
    server.daemon_threads = True

    def _run():
        server.serve_forever()

    t = threading.Thread(target=_run, daemon=True, name="intake-server")
    t.start()
    return t


def set_control_agents(agent_map: dict):
    """Register running agents for /control endpoint actions."""
    CONTROL_AGENTS.clear()
    CONTROL_AGENTS.update(agent_map or {})


def set_world_state_mgr(mgr):
    """Register world state manager for /world-state endpoint."""
    global WORLD_STATE_MGR
    WORLD_STATE_MGR = mgr


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-7s  %(message)s",
                        datefmt="%H:%M:%S")
    from shared_state import bulletin
    IntakeHandler.verifier = Verifier(mock_mode=True, bulletin=bulletin)
    server = ThreadingHTTPServer(("0.0.0.0", INTAKE_PORT), IntakeHandler)
    ip = get_local_ip()
    print(f"Intake server  http://{ip}:{INTAKE_PORT}/")
    print(f"QR code        http://{ip}:{INTAKE_PORT}/qr")
    server.serve_forever()
