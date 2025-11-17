import socket
import os
import time
import sys
import threading
import json
import random
import platform
import subprocess
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

# ==========================================
#               הגדרות מערכת
# ==========================================
HOST = '127.0.0.1'
WELCOME_PORT = 54321
HTTP_PORT = 8080
BUFFER_SIZE = 1024
CHUNK_SIZE = 980
FILES_DIR = os.path.join(os.getcwd(), "files")
if not os.path.exists(FILES_DIR): os.makedirs(FILES_DIR)

if not os.listdir(FILES_DIR):
    with open(os.path.join(FILES_DIR, "3.txt"), "w") as f: f.write("A" * 500000)

ALPHA = 0.125
BETA = 0.25
INITIAL_RTO = 1.0
FAST_RETRANSMIT_THRESHOLD = 3

# ==========================================
#          ניהול זיכרון משותף
# ==========================================
SERVER_STATE = {
    "clients": {},
    "graph_data": [],
    "logs": [],
    "running": False,
    "paused": False,
    "should_stop": False,
    "speed_delay": 0.0,
    "last_save_path": os.getcwd()
}

log_lock = threading.Lock()


def add_log(client_id, message, type="info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {"time": timestamp, "client": client_id, "msg": message, "type": type}
    with log_lock:
        SERVER_STATE["logs"].append(log_entry)
        if len(SERVER_STATE["logs"]) > 1000: SERVER_STATE["logs"].pop(0)


# ==========================================
#          ממשק המשתמש (HTML Final)
# ==========================================
DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RUDP Presentation Mode</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Alef:wght@400;700&family=Fira+Code:wght@400;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

    <style>
        :root {
            --bg-gradient: linear-gradient(135deg, #1e1e1e, #2c2c2c);
            --card-glass: rgba(255, 255, 255, 0.05);
            --border-glass: rgba(255, 255, 255, 0.1);
            --btn-start: #28c76f;
            --btn-stop: #ea5455;
            --btn-resume: #2196f3;
            --btn-restart: #ffc107;
            --text-main: #fff;
            --text-muted: #b0b0b0;
            --accent: #7367f0;
            --success: #28c76f;
            --danger: #ea5455;
            --warning: #ff9f43;
        }

        * { box-sizing: border-box; outline: none; }

        body {
            margin: 0; font-family: 'Alef', sans-serif;
            background: var(--bg-gradient); color: var(--text-main);
            height: 100vh; display: flex; overflow: hidden;
        }

        .sidebar {
            width: 340px; min-width: 340px; 
            background: rgba(0, 0, 0, 0.3); backdrop-filter: blur(10px);
            border-left: 1px solid var(--border-glass);
            padding: 20px; display: flex; flex-direction: column; gap: 15px;
            box-shadow: -5px 0 30px rgba(0,0,0,0.5); z-index: 20; overflow-y: auto;
        }

        .brand {
            font-size: 1.8rem; font-weight: 700; color: var(--text-main);
            display: flex; align-items: center; gap: 10px; margin-bottom: 10px;
            letter-spacing: 1px; text-shadow: 0 2px 10px rgba(0,0,0,0.3);
        }

        .control-card {
            background: var(--card-glass); padding: 15px;
            border-radius: 15px; border: 1px solid var(--border-glass);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }

        .input-box { margin-bottom: 12px; }
        .input-box label { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 5px; display: block; }
        .input-box input {
            width: 100%; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); color: #fff;
            padding: 8px; border-radius: 6px; font-family: 'Fira Code'; transition: 0.3s;
        }

        /* Slider styling for Snail Mode */
        input[type=range] {
            width: 100%; height: 6px; background: #333; border-radius: 5px; outline: none; -webkit-appearance: none;
        }
        input[type=range]::-webkit-slider-thumb {
            -webkit-appearance: none; appearance: none; width: 18px; height: 18px; border-radius: 50%; 
            background: var(--accent); cursor: pointer; transition: .2s;
        }
        input[type=range]::-webkit-slider-thumb:hover { transform: scale(1.2); }

        .btn {
            width: 100%; padding: 12px; margin-top: 8px; border: none; border-radius: 8px;
            font-size: 1rem; font-weight: bold; font-family: 'Alef'; cursor: pointer; 
            transition: 0.3s ease; color: white; display: flex; align-items: center; justify-content: center; gap: 8px;
        }
        .btn:hover { filter: brightness(1.2); transform: translateY(-2px); }
        .btn-start { background: var(--btn-start); }
        .btn-stop { background: var(--btn-stop); }
        .btn-resume { background: var(--btn-resume); }
        .btn-restart { background: var(--btn-restart); color: #222; }

        .btn-tool { 
            background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); 
            color: var(--text-muted); font-size: 0.85rem; padding: 8px; border-radius: 6px;
            cursor: pointer; transition: 0.3s; display: flex; align-items: center; gap: 8px;
        }
        .btn-tool:hover { background: rgba(255,255,255,0.15); color: white; }

        .main { flex: 1; padding: 20px; display: flex; flex-direction: column; gap: 15px; overflow: hidden; height: 100%; }

        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; flex-shrink: 0; }
        .card {
            background: var(--card-glass); border: 1px solid var(--border-glass); 
            border-radius: 12px; padding: 15px; position: relative;
            display: flex; flex-direction: column; justify-content: center;
        }
        .stat-val { font-size: 1.8rem; font-weight: 700; font-family: 'Fira Code'; }
        .stat-lbl { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }

        .mid-section { display: flex; gap: 15px; flex: 1; min-height: 0; }
        .graph-box { 
            flex: 2; background: var(--card-glass); border: 1px solid var(--border-glass); 
            border-radius: 12px; padding: 10px; position: relative;
        }
        .packet-map {
            flex: 1; background: var(--card-glass); border: 1px solid var(--border-glass); 
            border-radius: 12px; padding: 15px; display: flex; flex-direction: column; min-width: 250px;
        }
        .grid-container {
            flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(10px, 1fr));
            gap: 3px; overflow-y: auto; align-content: start; margin-top: 10px; padding-right: 5px;
        }
        .pkt { aspect-ratio: 1; border-radius: 2px; background: rgba(255,255,255,0.1); }
        .pkt.sent { background: #ffc107; }
        .pkt.acked { background: #28c76f; box-shadow: 0 0 5px rgba(40, 199, 111, 0.5); }
        .pkt.lost { background: #ea5455; }

        .log-box {
            height: 200px; flex-shrink: 0; background: rgba(0,0,0,0.4); 
            border: 1px solid var(--border-glass); border-radius: 12px;
            display: flex; flex-direction: column; font-family: 'Fira Code', monospace; font-size: 0.8rem;
        }
        .log-head { padding: 8px 15px; background: rgba(0,0,0,0.3); border-bottom: 1px solid var(--border-glass); color: var(--text-muted); font-size: 0.75rem; }
        .log-body { flex: 1; padding: 10px; overflow-y: auto; }
        .log-row { display: flex; gap: 10px; margin-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.03); }
        .l-msg.err { color: var(--danger); } .l-msg.ok { color: var(--success); } .l-msg.warn { color: var(--warning); }

        /* Modal */
        .modal-wrap {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85);
            z-index: 999; display: none; align-items: center; justify-content: center; backdrop-filter: blur(5px);
        }
        .modal {
            background: #1e1e1e; width: 750px; max-width: 95%; max-height: 90vh; overflow-y: auto;
            border: 1px solid var(--accent); border-radius: 16px; padding: 30px;
        }
        .term-item { background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px; margin-bottom: 12px; }
        .term-k { color: var(--accent); font-weight: bold; font-size: 1.1rem; margin-bottom: 4px; }
        .term-d { font-size: 0.95rem; line-height: 1.5; color: #ddd; }

    </style>
</head>
<body>

<div class="sidebar">
    <div class="brand">
        <i class="fa-solid fa-network-wired"></i> RUDP MASTER
    </div>

    <div class="control-card">

        <div class="input-box">
            <label>קובץ:</label>
            <input type="text" id="filename" value="3.txt">
        </div>

        <div class="input-box">
            <label style="display:flex; justify-content:space-between;">
                <span>איבוד חבילות</span>
                <span id="lossDisplay" style="color:var(--danger); font-weight:bold;">0%</span>
            </label>
            <input type="range" id="loss" min="0" max="40" value="0" oninput="document.getElementById('lossDisplay').innerText = this.value + '%'">
        </div>

        <div class="input-box" style="background: rgba(255, 255, 0, 0.05); padding:10px; border-radius:8px; border:1px dashed var(--warning);">
            <label style="color:var(--warning); display:flex; align-items:center; gap:5px;">
                <i class="fa-solid fa-chalkboard-user"></i> מצב פרזנטציה (האטה)
            </label>
            <div style="display:flex; align-items:center; gap:10px; margin-top:5px;">
                <i class="fa-solid fa-bolt" style="color:#888; font-size:0.8rem;"></i>
                <input type="range" id="speed" min="0" max="800" value="0" oninput="updateSpeed(this.value)">
                <i class="fa-solid fa-snail" style="color:var(--success); font-size:1.2rem;"></i>
            </div>
        </div>

        <div id="startSection">
            <button class="btn btn-start" onclick="startClient()">
                <i class="fa-solid fa-play"></i> התחל הרצה
            </button>
        </div>

        <div id="runningSection" style="display:none;">
            <button class="btn btn-stop" onclick="pauseClient()" style="background:var(--warning); color:#000;">
                <i class="fa-solid fa-pause"></i> השהה (Pause)
            </button>
            <button class="btn btn-stop" onclick="stopClient()">
                <i class="fa-solid fa-skull"></i> עצירה מלאה (Kill)
            </button>
        </div>

        <div id="pausedSection" style="display:none; gap:10px;">
            <button class="btn btn-resume" onclick="resumeClient()">
                <i class="fa-solid fa-forward"></i> המשך
            </button>
            <button class="btn btn-restart" onclick="restartClient()">
                <i class="fa-solid fa-rotate-right"></i> התחל מחדש
            </button>
        </div>

        <div id="status" style="text-align:center; margin-top:10px; color:var(--text-muted); font-size:0.9rem;">ממתין...</div>
    </div>

    <div style="margin-top: auto; display: flex; flex-direction: column; gap: 8px;">
        <button class="btn-tool" onclick="downloadLog()"><i class="fa-solid fa-file-lines"></i> ייצא לוג</button>
        <button class="btn-tool" onclick="downloadGlossary()"><i class="fa-solid fa-book"></i> ייצא מילון</button>
        <button class="btn-tool" onclick="openFolder()"><i class="fa-regular fa-folder-open"></i> פתח תיקייה</button>
        <button class="btn-tool" onclick="toggleModal()"><i class="fa-solid fa-info-circle"></i> מילון מושגים</button>
    </div>
</div>

<div class="main">
    <div class="stats">
        <div class="card" style="border-bottom: 3px solid var(--accent)">
            <div class="stat-val" id="val-cwnd">0</div>
            <div class="stat-lbl">CWND (Network Load)</div>
        </div>
        <div class="card" style="border-bottom: 3px solid var(--warning)">
            <div class="stat-val" id="val-rwnd">0</div>
            <div class="stat-lbl">RWND (Buffer)</div>
        </div>
        <div class="card" style="border-bottom: 3px solid var(--success)">
            <div class="stat-val" id="val-rto">0s</div>
            <div class="stat-lbl">RTO (Timer)</div>
        </div>
        <div class="card">
            <div class="stat-val" id="val-progress">0%</div>
            <div class="stat-lbl">Total Progress</div>
        </div>
    </div>

    <div class="mid-section">
        <div class="graph-box">
            <canvas id="mainChart"></canvas>
        </div>
        <div class="packet-map">
            <div class="map-header">
                <span>Packet Map</span>
                <div style="font-size:0.7rem;">
                    <span style="color:#ffc107">●</span> In-Flight 
                    <span style="color:#28c76f">●</span> ACK 
                    <span style="color:#ea5455">●</span> Lost
                </div>
            </div>
            <div class="grid-container" id="packetGrid"></div>
        </div>
    </div>

    <div class="log-box">
        <div class="log-head">
            <span>SYSTEM TERMINAL</span>
            <span style="color:var(--success)">● ONLINE</span>
        </div>
        <div class="log-body" id="logContent"></div>
    </div>
</div>

<div class="modal-wrap" id="glossaryModal" onclick="if(event.target===this) toggleModal()">
    <div class="modal">
        <h2 style="color:var(--accent); margin-top:0; text-align:center;">📚 מילון מושגים: Transport Layer</h2>
        <div class="term-grid" id="glossaryContent"></div>
        <button class="btn btn-start" onclick="toggleModal()">סגור</button>
    </div>
</div>

<script>
    let chart;
    let allLogsText = "";

    const glossaryData = [
        {k: "UDP", d: "פרוטוקול 'Best Effort'. לא מבטיח אמינות, סדר או בקרת זרימה. הפרויקט שלנו בונה את האמינות מעליו."},
        {k: "RDT (Reliable Data Transfer)", d: "מנגנון להוספת אמינות (ACK, Timer, SeqNum) מעל ערוץ לא אמין."},
        {k: "Multiplexing", d: "שימוש בפורטים כדי לנתב מידע לתהליכים שונים במקביל."},
        {k: "CWND (Congestion Window)", d: "כמות הנתונים המקסימלית שהשרת שולח לרשת לפני המתנה לאישור. מונע עומס ברשת."},
        {k: "RWND (Receive Window)", d: "מנגנון Flow Control. הלקוח אומר לשרת כמה מקום פנוי יש לו כדי לא להיות מוצף."},
        {k: "RTO (Dynamic Timeout)", d: "הזמן שהשרת מחכה לאישור. מחושב דינאמית לפי ה-RTT (זמן תגובה) של הרשת."},
        {k: "Fast Retransmit", d: "זיהוי מהיר של איבוד חבילה ע\"י קבלת 3 אישורים כפולים (Duplicate ACKs)."},
        {k: "Selective Repeat", d: "שיטה יעילה שבה הלקוח שומר חבילות בבאפר, והשרת שולח מחדש רק את מה שחסר."},
        {k: "Slow Start", d: "האצה אקספוננציאלית של קצב השליחה בתחילת הקשר."},
        {k: "AIMD", d: "התנהגות יציבה: עלייה ליניארית בקצב, וחיתוך חד (בחצי) בעת זיהוי איבוד."}
    ];

    const gDiv = document.getElementById('glossaryContent');
    glossaryData.forEach(i => {
        gDiv.innerHTML += `<div class="term-item"><div class="term-k">${i.k}</div><div class="term-d">${i.d}</div></div>`;
    });

    function initChart() {
        const ctx = document.getElementById('mainChart').getContext('2d');
        let gradient = ctx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, 'rgba(115, 103, 240, 0.4)');
        gradient.addColorStop(1, 'rgba(115, 103, 240, 0.0)');
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    { label: 'CWND', data: [], borderColor: '#7367f0', backgroundColor: gradient, borderWidth: 2, pointRadius: 0, fill: true, tension: 0.3 },
                    { label: 'SSTHRESH', data: [], borderColor: '#ff9f43', borderWidth: 2, borderDash: [5,5], pointRadius: 0, fill: false }
                ]
            },
            options: { responsive: true, maintainAspectRatio: false, animation: false, scales: { x: { display: false }, y: { grid: { color: '#333' }, ticks: { color: '#aaa' } } }, plugins: { legend: { display: false } } }
        });
    }

    function setUiState(state) {
        document.getElementById('startSection').style.display = 'none';
        document.getElementById('runningSection').style.display = 'none';
        document.getElementById('pausedSection').style.display = 'none';
        const st = document.getElementById('status');

        if (state === 'IDLE') {
            document.getElementById('startSection').style.display = 'block';
            st.innerText = 'מצב: מוכן'; st.style.color = '#888';
        } else if (state === 'RUNNING') {
            document.getElementById('runningSection').style.display = 'flex';
            document.getElementById('runningSection').style.flexDirection = 'column';
            document.getElementById('runningSection').style.gap = '10px';
            st.innerText = 'מצב: רץ...'; st.style.color = 'var(--success)';
        } else if (state === 'PAUSED') {
            document.getElementById('pausedSection').style.display = 'flex';
            st.innerText = 'מצב: מושהה'; st.style.color = 'var(--warning)';
        }
    }

    function updateSpeed(val) {
        fetch('/action', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ cmd: 'speed', val: val/1000 }) });
    }

    function startClient() {
        const filename = document.getElementById('filename').value;
        const loss = document.getElementById('loss').value;
        fetch('/action', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ cmd: 'start', filename, loss }) });
        setUiState('RUNNING');
    }
    function pauseClient() { fetch('/action', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ cmd: 'pause' }) }); setUiState('PAUSED'); }
    function resumeClient() { fetch('/action', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ cmd: 'resume' }) }); setUiState('RUNNING'); }
    function restartClient() { fetch('/action', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ cmd: 'stop' }) }); setUiState('IDLE'); setTimeout(startClient, 500); }
    function stopClient() { fetch('/action', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ cmd: 'stop' }) }); setUiState('IDLE'); }

    function openFolder() { fetch('/action', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ cmd: 'open' }) }); }
    function toggleModal() { const el = document.getElementById('glossaryModal'); el.style.display = el.style.display === 'flex' ? 'none' : 'flex'; }

    function downloadLog() {
        if(!allLogsText) return alert("אין לוגים");
        const blob = new Blob([allLogsText], { type: 'text/plain;charset=utf-8' });
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = "RUDP_Log.txt"; a.click();
    }
    function downloadGlossary() {
        let text = "📚 מילון מושגים - פרויקט RUDP\n================================\n\n";
        glossaryData.forEach(i => text += `[${i.k}]\n${i.d}\n\n`);
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = "RUDP_Glossary.txt"; a.click();
    }

    function updateDashboard() {
        fetch('/data').then(r => r.json()).then(data => {
            const clients = Object.values(data.clients);
            if(clients.length > 0) {
                const c = clients[0];
                document.getElementById('val-cwnd').innerText = c.cwnd;
                document.getElementById('val-rwnd').innerText = c.rwnd;
                document.getElementById('val-rto').innerText = c.rto + 's';
                const p = c.total ? (c.sent/c.total) : 0;
                document.getElementById('val-progress').innerText = (p*100).toFixed(1)+'%';
                if(p >= 1 && c.state !== 'DONE_ANI') confetti({ particleCount: 100, spread: 70, origin: { y: 0.6 } });

                const grid = document.getElementById('packetGrid');
                let gridHtml = '';
                const maxView = 300;
                for(let i=1; i<=Math.min(c.total || 0, maxView); i++) {
                    let cls = 'pkt';
                    if((c.acked_packets || []).includes(i)) cls += ' acked';
                    else if((c.lost_packets || []).includes(i)) cls += ' lost';
                    else if(i < (c.send_base || 1) + (c.cwnd || 1)) cls += ' sent';
                    gridHtml += `<div class="${cls}" title="SEQ ${i}"></div>`;
                }
                if(grid.innerHTML !== gridHtml) grid.innerHTML = gridHtml;
            }
            if(data.graph_data.length > 0) {
                chart.data.labels = data.graph_data.map(d => d.time);
                chart.data.datasets[0].data = data.graph_data.map(d => d.cwnd);
                chart.data.datasets[1].data = data.graph_data.map(d => d.ssthresh);
                chart.update();
            }
            const logDiv = document.getElementById('logContent');
            let html = ''; allLogsText = "";
            data.logs.forEach(log => {
                let cls = '';
                if(log.type==='error') cls='msg-err'; else if(log.type==='success') cls='msg-ok'; else if(log.type==='warning') cls='msg-warn';
                html += `<div class="log-row"><span class="l-time">[${log.time}]</span><span class="l-tag">${log.client}:</span> <span class="${cls} l-msg">${log.msg}</span></div>`;
                allLogsText += `[${log.time}] [${log.client}] ${log.msg}\n`;
            });
            if(logDiv.innerHTML !== html) { logDiv.innerHTML = html; logDiv.scrollTop = logDiv.scrollHeight; }
        }).catch(()=>{});
    }

    initChart();
    setInterval(updateDashboard, 250);
</script>
</body>
</html>
"""


# ==========================================
#          Web Handler
# ==========================================
class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200);
            self.send_header('Content-type', 'text/html; charset=utf-8');
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode('utf-8'))
        elif self.path == '/data':
            self.send_response(200);
            self.send_header('Content-type', 'application/json');
            self.end_headers()
            with log_lock:
                self.wfile.write(json.dumps(SERVER_STATE).encode('utf-8'))

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        post_data = json.loads(self.rfile.read(length))
        cmd = post_data.get('cmd')

        if cmd == 'start':
            SERVER_STATE["clients"] = {};
            SERVER_STATE["graph_data"] = [];
            SERVER_STATE["logs"] = []
            SERVER_STATE["running"] = True;
            SERVER_STATE["paused"] = False;
            SERVER_STATE["should_stop"] = False
            t = threading.Thread(target=run_simulated_client,
                                 args=(post_data.get('filename'), post_data.get('loss'), ""))
            t.daemon = True;
            t.start()
            add_log("SYSTEM", "התחלת סימולציה", "success")

        elif cmd == 'pause':
            SERVER_STATE["paused"] = True; add_log("SYSTEM", "המערכת מושהית", "warning")
        elif cmd == 'resume':
            SERVER_STATE["paused"] = False; add_log("SYSTEM", "ממשיך ריצה", "success")
        elif cmd == 'stop':
            SERVER_STATE["running"] = False;
            SERVER_STATE["should_stop"] = True;
            SERVER_STATE["clients"] = {}
            add_log("SYSTEM", "עצירה מלאה (Kill)", "error")
        elif cmd == 'speed':
            SERVER_STATE["speed_delay"] = float(post_data.get('val', 0.0))
        elif cmd == 'open':
            path = SERVER_STATE["last_save_path"]
            try:
                if platform.system() == "Windows":
                    os.startfile(path)
                elif platform.system() == "Darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
            except:
                pass

        self.send_response(200);
        self.end_headers()

    def log_message(self, format, *args):
        pass


# ==========================================
#          Client Logic (Simulated)
# ==========================================
def calculate_checksum(data): return sum(data)


def run_simulated_client(filename, loss_probability, save_path_input):
    SERVER_HOST_LOCAL = '127.0.0.1';
    PORT_LOCAL = 54321
    dl_path = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.exists(dl_path): dl_path = os.getcwd()
    SERVER_STATE["last_save_path"] = dl_path
    full_path = os.path.join(dl_path, f"received_{filename}")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.2)
            handshake = False
            while not handshake and SERVER_STATE["running"]:
                while SERVER_STATE["paused"]: time.sleep(0.2)
                try:
                    s.sendto(b'SYN', (SERVER_HOST_LOCAL, PORT_LOCAL))
                    d, _ = s.recvfrom(1024)
                    if d.startswith(b'SYN-ACK|'):
                        new_port = int(d.decode().split('|')[1]);
                        srv_addr = (SERVER_HOST_LOCAL, new_port);
                        handshake = True
                        add_log("CLIENT", f"מחובר! פורט: {new_port}", "success")
                except:
                    continue

            if not SERVER_STATE["running"]: return
            s.sendto(f"ACK|REQ|{filename}|32".encode(), srv_addr)
            exp_seq = 1;
            buf = {}

            with open(full_path, 'wb') as f:
                while SERVER_STATE["running"]:
                    while SERVER_STATE["paused"]: time.sleep(0.2)
                    if SERVER_STATE["speed_delay"] > 0: time.sleep(SERVER_STATE["speed_delay"])

                    try:
                        pkt, _ = s.recvfrom(1024)
                        if random.randint(0, 100) < int(loss_probability):
                            if pkt.startswith(b'SEQ'): add_log("NETWORK",
                                                               f"חבילה {pkt.decode().split('|')[1]} נפלה בדרך",
                                                               "error"); continue
                        if pkt == b'FIN':
                            s.sendto(b'ACK', srv_addr);
                            s.sendto(b'FIN', srv_addr)
                            add_log("CLIENT", "סיום מוצלח!", "success");
                            break

                        parts = pkt.split(b'|', 3)
                        if len(parts) < 4: continue
                        seq = int(parts[1].decode());
                        payload = parts[3];
                        rwnd = 32 - len(buf)
                        s.sendto(f"ACK|{seq}|{rwnd}|{exp_seq}".encode(), srv_addr)
                        if seq == exp_seq:
                            f.write(payload);
                            exp_seq += 1
                            while exp_seq in buf: f.write(buf[exp_seq]); del buf[exp_seq]; exp_seq += 1
                        else:
                            if seq > exp_seq: buf[seq] = payload
                    except:
                        continue
    except Exception as e:
        add_log("CLIENT", str(e), "error")


# ==========================================
#          Server Logic (RUDP)
# ==========================================
def handle_client_connection(client_addr, welcome_socket):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handler:
        handler.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        handler.bind((HOST, 0));
        new_port = handler.getsockname()[1];
        c_id = f"SRV:{new_port}"

        try:
            handler.settimeout(0.1)
            welcome_socket.sendto(f"SYN-ACK|{new_port}".encode(), client_addr)
            fname = "";
            crwnd = 32;
            req = False;
            start = time.time()

            while SERVER_STATE["running"] and not req:
                if time.time() - start > 10: return
                try:
                    d, _ = handler.recvfrom(BUFFER_SIZE)
                    p = d.decode().split('|')
                    if len(p) == 4 and p[1] == 'REQ': fname = p[2]; crwnd = int(p[3]); req = True
                except:
                    continue

            if not SERVER_STATE["running"]: return
            fpath = os.path.join(FILES_DIR, fname)
            if not os.path.exists(fpath):
                all_packets = [f"SEQ|{i}|0|DATA".encode() for i in range(1, 301)]
                add_log(c_id, "קובץ דמי נוצר לסימולציה", "warning")
            else:
                all_packets = []
                with open(fpath, 'rb') as f:
                    sq = 1
                    while True:
                        ch = f.read(CHUNK_SIZE)
                        if not ch: break
                        all_packets.append(f"SEQ|{sq}|{sum(ch)}|".encode() + ch);
                        sq += 1

            total = len(all_packets);
            add_log(c_id, f"שולח {total} חבילות...", "info")
            base = 1;
            next_sq = 1;
            timers = {};
            acked = set();
            lost = [];
            cwnd = 1.0;
            ssthresh = 16;
            rto = 1.0;
            dup = {};
            state = "SS";
            t0 = time.time()
            SERVER_STATE["clients"][c_id] = {"cwnd": 1, "rwnd": crwnd, "rto": 1.0, "state": "SS", "sent": 0,
                                             "total": total, "acked_packets": [], "lost_packets": []}

            while base <= total and SERVER_STATE["running"]:
                while SERVER_STATE["paused"]: time.sleep(0.2)
                if SERVER_STATE["speed_delay"] > 0: time.sleep(SERVER_STATE["speed_delay"])

                if random.random() < 0.3:
                    SERVER_STATE["graph_data"].append(
                        {"time": f"{time.time() - t0:.1f}", "cwnd": cwnd, "ssthresh": ssthresh})
                    if len(SERVER_STATE["graph_data"]) > 60: SERVER_STATE["graph_data"].pop(0)

                SERVER_STATE["clients"][c_id].update(
                    {"cwnd": int(cwnd), "rwnd": crwnd, "rto": round(rto, 2), "state": state, "sent": base - 1,
                     "acked_packets": list(acked), "lost_packets": lost})

                eff = min(int(cwnd), crwnd)
                while next_sq < base + eff and next_sq <= total:
                    if next_sq not in timers:
                        handler.sendto(all_packets[next_sq - 1], client_addr)
                        timers[next_sq] = time.time()
                    next_sq += 1

                for sq, t in list(timers.items()):
                    if time.time() - t > rto:
                        add_log(c_id, f"TIMEOUT SEQ {sq}", "warning")
                        ssthresh = max(int(cwnd / 2), 2);
                        cwnd = 1.0;
                        state = "TIMEOUT"
                        handler.sendto(all_packets[sq - 1], client_addr)
                        timers[sq] = time.time()
                        if sq not in lost: lost.append(sq)

                try:
                    handler.settimeout(0.05)
                    d, _ = handler.recvfrom(BUFFER_SIZE)
                    p = d.decode().split('|')
                    if p[0] == 'ACK':
                        ak = int(p[1]);
                        crwnd = int(p[2]);
                        exp = int(p[3])
                        if exp < next_sq and exp not in acked:
                            dup[exp] = dup.get(exp, 0) + 1
                            if dup[exp] == FAST_RETRANSMIT_THRESHOLD:
                                add_log(c_id, f"Fast Retransmit SEQ {exp}", "error")
                                state = "FAST RETRANSMIT";
                                ssthresh = max(int(cwnd / 2), 2);
                                cwnd = ssthresh
                                handler.sendto(all_packets[exp - 1], client_addr)
                                timers[exp] = time.time();
                                dup[exp] = 0
                                if exp not in lost: lost.append(exp)
                        if base <= ak < next_sq:
                            if ak not in acked:
                                acked.add(ak)
                                if ak in timers: del timers[ak]
                                if cwnd < ssthresh:
                                    cwnd += 1; state = "SS"
                                else:
                                    cwnd += 1.0 / int(cwnd); state = "CA"
                            while base in acked: acked.remove(base); base += 1
                except:
                    pass

            if SERVER_STATE["running"]:
                handler.sendto(b'FIN', client_addr)
                SERVER_STATE["clients"][c_id]["state"] = "DONE_ANI"
        except Exception as e:
            add_log(c_id, f"Closed: {e}", "warning")


if __name__ == "__main__":
    threading.Thread(target=lambda: HTTPServer(('0.0.0.0', HTTP_PORT), WebHandler).serve_forever(), daemon=True).start()
    print(f"\n   ✅ RUDP SERVER V9 ONLINE")
    print(f"   🔗 Open Dashboard: http://127.0.0.1:{HTTP_PORT}\n")
    add_log("SYSTEM", "המערכת מוכנה.", "success")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, WELCOME_PORT));
    sock.settimeout(0.5)
    while True:
        try:
            d, a = sock.recvfrom(1024)
            if d == b'SYN' and not SERVER_STATE["should_stop"]:
                threading.Thread(target=handle_client_connection, args=(a, sock)).start()
        except:
            pass