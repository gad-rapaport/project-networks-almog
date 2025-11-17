import socket
import os
import time
import sys
import threading
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---------------------------------
# הגדרות קבועות
# ---------------------------------
HOST = '127.0.0.1'
WELCOME_PORT = 54321
HTTP_PORT = 8080  # <-- פורט לממשק הדפדפן
BUFFER_SIZE = 1024
CHUNK_SIZE = 980
FILES_DIR = r"C:\Users\user\OneDrive\שולחן העבודה\לימודים\תקשורת\networks-projects\project\files"

# --- קבועים עבור RTT דינאמי ---
ALPHA = 0.125
BETA = 0.25
INITIAL_RTO = 1.0
FAST_RETRANSMIT_THRESHOLD = 3

# --- משתנה גלובלי למצב השרת (עבור הדשבורד) ---
# מילון שיכיל מידע חי על כל לקוח מחובר
SERVER_STATE = {}

# ---------------------------------
# תבנית ה-HTML/JS של הדשבורד
# ---------------------------------
# ---------------------------------
# תבנית ה-HTML/JS של הדשבורד המשודרג
# ---------------------------------
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>מערכת ניטור RUDP</title>
    <link href="https://fonts.googleapis.com/css2?family=Rubik:wght@300;400;500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #0f172a;
            --card-bg: #1e293b;
            --text-main: #e2e8f0;
            --text-muted: #94a3b8;
            --accent: #3b82f6;
            --success: #22c55e;
            --warning: #eab308;
            --danger: #ef4444;
            --glass: rgba(30, 41, 59, 0.7);
        }

        * { box-sizing: border-box; transition: all 0.3s ease; }

        body {
            font-family: 'Rubik', sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-main);
            margin: 0;
            padding: 20px;
            line-height: 1.6;
        }

        /* --- Header --- */
        header {
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        h1 { margin: 0; font-size: 2.5rem; background: linear-gradient(45deg, var(--accent), #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: var(--text-muted); margin-top: 5px; }

        /* --- Guide Section --- */
        .guide-panel {
            background: rgba(255,255,255,0.03);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 30px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            border: 1px solid rgba(255,255,255,0.05);
        }

        .guide-item { display: flex; align-items: center; gap: 10px; font-size: 0.9rem; }
        .dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
        .dot.ss { background: var(--success); box-shadow: 0 0 10px var(--success); }
        .dot.ca { background: var(--warning); box-shadow: 0 0 10px var(--warning); }
        .dot.fr { background: var(--danger); animation: pulse 1.5s infinite; }

        /* --- Grid Layout --- */
        .container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 25px;
            max-width: 1400px;
            margin: 0 auto;
        }

        /* --- Client Card --- */
        .card {
            background: var(--card-bg);
            border-radius: 16px;
            padding: 25px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255,255,255,0.05);
            position: relative;
            overflow: hidden;
        }
        .card::before {
            content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 4px;
            background: linear-gradient(90deg, var(--accent), #818cf8);
        }

        .card-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px; }
        .client-title { font-weight: 700; font-size: 1.2rem; }
        .file-badge { font-size: 0.85rem; background: rgba(255,255,255,0.1); padding: 4px 10px; border-radius: 8px; color: var(--text-muted); }

        .status-badge {
            padding: 6px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: bold;
            text-transform: uppercase; letter-spacing: 0.5px;
        }
        .status-ss { background: rgba(34, 197, 94, 0.2); color: var(--success); border: 1px solid var(--success); }
        .status-ca { background: rgba(234, 179, 8, 0.2); color: var(--warning); border: 1px solid var(--warning); }
        .status-fr { background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid var(--danger); animation: pulse 1s infinite; }

        /* --- Metrics Grid --- */
        .metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; }

        .metric-box {
            background: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px;
            position: relative; cursor: help;
        }
        .metric-box:hover { background: rgba(255,255,255,0.05); }

        /* Tooltip Logic */
        .metric-box::after {
            content: attr(data-tooltip);
            position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%);
            background: #334155; color: white; padding: 8px 12px; border-radius: 6px;
            font-size: 0.8rem; white-space: nowrap; pointer-events: none;
            opacity: 0; visibility: hidden; transition: opacity 0.2s; z-index: 10;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3); width: max-content; max-width: 200px; white-space: normal; text-align: center;
        }
        .metric-box:hover::after { opacity: 1; visibility: visible; bottom: 110%; }

        .metric-label { font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); display: block; margin-bottom: 4px; }
        .metric-value { font-size: 1.2rem; font-weight: 700; font-family: monospace; }

        /* --- Progress Bar --- */
        .progress-wrapper { position: relative; height: 24px; background: rgba(255,255,255,0.1); border-radius: 12px; overflow: hidden; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, var(--success), var(--accent)); width: 0%; border-radius: 12px; transition: width 0.5s ease-out; }
        .progress-text { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 0.8rem; font-weight: bold; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }

        /* --- Glossary Section --- */
        .glossary { margin-top: 60px; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 40px; }
        .glossary h2 { color: var(--accent); }
        .term-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }
        .term { background: rgba(255,255,255,0.02); padding: 15px; border-radius: 8px; }
        .term h3 { margin-top: 0; color: var(--text-main); font-size: 1rem; }
        .term p { font-size: 0.9rem; color: var(--text-muted); margin-bottom: 0; }

        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.6; } 100% { opacity: 1; } }
        .empty-state { text-align: center; padding: 100px 20px; opacity: 0.5; grid-column: 1 / -1; }
        .empty-icon { font-size: 4rem; margin-bottom: 20px; display: block; }

    </style>
</head>
<body>

    <header>
        <h1>📡 RUDP Control Center</h1>
        <div class="subtitle">מערכת ניטור ובקרת עומסים בזמן אמת</div>
    </header>

    <div class="guide-panel">
        <div class="guide-item">
            <span class="dot ss"></span>
            <span><strong>Slow Start:</strong> מצב האצה (הכפלת קצב)</span>
        </div>
        <div class="guide-item">
            <span class="dot ca"></span>
            <span><strong>Congestion Avoidance:</strong> מצב זהירות (גדילה ליניארית)</span>
        </div>
        <div class="guide-item">
            <span class="dot fr"></span>
            <span><strong>Fast Retransmit:</strong> זיהוי איבוד ושליחה חוזרת</span>
        </div>
    </div>

    <div id="grid" class="container">
        <div class="empty-state">
            <span class="empty-icon">💤</span>
            ממתין ללקוחות שיתחברו...<br>הרץ את <code>client.py</code> כדי להתחיל
        </div>
    </div>

    <div class="glossary">
        <h2>📚 מילון מושגים וטכנולוגיה</h2>
        <div class="term-grid">
            <div class="term">
                <h3>CWND (Congestion Window)</h3>
                <p>חלון הגודש. קובע כמה חבילות השרת מורשה לשלוח לרשת מבלי לחכות לאישור. גדל כשהרשת פנויה וקטן כשיש עומס.</p>
            </div>
            <div class="term">
                <h3>RWND (Receive Window)</h3>
                <p>חלון הקליטה של הלקוח. מונע מהשרת להציף את הלקוח במידע מהר מכפי שהוא יכול לעבד אותו (Flow Control).</p>
            </div>
            <div class="term">
                <h3>RTO (Retransmission Timeout)</h3>
                <p>פסק זמן דינאמי. השרת מודד את מהירות הרשת (RTT) ומחשב כמה זמן לחכות ל-ACK לפני שהוא מכריז על איבוד חבילה.</p>
            </div>
            <div class="term">
                <h3>Selective Repeat</h3>
                <p>שיטת העברה חכמה. אם חבילה אחת אובדת, הלקוח שומר את החבילות הבאות בבאפר, והשרת שולח מחדש <strong>רק</strong> את החבילה החסרה.</p>
            </div>
        </div>
    </div>

    <script>
        function updateDashboard() {
            fetch('/data')
                .then(response => response.json())
                .then(data => {
                    const grid = document.getElementById('grid');

                    if (Object.keys(data).length === 0) {
                        if (!grid.innerHTML.includes('empty-state')) {
                             grid.innerHTML = `
                                <div class="empty-state">
                                    <span class="empty-icon">💤</span>
                                    ממתין ללקוחות שיתחברו...
                                </div>`;
                        }
                        return;
                    }

                    let html = '';
                    for (const [id, client] of Object.entries(data)) {
                        // קביעת צבעים וסטטוסים לפי המצב
                        let statusClass = 'status-ss';
                        let statusText = 'Slow Start 🚀';

                        if (client.state === 'CA') {
                            statusClass = 'status-ca';
                            statusText = 'Congestion Avoidance ⚖️';
                        }
                        if (client.state.includes('Fast') || client.state.includes('TIMEOUT')) {
                            statusClass = 'status-fr';
                            statusText = client.state.includes('Fast') ? 'Fast Retransmit 🚨' : 'Timeout Recovery 🐌';
                        }
                        if (client.state.includes('FINISHED')) {
                            statusClass = 'status-ss'; // ירוק
                            statusText = 'הסתיים בהצלחה ✅';
                        }

                        const progress = ((client.sent / client.total) * 100).toFixed(1);

                        html += `
                        <div class="card">
                            <div class="card-header">
                                <div>
                                    <div class="client-title">Client Port: ${client.port}</div>
                                    <span class="file-badge">📄 ${client.file}</span>
                                </div>
                                <div class="status-badge ${statusClass}">${statusText}</div>
                            </div>

                            <div class="metrics">
                                <div class="metric-box" data-tooltip="חלון גודש: כמה השרת שולח במקביל לפי מצב הרשת">
                                    <span class="metric-label">CWND (רשת)</span>
                                    <span class="metric-value" style="color: var(--accent)">${client.cwnd}</span>
                                </div>
                                <div class="metric-box" data-tooltip="חלון קליטה: כמה מקום פנוי יש בבאפר של הלקוח">
                                    <span class="metric-label">RWND (לקוח)</span>
                                    <span class="metric-value" style="color: var(--warning)">${client.rwnd}</span>
                                </div>
                                <div class="metric-box" data-tooltip="פסק זמן דינאמי המחושב לפי מהירות הרשת הנוכחית">
                                    <span class="metric-label">RTO Timer</span>
                                    <span class="metric-value">${client.rto}s</span>
                                </div>
                                <div class="metric-box" data-tooltip="חבילות שנשלחו מתוך סך הכל">
                                    <span class="metric-label">Progress</span>
                                    <span class="metric-value">${client.sent} / ${client.total}</span>
                                </div>
                            </div>

                            <div class="progress-wrapper">
                                <div class="progress-fill" style="width: ${progress}%"></div>
                                <div class="progress-text">${progress}%</div>
                            </div>
                        </div>
                        `;
                    }
                    grid.innerHTML = html;
                })
                .catch(err => console.error('Connection Lost', err));
        }

        setInterval(updateDashboard, 200); // עדכון מהיר מאוד (5 פעמים בשנייה) לאנימציה חלקה
        updateDashboard();
    </script>
</body>
</html>
"""


# ---------------------------------
# מחלקת שרת ה-WEB (Dashboard)
# ---------------------------------
class DashboardHandler(BaseHTTPRequestHandler):
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
            # שליחת נתוני השרת כ-JSON
            self.wfile.write(json.dumps(SERVER_STATE).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    # ביטול הדפסות הלוג של HTTP לטרמינל כדי לא להפריע
    def log_message(self, format, *args):
        pass


def start_dashboard_server():
    server = HTTPServer(('0.0.0.0', HTTP_PORT), DashboardHandler)
    print(f"📊 Dashboard running at: http://127.0.0.1:{HTTP_PORT}")
    server.serve_forever()


# ---------------------------------
# פונקציות עזר ל-RUDP
# ---------------------------------
def calculate_checksum(data):
    return sum(data)


# ---------------------------------
# פונקציית הטיפול בלקוח (Thread)
# ---------------------------------
def handle_client_connection(client_addr, welcome_socket):
    thread_name = threading.current_thread().name

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handler_socket:
        handler_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        handler_socket.bind((HOST, 0))
        new_port = handler_socket.getsockname()[1]

        # מפתח ייחודי ללקוח בדשבורד
        client_key = f"{client_addr[0]}:{client_addr[1]}"

        try:
            # 1. Handshake
            handler_socket.settimeout(INITIAL_RTO * 2)
            welcome_socket.sendto(f"SYN-ACK|{new_port}".encode(), client_addr)

            data, addr = handler_socket.recvfrom(BUFFER_SIZE)
            if addr != client_addr: return

            parts = data.decode().split('|')
            if len(parts) != 4 or parts[0] != 'ACK' or parts[1] != 'REQ': return

            filename = parts[2]
            client_rwnd = int(parts[3])

            # 2. הכנת קובץ
            filepath = os.path.join(FILES_DIR, filename)
            if not os.path.exists(filepath):
                handler_socket.sendto(b'ERROR|File not found', client_addr)
                return

            all_packets = []
            seq_num = 1
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk: break
                    checksum = calculate_checksum(chunk)
                    packet = f"SEQ|{seq_num}|{checksum}|".encode() + chunk
                    all_packets.append(packet)
                    seq_num += 1

            total_packets = len(all_packets)

            # 3. משתני בקרה
            send_base = 1
            next_seq_num = 1
            packet_timers = {}
            acked_packets = set()

            cwnd = 1.0
            ssthresh = 16
            congestion_state = "SS"

            EstimatedRTT = INITIAL_RTO
            DevRTT = 0.0
            TimeoutInterval = EstimatedRTT
            missing_packet_reports = {}

            transfer_in_progress = True

            # --- הוספת הלקוח לדשבורד ---
            SERVER_STATE[client_key] = {
                "port": new_port,
                "file": filename,
                "sent": 0,
                "total": total_packets,
                "cwnd": 1,
                "rwnd": client_rwnd,
                "rto": f"{TimeoutInterval:.2f}",
                "state": "Slow Start (SS)"
            }

            while transfer_in_progress:

                # עדכון הדשבורד בזמן אמת
                SERVER_STATE[client_key].update({
                    "sent": send_base - 1,
                    "cwnd": int(cwnd),
                    "rwnd": client_rwnd,
                    "rto": f"{TimeoutInterval:.2f}",
                    "state": congestion_state
                })

                # א. שליחה
                effective_window = min(int(cwnd), client_rwnd)
                while next_seq_num < send_base + effective_window and next_seq_num <= total_packets:
                    if next_seq_num not in packet_timers:
                        handler_socket.sendto(all_packets[next_seq_num - 1], client_addr)
                        packet_timers[next_seq_num] = time.time()
                    next_seq_num += 1

                # ב. Timeout
                timed_out_packets = []
                for seq, start_time in packet_timers.items():
                    if time.time() - start_time > TimeoutInterval:
                        timed_out_packets.append(seq)

                for seq in timed_out_packets:
                    print(f"[{new_port}] Timeout SEQ {seq}")
                    ssthresh = max(int(cwnd / 2), 2)
                    cwnd = 1.0
                    congestion_state = "TIMEOUT (SS)"  # עדכון סטטוס ויזואלי
                    handler_socket.sendto(all_packets[seq - 1], client_addr)
                    packet_timers[seq] = time.time()

                # ג. קבלת ACKs
                try:
                    handler_socket.settimeout(0.01)
                    ack_data, _ = handler_socket.recvfrom(BUFFER_SIZE)
                    parts = ack_data.decode().split('|')

                    if parts[0] == 'ACK' and len(parts) == 4:
                        ack_num = int(parts[1])
                        client_rwnd = int(parts[2])
                        expected_by_client = int(parts[3])

                        # Fast Retransmit
                        if expected_by_client < next_seq_num and expected_by_client not in acked_packets:
                            if expected_by_client not in missing_packet_reports: missing_packet_reports[
                                expected_by_client] = 0
                            missing_packet_reports[expected_by_client] += 1

                            if missing_packet_reports[expected_by_client] == FAST_RETRANSMIT_THRESHOLD:
                                print(f"[{new_port}] Fast Retransmit SEQ {expected_by_client}")
                                ssthresh = max(int(cwnd / 2), 2)
                                cwnd = ssthresh
                                congestion_state = "Fast Retransmit (CA)"  # עדכון סטטוס
                                handler_socket.sendto(all_packets[expected_by_client - 1], client_addr)
                                packet_timers[expected_by_client] = time.time()
                                missing_packet_reports[expected_by_client] = 0

                        if send_base <= ack_num < next_seq_num:
                            if ack_num not in acked_packets:
                                acked_packets.add(ack_num)
                                if ack_num in packet_timers:
                                    send_time = packet_timers[ack_num]
                                    del packet_timers[ack_num]
                                    SampleRTT = time.time() - send_time
                                    EstimatedRTT = (1.0 - ALPHA) * EstimatedRTT + ALPHA * SampleRTT
                                    DevRTT = (1.0 - BETA) * DevRTT + BETA * abs(SampleRTT - EstimatedRTT)
                                    TimeoutInterval = EstimatedRTT + 4.0 * DevRTT

                                if cwnd < ssthresh:
                                    cwnd += 1
                                    congestion_state = "SS"
                                else:
                                    cwnd += (1.0 / int(cwnd))
                                    congestion_state = "CA"

                                if ack_num in missing_packet_reports: del missing_packet_reports[ack_num]

                            while send_base in acked_packets:
                                acked_packets.remove(send_base)
                                send_base += 1

                except socket.timeout:
                    pass

                if send_base > total_packets:
                    transfer_in_progress = False

            # סיום
            SERVER_STATE[client_key]["state"] = "FINISHED 🏁"
            SERVER_STATE[client_key]["sent"] = total_packets

            # 5. סגירה
            handler_socket.settimeout(TimeoutInterval * 2)
            handler_socket.sendto(b'FIN', client_addr)
            data, _ = handler_socket.recvfrom(BUFFER_SIZE)
            if data == b'ACK':
                data, _ = handler_socket.recvfrom(BUFFER_SIZE)
                if data == b'FIN':
                    handler_socket.sendto(b'ACK', client_addr)

        except Exception as e:
            print(f"[{thread_name}]: Error: {e}")
            if client_key in SERVER_STATE:
                SERVER_STATE[client_key]["state"] = "ERROR ❌"

        # מחיקת הלקוח מהדשבורד אחרי כמה שניות (אופציונלי - כרגע משאיר שיראו שסיים)
        # time.sleep(5)
        # if client_key in SERVER_STATE: del SERVER_STATE[client_key]


# ---------------------------------
# שרת ראשי
# ---------------------------------
print("Starting Main Server...")

# הפעלת הדשבורד בתהליכון נפרד
dashboard_thread = threading.Thread(target=start_dashboard_server, daemon=True)
dashboard_thread.start()

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as welcome_socket:
    welcome_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    welcome_socket.bind((HOST, WELCOME_PORT))
    print(f"Main Server listening on UDP {HOST}:{WELCOME_PORT}")

    thread_count = 1
    while True:
        try:
            data, addr = welcome_socket.recvfrom(BUFFER_SIZE)
            if data == b'SYN':
                print(f"New SYN from {addr}")
                t = threading.Thread(target=handle_client_connection, args=(addr, welcome_socket),
                                     name=f"T-{thread_count}")
                t.start()
                thread_count += 1
        except Exception as e:
            print(f"Error: {e}")