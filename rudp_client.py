import socket
import os
import sys

# ---------------------------------
# הגדרות קבועות
# ---------------------------------
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 54321
BUFFER_SIZE = 1024
DOWNLOAD_DIR = r"C:\Users\user\OneDrive\שולחן העבודה\לימודים\תקשורת\networks-projects\project"
WINDOW_SIZE = 32  # גודל חלון הקבלה בבאפר


# ---------------------------------
# פונקציות עזר
# ---------------------------------
def calculate_checksum(data):
    """ מחשב סכום בדיקה פשוט על ידי סכום ערכי הבתים. """
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

        request_message = f"REQ|{filename}".encode()
        server_address = (SERVER_HOST, SERVER_PORT)
        client_socket.sendto(request_message, server_address)
        print(f"Sent request for file: {filename}")

        save_path = os.path.join(DOWNLOAD_DIR, f"received_{filename}")
        expected_seq_num = 1
        receive_buffer = {}
        file_received_successfully = False

        try:
            with open(save_path, 'wb') as f:
                print(f"Waiting for data... Saving to {save_path}")

                while True:
                    packet, _ = client_socket.recvfrom(BUFFER_SIZE)

                    if packet == b'END':
                        if expected_seq_num == 1:
                            print("\nReceived stray END packet. Ignoring.")
                            continue
                        else:
                            print("\nReceived END signal. File transfer complete.")
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

                        if expected_seq_num <= seq_num < expected_seq_num + WINDOW_SIZE:

                            # ##### שונה: הדפסה נקייה באותה שורה #####
                            sys.stdout.write(
                                f'\rReceived packet: {seq_num} | Buffering: {len(receive_buffer)} | Next needed: {expected_seq_num}')
                            sys.stdout.flush()

                            ack_message = f"ACK|{seq_num}".encode()
                            client_socket.sendto(ack_message, server_address)

                            if seq_num == expected_seq_num:
                                f.write(data)
                                expected_seq_num += 1

                                while expected_seq_num in receive_buffer:
                                    f.write(receive_buffer[expected_seq_num])
                                    del receive_buffer[expected_seq_num]
                                    expected_seq_num += 1

                            else:  # החבילה לא בסדר, אבל תקינה
                                if seq_num not in receive_buffer:
                                    receive_buffer[seq_num] = data

                        elif seq_num < expected_seq_num:
                            # חבילה ישנה (כפילות)
                            ack_message = f"ACK|{seq_num}".encode()
                            client_socket.sendto(ack_message, server_address)

                        else:
                            # חבילה רחוקה מדי מחוץ לחלון
                            print(f"\nReceived packet {seq_num} (too far ahead). Discarding.")

                    except (ValueError, IndexError):
                        print(f"\nError parsing packet. Ignoring.")

        except IOError as e:
            print(f"\nError writing to file: {e}")
            file_received_successfully = False
        except Exception as e:
            print(f"\nAn error occurred: {e}")
            file_received_successfully = False

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