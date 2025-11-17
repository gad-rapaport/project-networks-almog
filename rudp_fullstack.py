import socket
import os
import time
import sys
import threading
import json
import random
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---------------------------------
# הגדרות
# ---------------------------------
HOST = '127.0.0.1'
WELCOME_PORT = 54321
HTTP_PORT = 8080
BUFFER_SIZE = 1024
CHUNK_SIZE = 980
FILES_DIR = r"C:\Users\user\OneDrive\שולחן העבודה\לימודים\תקשורת\networks-projects\project\files"

ALPHA = 0.125
BETA = 0.25
INITIAL_RTO = 1.0
FAST_RETRANSMIT_THRESHOLD = 3

# הזיכרון המשותף
SERVER_STATE = {
    "clients": {},
    "graph_data": [],
    "logs": []  # רשימת הלוגים להצגה וייצוא
}

# מנעול לסנכרון גישה ללוגים (Thread Safety)
log_lock = threading.Lock()


def add_log(client_id, message, type="info"):
    """
    מוסיף שורה ללוג המרכזי עם חותמת זמן
    types: info, success, warning, error
    """
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_entry = {
        "time": timestamp,
        "client": client_id,
        "msg": message,
        "type": type
    }
    with log_lock:
        SERVER_STATE["logs"].append(log_entry)
        # שמירת רק 200 הלוגים האחרונים בזיכרון כדי לא להכביד על הדפדפן
        # (אבל בייצוא נשמור הכל - לוגיקה מפוצלת בהמשך אם תרצה)
        if len(SERVER_STATE["logs"]) > 500:
            SERVER_STATE["logs"].pop(0)


# ---------------------------------
# ממשק HTML/JS/CSS משודרג
# ---------------------------------
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RUDP Pro Simulator</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Rubik:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --accent: #3b82f6; --success: #22c55e; --danger: #ef4444; --warning: #eab308; }
        body { font-family: 'Rubik', sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; display: flex; height: 100vh; box-sizing: border-box; overflow: hidden; }

        /* Layout */
        .sidebar { width: 300px; background: var(--card); padding: 20px; border-radius: 16px; display: flex; flex-direction: column; gap: 15px; height: 100%; overflow-y: auto; box-shadow: 4px 0 15px rgba(0,0,0,0.3); }
        .main { flex: 1; margin-right: 20px; display: grid; grid-template-rows: auto 1fr 1fr; gap: 20px; height: 100%; overflow: hidden; }

        /* Components */
        h2 { margin: 0 0 10px 0; color: var(--accent); font-size: 1.2rem; }

        .btn { background: var(--accent); color: white; border: none; padding: 12px; border-radius: 8px; cursor: pointer; font-weight: bold; width: 100%; transition: 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .btn:hover { filter: brightness(1.1); transform: translateY(-2px); }
        .btn-danger { background: var(--danger); }
        .btn-success { background: var(--success); color: #000; }

        .input-group { background: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px; }
        .input-group label { display: block; font-size: 0.85rem; color: #94a3b8; margin-bottom: 5px; }
        input { width: 100%; background: #334155; border: 1px solid #475569; color: white; padding: 6px; border-radius: 4px; }

        /* Stats Cards */
        .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }
        .stat-card { background: var(--card); padding: 15px; border-radius: 12px; text-align: center; border: 1px solid #334155; }
        .stat-val { font-size: 1.4rem; font-weight: 700; font-family: monospace; color: var(--accent); }
        .stat-label { font-size: 0.8rem; color: #94a3b8; }

        /* Graph */
        .graph-container { background: var(--card); padding: 15px; border-radius: 12px; position: relative; }

        /* Log Console */
        .log-container { background: #000; border-radius: 12px; border: 1px solid #334155; display: flex; flex-direction: column; overflow: hidden; font-family: 'Courier New', monospace; }
        .log-header { background: #1e293b; padding: 8px 15px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; }
        .log-content { flex: 1; overflow-y: auto; padding: 10px; font-size: 0.85rem; }

        .log-line { margin-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 2px; }
        .log-time { color: #64748b; margin-left: 8px; }
        .log-info { color: #e2e8f0; }
        .log-success { color: var(--success); }
        .log-warning { color: var(--warning); }
        .log-error { color: var(--danger); font-weight: bold; }

    </style>
</head>
<body>

    <div class="sidebar">
        <h2>🎛️ בקרת משימה</h2>

        <div class="input-group">
            <label>שם קובץ:</label>
            <input type="text" id="filename" value="3.txt">
        </div>

        <div class="input-group">
            <label>איבוד חבילות (%):</label>
            <input type="range" id="loss" min="0" max="50" value="0" oninput="document.getElementById('lossVal').innerText = this.value + '%'">
            <div style="text-align: left; font-weight: bold;" id="lossVal">0%</div>
        </div>

        <button class="btn" onclick="startClient()">▶️ התחל הורדה</button>
        <button class="btn btn-danger" onclick="stopClient()">⏹️ עצור הכל</button>

        <hr style="border-color: rgba(255,255,255,0.1); width: 100%;">

        <button class="btn btn-success" onclick="downloadLog()">📥 ייצא לוג (.txt)</button>
        <button class="btn" style="background: #475569;" onclick="clearData()">🧹 נקה מסך</button>

        <div class="packet-legend" style="font-size: 0.8em; margin-top: auto; opacity: 0.7;">
            <div><span style="color:var(--accent)">●</span> מידע רגיל</div>
            <div><span style="color:var(--warning)">●</span> איבוד/שליחה מחדש</div>
            <div><span style="color:var(--success)">●</span> סיום מוצלח</div>
        </div>
    </div>

    <div class="main">
        <div class="stats-row">
            <div class="stat-card">
                <div class="stat-val" id="val-cwnd">0</div>
                <div class="stat-label">CWND</div>
            </div>
            <div class="stat-card">
                <div class="stat-val" id="val-ssthresh">0</div>
                <div class="stat-label">SSTHRESH</div>
            </div>
            <div class="stat-card">
                <div class="stat-val" id="val-rto">0s</div>
                <div class="stat-label">RTO</div>
            </div>
            <div class="stat-card">
                <div class="stat-val" id="val-progress">0%</div>
                <div class="stat-label">התקדמות</div>
            </div>
        </div>

        <div class="graph-container">
            <canvas id="mainChart"></canvas>
        </div>

        <div class="log-container">
            <div class="log-header">
                <span>📜 לוג תהליכים חי</span>
                <span style="font-size: 0.8em; opacity: 0.7;">מציג את ה-500 האחרונים</span>
            </div>
            <div id="logContent" class="log-content">
                </div>
        </div>
    </div>

<script>
    let chart;
    let allLogsText = ""; // מחזיק את כל הטקסט לייצוא

    function initChart() {
        const ctx = document.getElementById('mainChart').getContext('2d');
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'CWND',
                    data: [],
                    borderColor: '#3b82f6',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: true,
                    backgroundColor: 'rgba(59, 130, 246, 0.1)'
                },
                {
                    label: 'SSTHRESH',
                    data: [],
                    borderColor: '#eab308',
                    borderDash: [5, 5],
                    borderWidth: 2,
                    pointRadius: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { intersect: false },
                scales: {
                    x: { display: false },
                    y: { grid: { color: '#334155' } }
                },
                plugins: { legend: { labels: { color: '#e2e8f0' } } }
            }
        });
    }

    function startClient() {
        const filename = document.getElementById('filename').value;
        const loss = document.getElementById('loss').value;
        fetch('/start_client', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ filename, loss })
        });
    }

    function stopClient() {
        fetch('/stop_client', { method: 'POST' });
    }

    function clearData() {
        fetch('/clear').then(() => {
            document.getElementById('logContent').innerHTML = '';
            allLogsText = "";
            initChart(); // איפוס גרף
        });
    }

    function downloadLog() {
        if (!allLogsText) { alert("אין לוגים לייצוא"); return; }
        const blob = new Blob([allLogsText], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `RUDP_Log_${new Date().toISOString().slice(0,19).replace(/:/g,"-")}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    function updateDashboard() {
        fetch('/data')
            .then(response => response.json())
            .then(data => {
                // 1. עדכון כרטיסים
                const clients = Object.values(data.clients);
                if (clients.length > 0) {
                    const c = clients[0];
                    document.getElementById('val-cwnd').innerText = c.cwnd;
                    document.getElementById('val-ssthresh').innerText = c.ssthresh;
                    document.getElementById('val-rto').innerText = c.rto + 's';
                    const prog = ((c.sent / c.total) * 100).toFixed(1);
                    document.getElementById('val-progress').innerText = prog + '%';
                }

                // 2. עדכון גרף
                if (data.graph_data.length > 0) {
                    chart.data.labels = data.graph_data.map(d => d.time);
                    chart.data.datasets[0].data = data.graph_data.map(d => d.cwnd);
                    chart.data.datasets[1].data = data.graph_data.map(d => d.ssthresh);
                    chart.update();
                }

                // 3. עדכון לוגים
                const logDiv = document.getElementById('logContent');
                let newHtml = '';
                allLogsText = ""; // בנייה מחדש של טקסט לייצוא

                data.logs.slice().reverse().forEach(log => { // הצג חדשים למעלה
                    let colorClass = 'log-info';
                    if (log.type === 'success') colorClass = 'log-success';
                    if (log.type === 'warning') colorClass = 'log-warning';
                    if (log.type === 'error') colorClass = 'log-error';

                    newHtml += `
                        <div class="log-line">
                            <span class="log-time">[${log.time}]</span>
                            <span class="${colorClass}">${log.msg}</span>
                        </div>
                    `;
                    // שמירה לטקסט (בסדר כרונולוגי)
                    allLogsText = `[${log.time}] ${log.msg}\n` + allLogsText;
                });

                // עדכון ה-HTML רק אם השתנה משהו (למנוע הבהוב)
                if (logDiv.innerHTML !== newHtml) {
                    logDiv.innerHTML = newHtml;
                }
            });
    }

    initChart();
    setInterval(updateDashboard, 500);
</script>
</body>
</html>
"""


# ---------------------------------
# שרת ה-WEB
# ---------------------------------
class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode('utf-8'))
        elif self.path == '/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            with log_lock:  # קריאה בטוחה
                self.wfile.write(json.dumps(SERVER_STATE).encode('utf-8'))

    def do_POST(self):
        if self.path == '/start_client':
            length = int(self.headers['Content-Length'])
            post_data = json.loads(self.rfile.read(length))

            # מנקים קודם אם יש לקוח פעיל
            SERVER_STATE["clients"] = {}
            SERVER_STATE["graph_data"] = []
            SERVER_STATE["logs"] = []

            # דגל פעילות
            SERVER_STATE["running"] = True

            t = threading.Thread(target=run_simulated_client,
                                 args=(post_data['filename'], post_data['loss']))
            t.start()

            add_log("SYSTEM", f"התחלת סימולציה: קובץ {post_data['filename']}, איבוד {post_data['loss']}%", "success")
            self.send_response(200)
            self.end_headers()

        elif self.path == '/stop_client':
            SERVER_STATE["running"] = False
            add_log("SYSTEM", "התקבלה פקודת עצירה מהמשתמש", "error")
            self.send_response(200)
            self.end_headers()

        elif self.path == '/clear':
            SERVER_STATE["clients"] = {}
            SERVER_STATE["graph_data"] = []
            SERVER_STATE["logs"] = []
            self.send_response(200)
            self.end_headers()

    def log_message(self, format, *args):
        pass


# ---------------------------------
# הלקוח המוטמע (הסימולטור)
# ---------------------------------
def run_simulated_client(filename, loss_probability):
    SERVER_HOST_LOCAL = '127.0.0.1'
    PORT_LOCAL = 54321

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_socket:
            client_socket.settimeout(2)

            # Handshake
            add_log("CLIENT", f"שולח SYN לפורט {PORT_LOCAL}")
            client_socket.sendto(b'SYN', (SERVER_HOST_LOCAL, PORT_LOCAL))

            try:
                data, _ = client_socket.recvfrom(1024)
                if not data.startswith(b'SYN-ACK|'): return
            except socket.timeout:
                add_log("CLIENT", "Timeout ב-Handshake", "error")
                return

            new_port = int(data.decode().split('|')[1])
            server_addr = (SERVER_HOST_LOCAL, new_port)
            add_log("CLIENT", f"קיבלתי פורט חדש: {new_port}", "success")

            # בקשת קובץ
            client_socket.sendto(f"ACK|REQ|{filename}|32".encode(), server_addr)

            expected_seq = 1
            receive_buffer = {}

            while SERVER_STATE.get("running", False):  # בדיקת כפתור עצירה
                try:
                    packet, _ = client_socket.recvfrom(1024)

                    # סימולציית איבוד
                    if random.randint(0, 100) < int(loss_probability):
                        # אם זו חבילת מידע (ולא סגירה)
                        if packet.startswith(b'SEQ'):
                            seq_str = packet.decode().split('|')[1]
                            add_log("NETWORK", f"חבילה {seq_str} אבדה בדרך! (Simulation)", "error")
                            continue

                    if packet == b'FIN':
                        add_log("CLIENT", "התקבל FIN - סיום העברה", "success")
                        client_socket.sendto(b'ACK', server_addr)
                        client_socket.sendto(b'FIN', server_addr)
                        break

                    parts = packet.split(b'|', 3)
                    if len(parts) < 4 or parts[0] != b'SEQ': continue

                    seq = int(parts[1].decode())
                    rwnd = 32 - len(receive_buffer)

                    # שליחת ACK
                    client_socket.sendto(f"ACK|{seq}|{rwnd}|{expected_seq}".encode(), server_addr)

                    if seq == expected_seq:
                        expected_seq += 1
                        # בדיקת באפר
                        while expected_seq in receive_buffer:
                            add_log("CLIENT", f"שולף חבילה {expected_seq} מהבאפר", "info")
                            del receive_buffer[expected_seq]
                            expected_seq += 1
                    else:
                        if seq > expected_seq:
                            add_log("CLIENT", f"חבילה {seq} הגיעה לא לפי הסדר (ציפיתי ל-{expected_seq}). שומר בבאפר.",
                                    "warning")
                            receive_buffer[seq] = True

                except socket.timeout:
                    break
    except Exception as e:
        add_log("CLIENT", f"שגיאה בלקוח: {e}", "error")


# ---------------------------------
# לוגיקת שרת RUDP
# ---------------------------------
def calculate_checksum(data): return sum(data)


def handle_client_connection(client_addr, welcome_socket):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handler:
        handler.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        handler.bind((HOST, 0))
        new_port = handler.getsockname()[1]
        client_id = f"Port {new_port}"

        try:
            # Handshake
            handler.settimeout(2)
            welcome_socket.sendto(f"SYN-ACK|{new_port}".encode(), client_addr)
            data, addr = handler.recvfrom(BUFFER_SIZE)

            parts = data.decode().split('|')
            if len(parts) != 4: return
            filename = parts[2]
            client_rwnd = int(parts[3])

            # בדיקת קובץ (או יצירת דמי)
            filepath = os.path.join(FILES_DIR, filename)
            if not os.path.exists(filepath):
                # ניצור תוכן דמי אם אין קובץ, כדי שהסימולציה תעבוד
                all_packets = [f"SEQ|{i}|0|DATA".encode() for i in range(1, 501)]
            else:
                all_packets = []
                with open(filepath, 'rb') as f:
                    seq = 1
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk: break
                        pkt = f"SEQ|{seq}|{calculate_checksum(chunk)}|".encode() + chunk
                        all_packets.append(pkt)
                        seq += 1

            total = len(all_packets)
            add_log(client_id, f"מתחיל שליחת {total} חבילות", "info")

            # משתנים
            send_base = 1
            next_seq = 1
            timers = {}
            acked = set()
            cwnd = 1.0
            ssthresh = 16
            rto = 1.0
            dup_acks = {}
            state = "Slow Start"
            start_time = time.time()

            SERVER_STATE["clients"][client_id] = {
                "cwnd": 1, "ssthresh": 16, "rto": 1.0, "state": "SS",
                "sent": 0, "total": total
            }

            while send_base <= total and SERVER_STATE.get("running", True):

                # עדכון גרף
                if random.random() < 0.2:
                    SERVER_STATE["graph_data"].append({
                        "time": f"{time.time() - start_time:.1f}",
                        "cwnd": cwnd,
                        "ssthresh": ssthresh
                    })

                SERVER_STATE["clients"][client_id].update({
                    "cwnd": int(cwnd), "ssthresh": ssthresh, "rto": round(rto, 2),
                    "state": state, "sent": send_base - 1
                })

                # שליחה
                eff_win = min(int(cwnd), client_rwnd)
                while next_seq < send_base + eff_win and next_seq <= total:
                    if next_seq not in timers:
                        handler.sendto(all_packets[next_seq - 1], client_addr)
                        timers[next_seq] = time.time()
                        # add_log(client_id, f"נשלחה חבילה {next_seq}", "info") # מכביד מדי על הלוג
                    next_seq += 1

                # Timeout
                for seq, t in list(timers.items()):
                    if time.time() - t > rto:
                        add_log(client_id, f"TIMEOUT לחבילה {seq}! חוזר ל-Slow Start", "error")
                        state = "TIMEOUT"
                        ssthresh = max(int(cwnd / 2), 2)
                        cwnd = 1.0
                        handler.sendto(all_packets[seq - 1], client_addr)
                        timers[seq] = time.time()

                # קליטה
                try:
                    handler.settimeout(0.01)
                    d, _ = handler.recvfrom(BUFFER_SIZE)
                    p = d.decode().split('|')
                    if p[0] == 'ACK':
                        ack = int(p[1])
                        client_rwnd = int(p[2])
                        expected = int(p[3])

                        # Fast Retransmit Logic
                        if expected < next_seq and expected not in acked:
                            dup_acks[expected] = dup_acks.get(expected, 0) + 1
                            if dup_acks[expected] == 3:
                                add_log(client_id, f"Fast Retransmit לחבילה {expected} (3 ACKs כפולים)", "warning")
                                state = "FAST RETRANSMIT"
                                ssthresh = max(int(cwnd / 2), 2)
                                cwnd = ssthresh
                                handler.sendto(all_packets[expected - 1], client_addr)
                                timers[expected] = time.time()
                                dup_acks[expected] = 0

                        if send_base <= ack < next_seq:
                            if ack not in acked:
                                acked.add(ack)
                                if ack in timers: del timers[ack]
                                # AIMD
                                if cwnd < ssthresh:
                                    cwnd += 1;
                                    state = "Slow Start"
                                else:
                                    cwnd += 1.0 / int(cwnd);
                                    state = "Congestion Avoidance"

                            while send_base in acked:
                                acked.remove(send_base)
                                send_base += 1

                except socket.timeout:
                    pass

            # סגירה
            add_log(client_id, "העברה הסתיימה. שולח FIN.", "success")
            handler.sendto(b'FIN', client_addr)

        except Exception as e:
            add_log(client_id, f"שגיאה קריטית: {e}", "error")


# ---------------------------------
# Main
# ---------------------------------
if __name__ == "__main__":
    threading.Thread(target=lambda: HTTPServer(('0.0.0.0', HTTP_PORT), WebHandler).serve_forever(), daemon=True).start()

    print(f"🔥 המערכת פועלת! כנס לכתובת: http://127.0.0.1:{HTTP_PORT}")
    add_log("SYSTEM", "שרת הופעל והוא מוכן לקליטה", "success")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, WELCOME_PORT))

    while True:
        try:
            d, a = sock.recvfrom(1024)
            if d == b'SYN':
                threading.Thread(target=handle_client_connection, args=(a, sock)).start()
        except:
            pass