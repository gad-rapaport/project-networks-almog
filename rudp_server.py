import socket
import os
import time
import sys
import threading

# ---------------------------------
# הגדרות קבועות
# ---------------------------------
HOST = '127.0.0.1'
WELCOME_PORT = 54321
BUFFER_SIZE = 1024
CHUNK_SIZE = 980
TIMEOUT = 2
FILES_DIR = r"C:\Users\user\OneDrive\שולחן העבודה\לימודים\תקשורת\networks-projects\project\files"

# --- קבועים עבור RTT דינאמי ---
ALPHA = 0.125
BETA = 0.25
INITIAL_RTO = 1.0
FAST_RETRANSMIT_THRESHOLD = 3


# ---------------------------------
# פונקציות עזר (ללא שינוי)
# ---------------------------------
def calculate_checksum(data):
    return sum(data)


def print_progress_bar(iteration, total, prefix='Progress:', suffix='', length=50, fill='█'):
    percent = ("{0:.1f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()
    if iteration == total:
        sys.stdout.write('\n')
        sys.stdout.flush()


# ---------------------------------
# פונקציית הטיפול בלקוח (תרוץ ב-Thread נפרד)
# ---------------------------------
def handle_client_connection(client_addr, welcome_socket):
    """
    מנהל חיבור מלא (Handshake, Transfer, Close) מול לקוח יחיד.
    """

    thread_name = threading.current_thread().name

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handler_socket:
        handler_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        handler_socket.bind((HOST, 0))
        new_port = handler_socket.getsockname()[1]

        print(f"[{thread_name}]: New connection from {client_addr}. Assigning port {new_port}.")

        try:
            # --- 1. ביצוע Handshake (שלב SYN-ACK) ---
            handler_socket.settimeout(INITIAL_RTO * 2)
            welcome_socket.sendto(f"SYN-ACK|{new_port}".encode(), client_addr)

            # --- 2. קבלת ACK|REQ|... ---
            data, addr = handler_socket.recvfrom(BUFFER_SIZE)

            if addr != client_addr:
                print(f"[{thread_name}]: Handshake address mismatch. Aborting.")
                return

            # --- ##### התיקון כאן ##### ---
            data_str = data.decode()
            parts = data_str.split('|')

            # הפורמט הנכון הוא: ACK|REQ|filename|rwnd (סה"כ 4 חלקים)
            if len(parts) != 4 or parts[0] != 'ACK' or parts[1] != 'REQ':
                print(f"[{thread_name}]: Failed handshake (expected ACK|REQ|filename|rwnd). Got: {data_str}. Aborting.")
                return

            # קריאה נכונה של החלקים
            filename = parts[2]
            client_rwnd = int(parts[3])
            # --- ##### סוף התיקון ##### ---

            print(f"[{thread_name}]: Handshake complete. REQ for '{filename}'. Client rwnd={client_rwnd}")

            # --- 3. טיפול בבקשת הקובץ ---
            filepath = os.path.join(FILES_DIR, filename)
            if not os.path.exists(filepath):
                print(f"[{thread_name}]: File not found.")
                handler_socket.sendto(b'ERROR|File not found', client_addr)
                return

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
            print(f"[{thread_name}]: Total packets to send: {total_packets}")

            # --- 4. אתחול מנגנוני בקרה ---
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
            progress_prefix = f"[{thread_name} Port {new_port}]:"
            status_suffix = f" (cwnd={int(cwnd)}, rwnd={client_rwnd}, RTO={TimeoutInterval:.2f}s, state={congestion_state})"
            print_progress_bar(0, total_packets, prefix=progress_prefix, suffix=status_suffix)

            while transfer_in_progress:

                # --- חלק א': שליחת חבילות ---
                effective_window = min(int(cwnd), client_rwnd)

                while next_seq_num < send_base + effective_window and next_seq_num <= total_packets:
                    if next_seq_num not in packet_timers:
                        packet_to_send = all_packets[next_seq_num - 1]
                        handler_socket.sendto(packet_to_send, client_addr)
                        packet_timers[next_seq_num] = time.time()
                    next_seq_num += 1

                # --- חלק ב': בדיקת Timeout ---
                timed_out_packets = []
                for seq, start_time in packet_timers.items():
                    if time.time() - start_time > TimeoutInterval:
                        timed_out_packets.append(seq)

                for seq in timed_out_packets:
                    sys.stdout.write(f'\r{" " * 90}\r')
                    print(f"\n[{thread_name}]: !!! Timeout for SEQ {seq} (MD)! Resending...")

                    ssthresh = max(int(cwnd / 2), 2)
                    cwnd = 1.0
                    congestion_state = "SS"

                    handler_socket.sendto(all_packets[seq - 1], client_addr)
                    packet_timers[seq] = time.time()

                    status_suffix = f" (cwnd={int(cwnd)}, rwnd={client_rwnd}, RTO={TimeoutInterval:.2f}s, state={congestion_state})"
                    print_progress_bar(send_base - 1, total_packets, prefix=progress_prefix, suffix=status_suffix)
                    if seq in missing_packet_reports:
                        missing_packet_reports[seq] = 0

                # --- חלק ג': קליטת ACKs ---
                try:
                    handler_socket.settimeout(0.01)
                    ack_data, _ = handler_socket.recvfrom(BUFFER_SIZE)

                    parts = ack_data.decode().split('|')

                    if parts[0] == 'ACK' and len(parts) == 4:
                        ack_num = int(parts[1])
                        client_rwnd = int(parts[2])
                        expected_by_client = int(parts[3])

                        if expected_by_client < next_seq_num and expected_by_client not in acked_packets:
                            if expected_by_client not in missing_packet_reports:
                                missing_packet_reports[expected_by_client] = 0
                            missing_packet_reports[expected_by_client] += 1

                            if missing_packet_reports[expected_by_client] == FAST_RETRANSMIT_THRESHOLD:
                                sys.stdout.write(f'\r{" " * 90}\r')
                                print(f"\n[{thread_name}]: !!! Fast Retransmit for SEQ {expected_by_client} (MD)!")

                                ssthresh = max(int(cwnd / 2), 2)
                                cwnd = ssthresh
                                congestion_state = "CA"

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

                                if ack_num in missing_packet_reports:
                                    del missing_packet_reports[ack_num]

                            while send_base in acked_packets:
                                acked_packets.remove(send_base)
                                send_base += 1

                            status_suffix = f" (cwnd={cwnd:.1f}, rwnd={client_rwnd}, RTO={TimeoutInterval:.2f}s, state={congestion_state})"
                            print_progress_bar(send_base - 1, total_packets, prefix=progress_prefix,
                                               suffix=status_suffix)

                except socket.timeout:
                    pass

                # --- חלק ד': בדיקת סיום ---
                if send_base > total_packets:
                    transfer_in_progress = False

            print_progress_bar(total_packets, total_packets, prefix=progress_prefix, suffix=" Complete!")

            # --- 5. ביצוע Handshake סגירה ---
            print(f"[{thread_name}]: File sent. Starting 4-way close handshake...")
            handler_socket.settimeout(TimeoutInterval * 2)
            handler_socket.sendto(b'FIN', client_addr)
            data, _ = handler_socket.recvfrom(BUFFER_SIZE)
            if data == b'ACK':
                data, _ = handler_socket.recvfrom(BUFFER_SIZE)
                if data == b'FIN':
                    handler_socket.sendto(b'ACK', client_addr)
                    print(f"[{thread_name}]: 4-way close complete. Connection closed.")

        except socket.timeout:
            print(f"[{thread_name}]: Client {client_addr} timed out. Closing thread.")
        except Exception as e:
            print(f"[{thread_name}]: An error occurred: {e}")


# ---------------------------------
# הלולאה הראשית של השרת - "פקיד הקבלה"
# ---------------------------------
print("Starting Main Server Thread (Welcome Socket)...")

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as welcome_socket:
    welcome_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    welcome_socket.bind((HOST, WELCOME_PORT))
    print(f"Main Server listening on {HOST}:{WELCOME_PORT}")

    thread_count = 1
    while True:
        try:
            data, addr = welcome_socket.recvfrom(BUFFER_SIZE)

            if data == b'SYN':
                print(f"\n[Main Server]: Received new SYN from {addr}. Spawning Thread-{thread_count}...")
                client_thread = threading.Thread(target=handle_client_connection,
                                                 args=(addr, welcome_socket),
                                                 name=f"Thread-{thread_count}")
                client_thread.start()
                thread_count += 1

            else:
                print(f"\n[Main Server]: Received stray data on welcome port from {addr}. Ignoring.")

        except Exception as e:
            print(f"[Main Server]: An error occurred: {e}")