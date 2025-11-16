import socket
import os
import sys

# ---------------------------------
# הגדרות קבועות
# ---------------------------------
SERVER_HOST = '127.0.0.1'
WELCOME_PORT = 54321
BUFFER_SIZE = 1024
DOWNLOAD_DIR = r"C:\Users\user\OneDrive\שולחן העבודה\לימודים\תקשורת\networks-projects\project"
CLIENT_MAX_BUFFER = 32
CLIENT_TIMEOUT = 5


# ---------------------------------
# פונקציות עזר
# ---------------------------------
def calculate_checksum(data):
    return sum(data)


# ---------------------------------
# הלוגיקה הראשית של הלקוח
# ---------------------------------

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_socket:
    while True:
        filename = input("\nEnter the filename to request (e.g., parsha.txt): ")
        if not filename:
            print("No filename entered. Exiting.")
            break

        expected_seq_num = 1
        receive_buffer = {}
        file_received_successfully = False
        server_handler_address = None

        try:
            # --- 1. ביצוע Handshake פתיחה ---
            print(f"Sending SYN to {SERVER_HOST}:{WELCOME_PORT}...")
            welcome_address = (SERVER_HOST, WELCOME_PORT)
            client_socket.sendto(b'SYN', welcome_address)

            client_socket.settimeout(CLIENT_TIMEOUT)
            handshake_success = False

            while not handshake_success:
                try:
                    port_message, _ = client_socket.recvfrom(BUFFER_SIZE)

                    if port_message.decode().startswith("SYN-ACK|"):
                        new_port = int(port_message.decode().split('|')[1])
                        server_handler_address = (SERVER_HOST, new_port)
                        print(f"Handshake OK. Server assigned port {new_port}.")
                        handshake_success = True

                    else:
                        print(f"Received stray packet while waiting for SYN-ACK. Ignoring.")

                except socket.timeout:
                    print("Server did not respond to SYN. Aborting.")
                    break

            if not handshake_success:
                client_socket.settimeout(None)  # נקה פסק זמן
                continue

            client_socket.settimeout(None)  # בטל פסק זמן כללי

            # --- שלב 3: שלח ACK + REQ + RWND לפורט החדש ---
            client_rwnd = CLIENT_MAX_BUFFER - len(receive_buffer)
            # ##### שונה: פורמט ההודעה שונתה ל-ACK|REQ|file|rwnd #####
            request_message = f"ACK|REQ|{filename}|{client_rwnd}".encode()
            client_socket.sendto(request_message, server_handler_address)

            # --- 2. לוגיקת קבלת קובץ (SR) ---
            save_path = os.path.join(DOWNLOAD_DIR, f"received_{filename}")
            with open(save_path, 'wb') as f:
                print(f"Waiting for data on port {new_port}... Saving to {save_path}")

                while True:
                    packet, _ = client_socket.recvfrom(BUFFER_SIZE)

                    # --- 3. לוגיקת Handshake סגירה ---
                    if packet == b'FIN':
                        print("\nReceived FIN from server. Acknowledging and closing.")
                        client_socket.sendto(b'ACK', server_handler_address)
                        client_socket.sendto(b'FIN', server_handler_address)
                        try:
                            client_socket.settimeout(2.0)
                            packet, _ = client_socket.recvfrom(BUFFER_SIZE)
                            if packet == b'ACK':
                                print("Final ACK received. Connection closed cleanly.")
                        except socket.timeout:
                            print("Warning: Did not receive final ACK, but closing anyway.")

                        file_received_successfully = True
                        break

                    if packet.startswith(b'ERROR|'):
                        print(f"\nServer error: {packet.decode()}")
                        file_received_successfully = False
                        break

                    try:
                        parts = packet.split(b'|', 3)
                        if len(parts) < 4 or parts[0] != b'SEQ':
                            print(f"\nReceived malformed packet. Ignoring.")
                            continue

                        seq_num = int(parts[1].decode())
                        received_checksum = int(parts[2].decode())
                        data = parts[3]
                        expected_checksum = calculate_checksum(data)

                        if received_checksum != expected_checksum:
                            print(f"\nReceived SEQ {seq_num} but CHECKSUM FAILED. Discarding.")
                            continue

                            # --- חישוב rwnd ---
                        client_rwnd = CLIENT_MAX_BUFFER - len(receive_buffer)

                        # ##### שונה: פורמט ACK חדש (עם 4 חלקים) #####
                        ack_to_send = -1

                        if expected_seq_num <= seq_num < expected_seq_num + CLIENT_MAX_BUFFER:
                            sys.stdout.write(
                                f'\rGot: {seq_num} | Need: {expected_seq_num} | Buf: {len(receive_buffer)} | Free: {client_rwnd} ')
                            sys.stdout.flush()
                            ack_to_send = seq_num  # אשר את מה שקיבלת

                            if seq_num == expected_seq_num:
                                f.write(data)
                                expected_seq_num += 1

                                while expected_seq_num in receive_buffer:
                                    f.write(receive_buffer[expected_seq_num])
                                    del receive_buffer[expected_seq_num]
                                    expected_seq_num += 1
                            else:
                                if seq_num not in receive_buffer and len(receive_buffer) < CLIENT_MAX_BUFFER:
                                    receive_buffer[seq_num] = data
                                elif len(receive_buffer) >= CLIENT_MAX_BUFFER:
                                    print(f"\nClient buffer full! Discarding packet {seq_num}")

                        elif seq_num < expected_seq_num:
                            # חבילה ישנה (כפילות)
                            ack_to_send = seq_num  # אשר שוב
                        else:
                            print(f"\nReceived packet {seq_num} (out of window). Discarding.")

                        # שלח ACK אם צריך
                        if ack_to_send != -1:
                            # הפורמט החדש כולל את expected_seq_num
                            ack_message = f"ACK|{ack_to_send}|{client_rwnd}|{expected_seq_num}".encode()
                            client_socket.sendto(ack_message, server_handler_address)

                    except (ValueError, IndexError):
                        print(f"\nError parsing packet. Ignoring.")

        except socket.timeout:
            print("\nConnection timed out. Aborting.")
            file_received_successfully = False
        except IOError as e:
            print(f"\nError writing to file: {e}")
            file_received_successfully = False
        except Exception as e:
            print(f"\nAn error occurred: {e}")
            file_received_successfully = False
        finally:
            client_socket.settimeout(None)

            # --- 4. ניקוי ושאלה להמשך ---
        if file_received_successfully:
            print(f"\nSuccessfully downloaded and saved to {save_path}")
        else:
            print(f"\nFile download failed for {filename}")
            if os.path.exists(save_path) and not file_received_successfully:
                try:
                    os.remove(save_path)
                    print(f"Removed partial file: {save_path}")
                except OSError as e:
                    print(f"Error removing partial file: {e}")

        while True:
            choice = input("\nDo you want to download another file? (yes/no): ").strip().lower()
            if choice in ('yes', 'y'):
                break
            elif choice in ('no', 'n'):
                break
            else:
                print("Invalid input. Please enter 'yes' or 'no'.")

        if choice in ('no', 'n'):
            break

print("\nClient shutting down. Goodbye!")