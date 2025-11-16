import socket
import os
import time

# הגדרות השרת
HOST = '127.0.0.1'
PORT = 65432
BUFFER_SIZE = 1024
CHUNK_SIZE = 980
TIMEOUT = 2  # פסק זמן בשניות
WINDOW_SIZE = 4  # גודל החלון (N)

FILES_DIR = r"C:\Users\user\OneDrive\שולחן העבודה\לימודים\תקשורת\project\files"


def calculate_checksum(data):
    return sum(data)


print("Starting Go-Back-N server...")
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server_socket:
    server_socket.bind((HOST, PORT))
    print(f"Server is listening on {HOST}:{PORT}")

    while True:
        print("\nWaiting for a file request...")
        try:
            # שלב 1: המתנה לבקשה (זה עדיין חוסם, מטפלים בלקוח אחד כל פעם)
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

                # שלב 2: קריאת כל הקובץ לזיכרון והכנת כל החבילות מראש
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

                # שלב 3: אתחול משתני החלון של GBN
                send_base = 1
                next_seq_num = 1
                last_ack_time = time.time()  # זה יהיה הטיימר שלנו

                transfer_in_progress = True
                while transfer_in_progress:

                    # --- חלק השולח ---
                    # כל עוד החלון לא מלא, שלח עוד חבילות
                    while next_seq_num < send_base + WINDOW_SIZE and next_seq_num <= total_packets:
                        packet_to_send = all_packets[next_seq_num - 1]
                        server_socket.sendto(packet_to_send, addr)
                        print(f"Sent SEQ {next_seq_num}")
                        next_seq_num += 1

                    # --- חלק בודק הטיימר ---
                    if time.time() - last_ack_time > TIMEOUT:
                        print(f"!!! Timeout! Going back to N. Resending from {send_base}")
                        # "הולכים אחורה" ושולחים שוב את כל החלון
                        for i in range(send_base, next_seq_num):
                            print(f"Resending SEQ {i}")
                            server_socket.sendto(all_packets[i - 1], addr)
                        last_ack_time = time.time()  # אתחול הטיימר מחדש

                    # --- חלק מאזין ה-ACK (באופן לא-חוסם) ---
                    try:
                        server_socket.settimeout(0.01)  # אל תחסום, רק תבדוק אם הגיע משהו
                        ack_data, _ = server_socket.recvfrom(BUFFER_SIZE)
                        ack_message = ack_data.decode()

                        if ack_message.startswith("ACK|"):
                            ack_num = int(ack_message.split('|')[1])

                            # אם ה-ACK מקדם את הבסיס (ACK מצטבר)
                            if ack_num >= send_base:
                                send_base = ack_num + 1
                                print(f"Received ACK {ack_num}. Window base moved to {send_base}")
                                last_ack_time = time.time()  # אתחול הטיימר

                    except socket.timeout:
                        pass  # זה בסדר גמור, פשוט לא הגיע ACK ב-0.01 שניות האלה

                    # בדוק אם סיימנו
                    if send_base > total_packets:
                        transfer_in_progress = False

                # סוף הלולאה `while transfer_in_progress`
                print(f"Finished sending {filename}.")
                for _ in range(5):  # שלח END 5 פעמים כדי לוודא הגעה
                    server_socket.sendto(b'END', addr)
                    time.sleep(0.01)

                server_socket.settimeout(None)  # בטל פסק זמן

        except Exception as e:
            print(f"An error occurred: {e}")
            server_socket.settimeout(None)  # נקה טיימר במקרה של שגיאה