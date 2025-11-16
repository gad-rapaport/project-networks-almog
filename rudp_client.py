import socket
import os
import sys

# ---------------------------------
# הגדרות קבועות
# ---------------------------------
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 54321  # <--- שיניתי את הפורט
BUFFER_SIZE = 1024
DOWNLOAD_DIR = r"C:\Users\user\OneDrive\שולחן העבודה\לימודים\תקשורת\networks-projects\project"


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
        file_received_successfully = False

        try:
            with open(save_path, 'wb') as f:
                print(f"Waiting for data... Saving to {save_path}")

                while True:
                    packet, _ = client_socket.recvfrom(BUFFER_SIZE)

                    if packet == b'END':
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

                        if seq_num == expected_seq_num and received_checksum == expected_checksum:
                            sys.stdout.write(f'\rReceived SEQ {seq_num} (OK). Sending ACK {seq_num}')
                            sys.stdout.flush()
                            f.write(data)

                            ack_message = f"ACK|{seq_num}".encode()
                            client_socket.sendto(ack_message, server_address)
                            expected_seq_num += 1

                        else:
                            last_good_ack_num = expected_seq_num - 1
                            if received_checksum != expected_checksum:
                                print(
                                    f"\nReceived SEQ {seq_num} but CHECKSUM FAILED. Discarding. Resending ACK {last_good_ack_num}")
                            elif seq_num < expected_seq_num:
                                print(
                                    f"\nReceived DUPLICATE SEQ {seq_num}. Discarding. Resending ACK {last_good_ack_num}")
                            else:
                                print(
                                    f"\nReceived OUT-OF-ORDER SEQ {seq_num}. Discarding. Resending ACK {last_good_ack_num}")

                            ack_message = f"ACK|{last_good_ack_num}".encode()
                            client_socket.sendto(ack_message, server_address)

                    except (ValueError, IndexError):
                        print(f"\nError parsing packet. Ignoring.")

        except IOError as e:
            print(f"\nError writing to file: {e}")
            file_received_successfully = False
        except Exception as e:
            print(f"\nAn error occurred: {e}")
            file_received_successfully = False

        if file_received_successfully:
            print(f"Successfully downloaded and saved to {save_path}")
        else:
            print(f"File download failed for {filename}")
            if os.path.exists(save_path):
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