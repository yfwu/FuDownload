import json
import threading
import time
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


MONITOR_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FuDownload Monitor</title>
  <style>
    :root {
      --paper: #FFFFFF;
      --silver: #D8DEE9;
      --graphite: #2E3440;
      --teal: #5EBCBF;
      --indigo: #81A1C1;
      --emerald: #A3BE8C;
      --amber: #EBCB8B;
      --coral: #D08770;
      --plum: #B48EAD;
      --slate: #708090;

      --teal-50: rgba(94, 188, 191, 0.12);
      --indigo-50: rgba(129, 161, 193, 0.15);
      --emerald-50: rgba(163, 190, 140, 0.18);
      --amber-50: rgba(235, 203, 139, 0.18);
      --coral-50: rgba(208, 135, 112, 0.18);
      --plum-50: rgba(180, 142, 173, 0.18);
      --slate-50: rgba(112, 128, 144, 0.14);

      --teal-50p: rgba(94, 188, 191, 0.5);
      --indigo-50p: rgba(129, 161, 193, 0.5);
      --emerald-50p: rgba(163, 190, 140, 0.5);
      --amber-50p: rgba(235, 203, 139, 0.5);
      --coral-50p: rgba(208, 135, 112, 0.5);
      --slate-50p: rgba(112, 128, 144, 0.5);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Iosevka YFWU", "Menlo", "Consolas", monospace;
      color: var(--graphite);
      background: var(--paper);
      min-height: 100vh;
    }
    .page {
      max-width: 1100px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 24px;
      animation: fadeDown 0.7s ease both;
    }
    .eyebrow {
      text-transform: uppercase;
      letter-spacing: 0.16em;
      font-size: 12px;
      color: var(--slate);
    }
    h1 {
      margin: 8px 0 4px;
      font-size: 32px;
      font-family: "Spectral", "Palatino Linotype", "Book Antiqua", Palatino, serif;
    }
    .meta {
      color: var(--slate);
      font-size: 14px;
    }
    .indicator {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      height: 28px;
      padding: 0 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.02em;
      border: 1px solid var(--indicator-border);
      color: var(--indicator-color);
      background: var(--indicator-bg);
    }
    .status-pill {
      min-width: 140px;
      text-align: center;
    }
    .tag {
      height: 24px;
      padding: 0 10px;
      font-size: 11px;
    }
    .tone-primary {
      --indicator-color: var(--teal);
      --indicator-bg: var(--teal-50p);
      --indicator-border: rgba(94, 188, 191, 0.45);
    }
    .tone-info {
      --indicator-color: var(--indigo);
      --indicator-bg: var(--indigo-50p);
      --indicator-border: rgba(129, 161, 193, 0.45);
    }
    .tone-success {
      --indicator-color: var(--emerald);
      --indicator-bg: var(--emerald-50p);
      --indicator-border: rgba(163, 190, 140, 0.45);
    }
    .tone-warning {
      --indicator-color: var(--amber);
      --indicator-bg: var(--amber-50p);
      --indicator-border: rgba(235, 203, 139, 0.55);
    }
    .tone-danger {
      --indicator-color: var(--coral);
      --indicator-bg: var(--coral-50p);
      --indicator-border: rgba(208, 135, 112, 0.55);
    }
    .tone-neutral {
      --indicator-color: var(--slate);
      --indicator-bg: var(--slate-50p);
      --indicator-border: rgba(112, 128, 144, 0.45);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .card {
      background: var(--paper);
      border: 1px solid var(--silver);
      border-radius: 16px;
      padding: 16px;
      animation: fadeUp 0.7s ease both;
    }
    .card:nth-child(2) { animation-delay: 0.05s; }
    .card:nth-child(3) { animation-delay: 0.1s; }
    .card:nth-child(4) { animation-delay: 0.15s; }
    .card:nth-child(5) { animation-delay: 0.2s; }
    .label {
      color: var(--slate);
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 6px;
    }
    .value {
      font-size: 22px;
      font-weight: 700;
      margin-bottom: 6px;
    }
    .sub {
      font-size: 13px;
      color: var(--slate);
    }
    .panel {
      background: var(--slate-50);
      border: 1px solid var(--silver);
      border-radius: 18px;
      padding: 18px;
      margin-bottom: 20px;
      animation: fadeUp 0.7s ease both;
      animation-delay: 0.15s;
    }
    h2 {
      margin: 0 0 14px;
      font-size: 18px;
      font-family: "Spectral", "Palatino Linotype", "Book Antiqua", Palatino, serif;
    }
    .table {
      display: grid;
      gap: 8px;
    }
    .row {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr 1fr 1fr 0.8fr;
      gap: 12px;
      padding: 10px 12px;
      border-radius: 12px;
      background: var(--paper);
      border: 1px solid var(--silver);
      font-size: 14px;
    }
    .row.data {
      border-left: 4px solid var(--teal);
    }
    .table .row.data:nth-child(even) {
      border-left-color: var(--indigo);
    }
    .row.head {
      background: transparent;
      border: none;
      color: var(--slate);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .row.empty {
      grid-template-columns: 1fr;
      text-align: center;
      color: var(--slate);
      border-style: dashed;
      background: var(--slate-50);
    }
    .logs {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 10px;
    }
    .log-item {
      border-left: 3px solid var(--teal);
      padding: 8px 12px;
      background: var(--paper);
      border: 1px solid var(--silver);
      border-radius: 10px;
      font-size: 13px;
      color: var(--slate);
    }
    .log-item strong {
      color: var(--graphite);
      font-weight: 600;
    }
    .log-item.tone-info { border-left-color: var(--indigo); }
    .log-item.tone-success { border-left-color: var(--emerald); }
    .log-item.tone-warning { border-left-color: var(--amber); }
    .log-item.tone-danger { border-left-color: var(--coral); }
    .log-item.tone-neutral { border-left-color: var(--slate); }
    .muted {
      color: var(--slate);
    }
    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes fadeDown {
      from { opacity: 0; transform: translateY(-10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @media (max-width: 800px) {
      .row {
        grid-template-columns: 1fr;
      }
      .row.head {
        display: none;
      }
    }
  </style>
</head>
<body>
  <div class="page">
    <header>
      <div>
        <div class="eyebrow">Live download</div>
        <h1>FuDownload Monitor</h1>
        <div class="meta">Auto refresh every 2 seconds</div>
      </div>
      <div class="indicator status-pill tone-primary" id="server-status">Starting</div>
    </header>

    <section class="grid">
      <div class="card">
        <div class="label">Uptime</div>
        <div class="value" id="uptime">--</div>
        <div class="sub" id="start-time">--</div>
      </div>
      <div class="card">
        <div class="label">CSV files</div>
        <div class="value" id="csv-progress">0 / 0</div>
        <div class="sub" id="csv-name">--</div>
      </div>
      <div class="card">
        <div class="label">Batches</div>
        <div class="value" id="batch-progress">0 / 0</div>
        <div class="sub" id="batch-current">--</div>
      </div>
      <div class="card">
        <div class="label">Cases</div>
        <div class="value" id="case-progress">0 / 0</div>
        <div class="sub" id="case-meta">--</div>
      </div>
      <div class="card">
        <div class="label">Mode</div>
        <div class="value" id="mode">--</div>
        <div class="sub" id="phase">--</div>
      </div>
    </section>

    <section class="panel">
      <h2>Current Activity</h2>
      <div class="table">
        <div class="row head">
          <div>CSV</div>
          <div>Batch</div>
          <div>Cases</div>
          <div>Phase</div>
          <div>Status</div>
        </div>
        <div class="row data">
          <div id="current-csv">--</div>
          <div id="current-batch">--</div>
          <div id="current-cases">--</div>
          <div id="current-phase">--</div>
          <div><span class="indicator tag tone-primary" id="current-status">--</span></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <h2>Recent Logs</h2>
      <ul class="logs" id="log-list"></ul>
    </section>
  </div>

  <script>
    const el = (id) => document.getElementById(id);
    const indicatorTones = [
      "tone-primary",
      "tone-info",
      "tone-success",
      "tone-warning",
      "tone-danger",
      "tone-neutral"
    ];

    const applyTone = (node, tone) => {
      if (!node) return;
      indicatorTones.forEach((name) => node.classList.remove(name));
      node.classList.add(`tone-${tone}`);
    };

    const toneFromStatus = (value) => {
      const text = (value || "").toLowerCase();
      if (!text || text === "--") return "neutral";
      if (text.includes("error") || text.includes("fail")) return "danger";
      if (text.includes("warn")) return "warning";
      if (text.includes("success") || text.includes("complete")) return "success";
      if (text.includes("idle") || text.includes("stop")) return "neutral";
      return "primary";
    };

    const toneFromLevel = (value) => {
      const text = (value || "").toLowerCase();
      if (text.includes("error")) return "danger";
      if (text.includes("warn")) return "warning";
      if (text.includes("success")) return "success";
      if (text.includes("debug")) return "neutral";
      return "info";
    };

    const fmtPair = (a, b) => {
      if (a == null || b == null) return "--";
      return `${a} / ${b}`;
    };

    const updateStatus = async () => {
      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        const data = await response.json();
        const progress = data.progress || {};

        const serverStatus = data.status || "Running";
        el("server-status").textContent = serverStatus;
        applyTone(el("server-status"), toneFromStatus(serverStatus));
        el("uptime").textContent = data.uptime_human || "--";
        el("start-time").textContent = data.start_time || "--";

        el("csv-progress").textContent = fmtPair(progress.csv_index || 0, progress.csv_total || 0);
        el("csv-name").textContent = data.current_csv || "--";

        el("batch-progress").textContent = fmtPair(progress.batches_done || 0, progress.batches_total || 0);
        el("batch-current").textContent = fmtPair(progress.current_batch || 0, progress.current_batch_total || 0);

        el("case-progress").textContent = fmtPair(progress.cases_done || 0, progress.cases_total || 0);
        const skipped = progress.cases_skipped || 0;
        const errors = progress.errors || 0;
        el("case-meta").textContent = `Skipped: ${skipped} | Errors: ${errors}`;

        const mode = data.transfer_mode || "--";
        const protocol = data.transfer_protocol || "--";
        el("mode").textContent = `${mode} / ${protocol}`;
        el("phase").textContent = `Phase: ${data.phase || "--"}`;

        el("current-csv").textContent = data.current_csv || "--";
        el("current-batch").textContent = fmtPair(progress.current_batch || 0, progress.current_batch_total || 0);
        el("current-cases").textContent = fmtPair(progress.cases_done || 0, progress.cases_total || 0);
        el("current-phase").textContent = data.phase || "--";
        const currentStatus = data.status || "--";
        el("current-status").textContent = currentStatus;
        applyTone(el("current-status"), toneFromStatus(currentStatus));

        const logs = data.recent_logs || [];
        const logList = el("log-list");
        if (!logs.length) {
          logList.innerHTML = "<li class='log-item tone-neutral muted'>No logs yet.</li>";
        } else {
          logList.innerHTML = logs.slice(0, 8).map((item) => {
            const ts = item.timestamp || "--";
            const level = item.level || "INFO";
            const msg = item.message || "";
            const tone = toneFromLevel(level);
            return `<li class="log-item tone-${tone}"><strong>[${ts}] [${level}]</strong> ${msg}</li>`;
          }).join("");
        }
      } catch (err) {
        console.error("Failed to refresh status", err);
      }
    };

    updateStatus();
    setInterval(updateStatus, 2000);
  </script>
</body>
</html>
"""


def now_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_duration(seconds):
    seconds = int(max(seconds, 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class DownloadMonitor:
    def __init__(self, host="0.0.0.0", port=8081, enabled=True):
        self.host = host
        self.port = port
        self.enabled = enabled
        self.lock = threading.Lock()
        self.thread = None
        self.running = False
        self.recent_events = deque(maxlen=200)
        self.state = {
            "status": "Starting",
            "phase": "idle",
            "start_time": None,
            "transfer_mode": None,
            "transfer_protocol": None,
            "csv_total": 0,
            "csv_index": 0,
            "current_csv": None,
            "batches_total": 0,
            "batches_done": 0,
            "current_batch": 0,
            "current_batch_total": 0,
            "cases_total": 0,
            "cases_done": 0,
            "cases_skipped": 0,
            "errors": 0,
        }

    def update(self, **updates):
        with self.lock:
            self.state.update(updates)

    def log_event(self, message, level="INFO"):
        timestamp = now_timestamp()
        with self.lock:
            self.recent_events.append({
                "timestamp": timestamp,
                "level": level,
                "message": message,
            })

    def _build_status_payload(self):
        with self.lock:
            snapshot = dict(self.state)
            logs_snapshot = list(self.recent_events)

        start_time = snapshot.get("start_time")
        if start_time is None:
            start_time = datetime.now()
            snapshot["start_time"] = start_time

        uptime_seconds = (datetime.now() - start_time).total_seconds()

        return {
            "status": snapshot.get("status", "Running"),
            "phase": snapshot.get("phase", "idle"),
            "transfer_mode": snapshot.get("transfer_mode"),
            "transfer_protocol": snapshot.get("transfer_protocol"),
            "current_csv": snapshot.get("current_csv"),
            "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "uptime_seconds": int(uptime_seconds),
            "uptime_human": format_duration(uptime_seconds),
            "progress": {
                "csv_index": snapshot.get("csv_index", 0),
                "csv_total": snapshot.get("csv_total", 0),
                "batches_total": snapshot.get("batches_total", 0),
                "batches_done": snapshot.get("batches_done", 0),
                "current_batch": snapshot.get("current_batch", 0),
                "current_batch_total": snapshot.get("current_batch_total", 0),
                "cases_total": snapshot.get("cases_total", 0),
                "cases_done": snapshot.get("cases_done", 0),
                "cases_skipped": snapshot.get("cases_skipped", 0),
                "errors": snapshot.get("errors", 0),
            },
            "recent_logs": list(reversed(logs_snapshot)),
        }

    def start(self):
        if not self.enabled or self.running:
            return

        self.running = True
        with self.lock:
            if not self.state.get("start_time"):
                self.state["start_time"] = datetime.now()

        monitor_ref = self

        class MonitorHandler(BaseHTTPRequestHandler):
            def _send(self, status_code, body, content_type):
                self.send_response(status_code)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    body = MONITOR_TEMPLATE.encode("utf-8")
                    self._send(200, body, "text/html; charset=utf-8")
                    return

                if self.path.startswith("/api/status"):
                    payload = monitor_ref._build_status_payload()
                    body = json.dumps(payload).encode("utf-8")
                    self._send(200, body, "application/json; charset=utf-8")
                    return

                self._send(404, b"Not Found", "text/plain; charset=utf-8")

            def log_message(self, format, *args):
                return

        def run_server():
            try:
                httpd = ThreadingHTTPServer((self.host, self.port), MonitorHandler)
                httpd.serve_forever()
            except Exception as exc:
                self.log_event(f"Monitoring UI failed to start: {exc}", "ERROR")
                print(f"[monitor] Failed to start UI: {exc}")

        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()

        host_label = self.host
        if host_label in ("0.0.0.0", "127.0.0.1"):
            host_label = "localhost"
        print(f"[monitor] UI available at http://{host_label}:{self.port}")
