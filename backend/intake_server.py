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
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

from shared_state import bulletin
from verifier import Verifier

logger = logging.getLogger(__name__)

INTAKE_PORT = 8766

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
       min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:24px 16px}
  .header{display:flex;align-items:center;gap:10px;margin-bottom:20px;width:100%;max-width:480px}
  .logo{font-size:20px;font-weight:800;color:#e5e7eb;letter-spacing:-0.5px}
  .badge{font-size:10px;padding:2px 8px;border-radius:9999px;background:#052e16;
         color:#4ade80;border:1px solid #166534;letter-spacing:1px}
  form{width:100%;max-width:480px;display:flex;flex-direction:column;gap:14px}
  label{font-size:10px;color:#6b7280;letter-spacing:1px;text-transform:uppercase;
        display:block;margin-bottom:4px}
  input,textarea,select{width:100%;background:#111827;border:1px solid #1f2937;
    border-radius:6px;color:#e5e7eb;font-family:'Courier New',monospace;font-size:14px;
    padding:10px 12px;outline:none;transition:border-color 0.2s;-webkit-appearance:none}
  input:focus,textarea:focus,select:focus{border-color:#f97316}
  textarea{resize:vertical;min-height:130px;line-height:1.5}
  select option{background:#111827}
  .btn{background:#f97316;color:#0d1117;border:none;border-radius:6px;padding:14px;
       font-family:'Courier New',monospace;font-size:13px;font-weight:800;
       letter-spacing:1px;cursor:pointer;width:100%;transition:background 0.2s}
  .btn:hover{background:#ea580c}
  .btn:disabled{background:#374151;color:#6b7280;cursor:not-allowed}
  .warn{background:#1c0a0a;border:1px solid #7f1d1d;border-radius:6px;
        padding:10px 12px;font-size:11px;color:#f87171;line-height:1.5}
  .note{font-size:10px;color:#4b5563;text-align:center;line-height:1.6}
</style>
</head>
<body>
<div class="header">
  <div class="logo">&#x2B21; MACS</div>
  <div class="badge">FIELD REPORT</div>
</div>

<form id="f">
  <div class="warn">
    &#9888; Submit only verified field observations.
    False reports waste emergency resources.
  </div>

  <div>
    <label>What are you observing? *</label>
    <textarea id="msg" placeholder="Describe what you see &#8212; casualties, blocked routes,
infrastructure damage, missing services, civilian needs..." required></textarea>
  </div>

  <div>
    <label>Location (optional)</label>
    <input type="text" id="loc" placeholder="Grid ref, street name, landmark...">
  </div>

  <div>
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

  <div class="note">
    Reports are AI-verified before reaching response agents.<br>
    Your submission is anonymous.
  </div>
</form>

<script>
document.getElementById('f').addEventListener('submit',async function(e){
  e.preventDefault();
  var btn=document.getElementById('btn');
  btn.textContent='VERIFYING…';btn.disabled=true;
  try{
    var r=await fetch('/report',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        message:document.getElementById('msg').value,
        location:document.getElementById('loc').value,
        urgency:document.getElementById('urg').value
      })
    });
    var d=await r.json();
    if(d.accepted){
      document.body.innerHTML='<div style="text-align:center;padding:48px 24px;max-width:480px;margin:auto">'
        +'<div style="font-size:56px;margin-bottom:16px">✓</div>'
        +'<div style="font-size:18px;font-weight:800;color:#4ade80;margin-bottom:12px">REPORT ACCEPTED</div>'
        +'<div style="font-size:12px;color:#6b7280;line-height:1.8">'
        +'Domain: <span style="color:#e5e7eb">'+d.domain+'</span><br>'
        +'Severity: <span style="color:#f59e0b">'+d.severity+'</span><br>'
        +'Confidence: <span style="color:#60a5fa">'+(Math.round(d.confidence*100))+'%</span>'
        +'</div>'
        +'<div style="margin-top:28px">'
        +'<a href="/" style="color:#f97316;font-size:12px;text-decoration:none">← Submit another report</a>'
        +'</div></div>';
    }else{
      btn.textContent='SUBMIT FIELD REPORT →';btn.disabled=false;
      alert('Not accepted: '+(d.reason||'Please add more detail and try again.'));
    }
  }catch(err){
    btn.textContent='SUBMIT FIELD REPORT →';btn.disabled=false;
    alert('Connection error. Please try again.');
  }
});
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
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#e5e7eb", back_color="#0d1117")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


# ── HTTP handler ──────────────────────────────────────────────────────────────

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4, "UNKNOWN": 5}


class IntakeHandler(BaseHTTPRequestHandler):
    verifier: Verifier = None

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

        else:
            self._send(404, "text/plain", b"Not found")

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self):
        if urlparse(self.path).path != "/report":
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

        if not message:
            self._json({"accepted": False, "reason": "Empty message"})
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

        bulletin.post(
            source="FIELD_REPORT",
            event_type="CITIZEN_INTEL",
            domain=result["domain"],
            severity=ai_sev,
            payload={
                "message":    result["message"],
                "original":   message,
                "location":   location or "unknown",
                "confidence": result["confidence"],
                "verified_by": "MACS-VERIFIER",
            },
            tags=["citizen", "field-report", "verified"],
        )
        logger.info(
            f"[INTAKE] Accepted {result['domain']}/{ai_sev} "
            f"conf={result['confidence']}: {result['message'][:60]}"
        )
        self._json({
            "accepted":   True,
            "domain":     result["domain"],
            "severity":   ai_sev,
            "confidence": result["confidence"],
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
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: dict):
        self._send(200, "application/json", json.dumps(data).encode())


# ── Entry point ───────────────────────────────────────────────────────────────

def start_intake_server(verifier: Verifier) -> threading.Thread:
    """Start the intake HTTP server in a background thread."""
    IntakeHandler.verifier = verifier
    server = HTTPServer(("0.0.0.0", INTAKE_PORT), IntakeHandler)

    def _run():
        server.serve_forever()

    t = threading.Thread(target=_run, daemon=True, name="intake-server")
    t.start()
    return t


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-7s  %(message)s",
                        datefmt="%H:%M:%S")
    IntakeHandler.verifier = Verifier(mock_mode=True)
    server = HTTPServer(("0.0.0.0", INTAKE_PORT), IntakeHandler)
    ip = get_local_ip()
    print(f"Intake server  http://{ip}:{INTAKE_PORT}/")
    print(f"QR code        http://{ip}:{INTAKE_PORT}/qr")
    server.serve_forever()
