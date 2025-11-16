import socket
import os
import time
import sys

# --------------------------------
# הגדרות קבועות
# --------------------------------
HOST = '127.0.0.1'
PORT = 65432
BUFFER_SIZE = 1024
CHUNK_SIZE = 980
TIMEOUT = 2
WINDOW_SIZE = 4
# עדכון הנתיב כפי שביקשת
FILES_DIR = r"C:\Users\user\OneDrive\שולחן העבודה\לימודים\תקשורת\networks-projects\project\files"


# ---------------------------------
# פונקציות עזר
# ---------------------------------
def calculate_checksum(data):
    """ מחשב סכום בדיקה פשוט על ידי סכום ערכי הבתים. """
    return sum(data)


def print_progress_bar(iteration, total, prefix='Progress:', suffix='Complete', length=50, fill='█'):
    """
    פונקציית עזר להדפסת פס התקדמות המתעדכן באותה שורה.
    """
    percent = ("{0:.1f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    # \r (Carriage Return) מחזיר את הסמן לתחילת השורה
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()
    if iteration == total:
        sys.stdout.write('\n')
        sys.stdout.flush()


# ---------------------------------
# הלוגיקה הראשית של השרת
# ---------------------------------
print("Starting Go-Back-N server...")

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
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

                # שלב 2: הכנת כל החבילות מראש
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

                # שלב 3: אתחול מנגנון Go-Back-N
                send_base = 1
                next_seq_num = 1
                last_ack_time = time.time()
                transfer_in_progress = True

                # הדפסה ראשונית של פס ההתקדמות
                print_progress_bar(0, total_packets)

                while transfer_in_progress:

                    # --- חלק א': שליחת חבילות ---
                    while next_seq_num < send_base + WINDOW_SIZE and next_seq_num <= total_packets:
                        packet_to_send = all_packets[next_seq_num - 1]
                        server_socket.sendto(packet_to_send, addr)
                        # הסרנו את ה-print שהיה פה כדי למנוע הצפה
                        next_seq_num += 1

                    # --- חלק ב': בדיקת פסק זמן (Timeout) ---
                    if time.time() - last_ack_time > TIMEOUT:
                        print(f"\n!!! Timeout! Resending from {send_base}")

                        # "הולכים אחורה" ושולחים שוב את כל החלון
                        for i in range(send_base, next_seq_num):
                            server_socket.sendto(all_packets[i - 1], addr)
                        last_ack_time = time.time()
                        print_progress_bar(send_base - 1, total_packets)  # עדכן את הפס חזרה

                    # --- חלק ג': קליטת ACKs (באופן לא-חוסם) ---
                    try:
                        server_socket.settimeout(0.01)
                        ack_data, _ = server_socket.recvfrom(BUFFER_SIZE)
                        ack_message = ack_data.decode()

                        if ack_message.startswith("ACK|"):
                            ack_num = int(ack_message.split('|')[1])

                            if ack_num >= send_base:
                                send_base = ack_num + 1
                                # עדכון פס ההתקדמות במקום הדפסה
                                print_progress_bar(send_base - 1, total_packets)
                                last_ack_time = time.time()

                    except socket.timeout:
                        pass

                    # --- חלק ד': בדיקת סיום ---
                    if send_base > total_packets:
                        transfer_in_progress = False

                # סיום העברה
                print_progress_bar(total_packets, total_packets)  # סיום הפס (100%)
                print(f"Finished sending {filename}.")
                for _ in range(5):
                    server_socket.sendto(b'END', addr)
                    time.sleep(0.01)

                server_socket.settimeout(None)

        except Exception as e:
            print(f"An error occurred: {e}")
            server_socket.settimeout(None)