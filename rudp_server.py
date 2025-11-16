import socket
import os
import time
import sys

# ---------------------------------
# הגדרות קבועות
# ---------------------------------
HOST = '127.0.0.1'
PORT = 54321
BUFFER_SIZE = 1024
CHUNK_SIZE = 980
TIMEOUT = 2
FILES_DIR = r"C:\Users\user\OneDrive\שולחן העבודה\לימודים\תקשורת\networks-projects\project\files"


# ---------------------------------
# פונקציות עזר
# ---------------------------------
def calculate_checksum(data):
    """ מחשב סכום בדיקה פשוט על ידי סכום ערכי הבתים. """
    return sum(data)


def print_progress_bar(iteration, total, prefix='Progress:', suffix='', length=50, fill='█'):
    """
    ##### שונה: הפונקציה מקבלת עכשיו פרמטר 'suffix' #####
    כדי להציג מידע דינמי כמו cwnd באותה שורה.
    """
    percent = ("{0:.1f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    # הדפסה עם \r גורמת לכתיבה מחדש באותה שורה
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()
    if iteration == total:
        sys.stdout.write('\n')
        sys.stdout.flush()


# ---------------------------------
# הלוגיקה הראשית של השרת
# ---------------------------------
print("Starting Ultimate RUDP server (SR + Congestion Control)...")

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    print(f"Server is listening on {HOST}:{PORT}")

    while True:
        print("\n" + "=" * 30)
        print("Waiting for a new file request...")

        try:
            data, addr = server_socket.recvfrom(BUFFER_SIZE)
            request = data.decode()
            print(f"Received request from {addr}: {request}")

            if request.startswith("REQ|"):
                filename = request.split('|')[1]
                filepath = os.path.join(FILES_DIR, filename)

                if not os.path.exists(filepath):
                    print(f"File not found: {filename}")
                    server_socket.sendto(b'ERROR|File not found', addr)
                    continue

                print(f"File '{filename}' found. Preparing chunks...")

                all_packets = []
                seq_num = 1
                with open(filepath, 'rb') as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        checksum = calculate_checksum(chunk)
                        packet = f"SEQ|{seq_num}|{checksum}|".encode() + chunk
                        all_packets.append(packet)
                        seq_num += 1

                total_packets = len(all_packets)
                print(f"Total packets to send: {total_packets}")

                # שלב 3: אתחול מנגנון SR + בקרת גודש
                send_base = 1
                next_seq_num = 1
                packet_timers = {}
                acked_packets = set()

                cwnd = 1.0
                ssthresh = 16
                congestion_state = "SS"  # (Slow Start)

                transfer_in_progress = True

                # הכנת מחרוזת הסטטוס הראשונית
                status_suffix = f" (cwnd={int(cwnd)}, ssthresh={ssthresh}, state={congestion_state})"
                print_progress_bar(0, total_packets, suffix=status_suffix)

                while transfer_in_progress:

                    # --- חלק א': שליחת חבילות (מילוי החלון) ---
                    while next_seq_num < send_base + int(cwnd) and next_seq_num <= total_packets:
                        if next_seq_num not in packet_timers:
                            packet_to_send = all_packets[next_seq_num - 1]
                            server_socket.sendto(packet_to_send, addr)
                            packet_timers[next_seq_num] = time.time()
                        next_seq_num += 1

                    # --- חלק ב': בדיקת Timeout (עבור *כל* חבילה בחלון) ---
                    timed_out_packets = []
                    for seq, start_time in packet_timers.items():
                        if time.time() - start_time > TIMEOUT:
                            timed_out_packets.append(seq)

                    for seq in timed_out_packets:
                        print(f"\n!!! Timeout for SEQ {seq} (MD)! Resending...")

                        ssthresh = max(int(cwnd / 2), 2)
                        cwnd = 1.0
                        congestion_state = "SS"  # חזרה ל-Slow Start

                        # שלח שוב *רק* את החבילה שפג לה הזמן
                        server_socket.sendto(all_packets[seq - 1], addr)
                        packet_timers[seq] = time.time()  # אתחל את הטיימר שלה

                        # עדכן את הסטטוס בפס ההתקדמות
                        status_suffix = f" (cwnd={int(cwnd)}, ssthresh={ssthresh}, state={congestion_state})"
                        print_progress_bar(send_base - 1, total_packets, suffix=status_suffix)

                    # --- חלק ג': קליטת ACKs (באופן לא-חוסם) ---
                    try:
                        server_socket.settimeout(0.01)
                        ack_data, _ = server_socket.recvfrom(BUFFER_SIZE)
                        ack_message = ack_data.decode()

                        if ack_message.startswith("ACK|"):
                            ack_num = int(ack_message.split('|')[1])

                            if send_base <= ack_num < next_seq_num:
                                if ack_num not in acked_packets:
                                    # --- ACK חדש (המסלול השמח: הגדלת החלון) ---
                                    acked_packets.add(ack_num)
                                    if ack_num in packet_timers:
                                        del packet_timers[ack_num]

                                    if cwnd < ssthresh:
                                        cwnd += 1
                                        congestion_state = "SS"
                                    else:
                                        cwnd += (1.0 / int(cwnd))
                                        congestion_state = "CA"  # (Congestion Avoidance)

                                # --- לוגיקת הזזת החלון של SR ---
                                while send_base in acked_packets:
                                    acked_packets.remove(send_base)
                                    send_base += 1

                                # ##### שונה: עדכון הפס והסטטוס באותה שורה #####
                                status_suffix = f" (cwnd={cwnd:.1f}, ssthresh={ssthresh}, state={congestion_state})"
                                print_progress_bar(send_base - 1, total_packets, suffix=status_suffix)

                    except socket.timeout:
                        pass  # זהו מצב תקין, אין ACK כרגע

                    # --- חלק ד': בדיקת סיום ---
                    if send_base > total_packets:
                        transfer_in_progress = False

                # סיום העברה
                print_progress_bar(total_packets, total_packets, suffix=" Complete!")
                print(f"Finished sending {filename}.")
                for _ in range(5):
                    server_socket.sendto(b'END', addr)
                    time.sleep(0.01)

                server_socket.settimeout(None)

        except Exception as e:
            print(f"An error occurred: {e}")
            server_socket.settimeout(None)