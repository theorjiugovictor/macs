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
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e5e7eb;font-family:'Courier New',monospace;
     min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:16px 12px}
.hdr{display:flex;align-items:center;gap:10px;width:100%;max-width:520px;margin-bottom:12px}
.logo{font-size:20px;font-weight:800;color:#e5e7eb;letter-spacing:-0.5px}
.badge{font-size:10px;padding:2px 8px;border-radius:9999px;background:#052e16;
       color:#4ade80;border:1px solid #166534;letter-spacing:1px}
.notif-bar{width:100%;max-width:520px;background:#1a1a2e;border:1px solid #16213e;
           border-radius:8px;padding:10px 14px;margin-bottom:12px;display:flex;
           align-items:center;gap:10px;font-size:11px;cursor:pointer;transition:all .2s}
.notif-bar:hover{border-color:#f97316}
.notif-bar .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot-off{background:#6b7280}.dot-on{background:#4ade80;box-shadow:0 0 6px #4ade80}
.tabs{display:flex;width:100%;max-width:520px;gap:0;margin-bottom:14px}
.tab{flex:1;padding:10px;text-align:center;font-size:11px;font-weight:700;
     letter-spacing:1px;cursor:pointer;background:#111827;border:1px solid #1f2937;
     color:#6b7280;transition:all .2s;text-transform:uppercase;position:relative}
.tab:first-child{border-radius:6px 0 0 6px}.tab:last-child{border-radius:0 6px 6px 0}
.tab.active{background:#1f2937;color:#f97316;border-color:#f97316}
.tab .pulse{position:absolute;top:6px;right:8px;width:8px;height:8px;
            border-radius:50%;background:#ef4444;display:none}
.tab .pulse.show{display:block;animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.4)}}
.panel{width:100%;max-width:520px;display:none}.panel.active{display:block}
label{font-size:10px;color:#6b7280;letter-spacing:1px;text-transform:uppercase;
      display:block;margin-bottom:4px}
input,textarea,select{width:100%;background:#111827;border:1px solid #1f2937;
  border-radius:6px;color:#e5e7eb;font-family:'Courier New',monospace;font-size:14px;
  padding:10px 12px;outline:none;transition:border-color 0.2s;-webkit-appearance:none}
input:focus,textarea:focus,select:focus{border-color:#f97316}
textarea{resize:vertical;min-height:110px;line-height:1.5}
select option{background:#111827}
.field{margin-bottom:14px}
.btn{background:#f97316;color:#0d1117;border:none;border-radius:6px;padding:14px;
     font-family:'Courier New',monospace;font-size:13px;font-weight:800;
     letter-spacing:1px;cursor:pointer;width:100%;transition:background 0.2s}
.btn:hover{background:#ea580c}
.btn:disabled{background:#374151;color:#6b7280;cursor:not-allowed}
.warn{background:#1c0a0a;border:1px solid #7f1d1d;border-radius:6px;
      padding:10px 12px;font-size:11px;color:#f87171;line-height:1.5;margin-bottom:14px}
.note{font-size:10px;color:#4b5563;text-align:center;line-height:1.6;margin-top:12px}
.photo-area{border:2px dashed #1f2937;border-radius:8px;padding:16px;text-align:center;
            cursor:pointer;transition:border-color .2s;margin-bottom:14px;position:relative}
.photo-area:hover{border-color:#f97316}
.photo-area img{max-width:100%;max-height:200px;border-radius:6px;margin-top:8px}
.photo-area .ph-label{color:#6b7280;font-size:12px}
.photo-area .ph-icon{font-size:32px;margin-bottom:6px}
.photo-remove{position:absolute;top:6px;right:8px;background:#7f1d1d;color:#fff;
              border:none;border-radius:50%;width:24px;height:24px;cursor:pointer;
              font-size:14px;line-height:24px;display:none}
/* Feed */
.feed-empty{text-align:center;padding:40px 16px;color:#4b5563;font-size:12px}
.report-card{background:#111827;border:1px solid #1f2937;border-radius:8px;
             padding:14px;margin-bottom:10px;transition:border-color .2s}
.report-card.needs-val{border-color:#f59e0b;animation:glow 2s infinite}
@keyframes glow{0%,100%{box-shadow:none}50%{box-shadow:0 0 8px rgba(249,115,22,.2)}}
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
.rc-photo{width:100%;max-height:180px;object-fit:cover;border-radius:6px;margin-bottom:8px}
.rc-meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px;font-size:10px}
.rc-meta span{padding:2px 6px;border-radius:4px}
.conf-high{background:#052e16;color:#4ade80}.conf-med{background:#1c1a05;color:#fbbf24}
.conf-low{background:#1c0a0a;color:#f87171}
.corr-yes{background:#052e16;color:#4ade80}.corr-no{background:#1c0a0a;color:#f87171}
.val-badge{background:#1f2937;color:#e5e7eb}
.needs-tag{background:#78350f;color:#fbbf24;font-weight:700;animation:pulse 1.5s infinite}
.sev-CRITICAL{color:#ef4444}.sev-HIGH{color:#f59e0b}.sev-MEDIUM{color:#60a5fa}.sev-LOW{color:#9ca3af}
.validate-btn{width:100%;padding:10px;border-radius:6px;font-family:'Courier New',monospace;
              font-size:12px;font-weight:700;cursor:pointer;letter-spacing:.5px;
              transition:all .2s;border:1px solid #166534;background:#052e16;color:#4ade80}
.validate-btn:hover{background:#166534;color:#fff}
.validate-btn:disabled{background:#1f2937;color:#4b5563;border-color:#374151;cursor:default}
.validate-btn.done{background:#166534;color:#fff;border-color:#4ade80}
.success-overlay{position:fixed;inset:0;background:rgba(0,0,0,.85);display:flex;
                 flex-direction:column;align-items:center;justify-content:center;
                 z-index:100;padding:24px;text-align:center}
.success-overlay .big{font-size:56px;margin-bottom:16px}
.success-overlay .title{font-size:18px;font-weight:800;color:#4ade80;margin-bottom:8px}
.success-overlay .detail{font-size:12px;color:#6b7280;line-height:1.8}
.success-overlay a{color:#f97316;font-size:12px;text-decoration:none;margin-top:24px;display:block}
</style>
</head>
<body>
<div class="hdr">
  <div class="logo">&#x2B21; MACS</div>
  <div class="badge">FIELD REPORT</div>
</div>

<div class="notif-bar" id="notifBar" onclick="toggleNotif()">
  <div class="dot dot-off" id="notifDot"></div>
  <span id="notifText">&#x1F514; Enable live alerts to validate nearby reports</span>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('submit')" id="tabSubmit">&#x1F4DD; Submit</div>
  <div class="tab" onclick="showTab('feed')" id="tabFeed">&#x1F4E1; Live Feed <span class="pulse" id="feedPulse"></span></div>
</div>

<!-- ── SUBMIT PANEL ─────────────────────────────────────────── -->
<div class="panel active" id="panelSubmit">
  <form id="f">
    <div class="warn">&#9888; Submit only verified field observations. False reports waste emergency resources.</div>

    <div class="photo-area" id="photoArea" onclick="document.getElementById('photoInput').click()">
      <div class="ph-icon">&#x1F4F7;</div>
      <div class="ph-label">Tap to add photo / video evidence</div>
      <img id="photoPreview" style="display:none">
      <button type="button" class="photo-remove" id="photoRemove" onclick="removePhoto(event)">&#x2715;</button>
      <input type="file" id="photoInput" accept="image/*,video/*" capture="environment"
             style="display:none" onchange="handlePhoto(this)">
    </div>

    <div class="field">
      <label>What are you observing? *</label>
      <textarea id="msg" placeholder="Describe what you see &#8212; casualties, blocked routes, infrastructure damage, missing services..." required></textarea>
    </div>
    <div class="field">
      <label>Location (auto-detected or type manually)</label>
      <input type="text" id="loc" placeholder="Detecting GPS...">
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
    <button class="btn" type="submit" id="btn">SUBMIT FIELD REPORT &#8594;</button>
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

// ── Geolocation
if(navigator.geolocation){
  navigator.geolocation.getCurrentPosition(function(p){
    geoLat=p.coords.latitude; geoLng=p.coords.longitude;
    document.getElementById('loc').placeholder=
      'GPS: '+geoLat.toFixed(4)+', '+geoLng.toFixed(4)+' (or type manually)';
  }, function(){}, {enableHighAccuracy:true, timeout:5000});
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
    reader.onload=function(e){
      var img=new Image();
      img.onload=function(){
        var c=document.createElement('canvas');
        var maxW=800;
        var w=img.width,h=img.height;
        if(w>maxW){h=h*(maxW/w);w=maxW}
        c.width=w;c.height=h;
        c.getContext('2d').drawImage(img,0,0,w,h);
        photoB64=c.toDataURL('image/jpeg',0.55);
        showPreview(photoB64);
      };
      img.src=e.target.result;
    };
    reader.readAsDataURL(file);
  }
}
function showPreview(src){
  var p=document.getElementById('photoPreview');
  p.src=src;p.style.display='block';
  document.getElementById('photoRemove').style.display='block';
  document.querySelector('.ph-icon').style.display='none';
  document.querySelector('.ph-label').textContent='Photo attached \\u2714';
}
function removePhoto(e){
  e.stopPropagation();photoB64=null;photoMime=null;
  document.getElementById('photoPreview').style.display='none';
  document.getElementById('photoRemove').style.display='none';
  document.getElementById('photoInput').value='';
  document.querySelector('.ph-icon').style.display='block';
  document.querySelector('.ph-label').textContent='Tap to add photo / video evidence';
}

// ── Notifications
function toggleNotif(){
  if(notifEnabled){notifEnabled=false;updateNotifUI();return}
  if(!('Notification' in window)){alert('Notifications not supported');return}
  Notification.requestPermission().then(function(p){
    notifEnabled=(p==='granted');updateNotifUI();
  });
}
function updateNotifUI(){
  var dot=document.getElementById('notifDot');
  var txt=document.getElementById('notifText');
  if(notifEnabled){
    dot.className='dot dot-on';
    txt.innerHTML='\\u2705 Live alerts ON \\u2014 you\\'ll be notified of nearby reports';
  } else {
    dot.className='dot dot-off';
    txt.innerHTML='\\uD83D\\uDD14 Enable live alerts to validate nearby reports';
  }
}
function sendNotification(report){
  if(!notifEnabled)return;
  try{
    var n=new Notification('\\uD83D\\uDEA8 MACS: New '+report.domain+' report',{
      body:report.message.substring(0,100)+'...',
      icon:'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>\\u2B21</text></svg>',
      vibrate:[200,100,200],
      tag:'macs-'+report.id,
      requireInteraction:true
    });
    n.onclick=function(){window.focus();showTab('feed');n.close()};
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
      overlay.innerHTML='<div class="big">\\u2713</div>'
        +'<div class="title">REPORT ACCEPTED</div>'
        +'<div class="detail">'
        +'Domain: <span style="color:#e5e7eb">'+d.domain+'</span><br>'
        +'Severity: <span class="sev-'+d.severity+'">'+d.severity+'</span><br>'
        +'Confidence: <span style="color:#60a5fa">'+Math.round(d.confidence*100)+'%</span><br>'
        +(d.corroboration_score>0?'Corroboration: <span style="color:#4ade80">'+Math.round(d.corroboration_score*100)+'%</span><br>':'')
        +(d.event_id?'Event ID: <span style="color:#9ca3af">'+d.event_id+'</span>':'')
        +'</div>'
        +'<a href="javascript:void(0)" onclick="this.parentElement.remove()">\\u2190 Submit another report</a>'
        +'<a href="javascript:void(0)" onclick="this.parentElement.remove();showTab(\\'feed\\')" style="margin-top:8px">'
        +'View Live Feed \\u2192</a>';
      document.body.appendChild(overlay);
      document.getElementById('f').reset();photoB64=null;removePhoto({stopPropagation:function(){}});
    } else {
      btn.textContent='SUBMIT FIELD REPORT \\u2192';btn.disabled=false;
      alert('Not accepted: '+(d.reason||'Please add more detail and try again.'));
    }
  }catch(err){
    btn.textContent='SUBMIT FIELD REPORT \\u2192';btn.disabled=false;
    alert('Connection error. Please try again.');
  }
});

// ── Live Feed
var feedTimer=null;
async function loadFeed(){
  try{
    var r=await fetch('/reports');
    var reports=await r.json();
    var container=document.getElementById('feedList');
    if(!reports.length){container.innerHTML='<div class="feed-empty">No citizen reports yet. Be the first! \\uD83D\\uDCE1</div>';return}
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
      // Notification for new reports
      if(!seenIds.has(rpt.id)&&rpt.source!=='FIELD_REPORT_'+RID){
        seenIds.add(rpt.id);
        if(seenIds.size>1)sendNotification({id:rpt.id,domain:rpt.domain,message:p.message||''});
      } else { seenIds.add(rpt.id); }
      html+='<div class="report-card'+(needsVal?' needs-val':'')+'">'
        +'<div class="rc-head">'
        +'<span class="rc-id">'+rpt.id+' \\u2022 '+new Date(rpt.timestamp*1000).toLocaleTimeString()+'</span>'
        +'<span class="rc-domain d-'+rpt.domain+'">'+rpt.domain+'</span>'
        +'</div>';
      if(rpt.has_photo){html+='<img class="rc-photo" src="/photo/'+rpt.id+'" loading="lazy">';}
      html+='<div class="rc-msg">'+escHtml(p.message||p.original||'')+'</div>'
        +'<div class="rc-meta">'
        +'<span class="'+confClass+'">\\uD83C\\uDFAF '+conf+'% confidence</span>'
        +'<span class="sev-'+rpt.severity+'">\\u26A0 '+rpt.severity+'</span>'
        +(corrScore>0?'<span class="'+corrClass+'">\\uD83D\\uDD17 Corroborated '+Math.round(corrScore*100)+'%</span>':'')
        +'<span class="val-badge">\\u2705 '+valCount+' validation'+(valCount!==1?'s':'')+'</span>'
        +(needsVal?'<span class="needs-tag">\\uD83D\\uDC41 NEEDS VALIDATION</span>':'')
        +'</div>';
      if(p.location&&p.location!=='unknown'){html+='<div style="font-size:10px;color:#6b7280;margin-bottom:8px">\\uD83D\\uDCCD '+escHtml(p.location)+'</div>';}
      if(!isValidated){
        html+='<button class="validate-btn" onclick="validateReport(\\''+rpt.id+'\\',this)">'
          +'\\u2714 I CAN CONFIRM THIS REPORT</button>';
      } else {
        html+='<button class="validate-btn done" disabled>\\u2714 YOU VALIDATED THIS</button>';
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
      btn.className='validate-btn done';btn.textContent='\\u2714 YOU VALIDATED THIS';
      loadFeed();
    } else {btn.textContent='\\u2714 I CAN CONFIRM THIS REPORT';btn.disabled=false;
            if(d.reason)alert(d.reason)}
  }catch(e){btn.textContent='\\u2714 I CAN CONFIRM THIS REPORT';btn.disabled=false}
}

function escHtml(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML}

// Auto-refresh feed every 4s when visible
setInterval(function(){
  if(document.getElementById('panelFeed').classList.contains('active'))loadFeed();
  else checkNewReports();
},4000);

var lastKnownCount=0;
async function checkNewReports(){
  try{
    var r=await fetch('/reports');var d=await r.json();
    if(d.length>lastKnownCount&&lastKnownCount>0){
      document.getElementById('feedPulse').classList.add('show');
      // Notify for each new report
      for(var i=lastKnownCount;i<d.length;i++){
        if(!seenIds.has(d[i].id)){
          seenIds.add(d[i].id);
          sendNotification({id:d[i].id,domain:d[i].domain,message:(d[i].payload||{}).message||''});
        }
      }
    }
    lastKnownCount=d.length;
  }catch(e){}
}
checkNewReports();
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
            self._send(200, "text/html; charset=utf-8", FORM_HTML.encode("utf-8"))

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
                # Strip data URL prefix if present
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                import base64
                try:
                    img_bytes = base64.b64decode(b64)
                    self._send(200, "image/jpeg", img_bytes)
                except Exception:
                    self._send(404, "text/plain", b"Invalid photo data")
            else:
                self._send(404, "text/plain", b"No photo for this event")

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
