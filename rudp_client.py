import socket
import os

# הגדרות הלקוח
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 65432
BUFFER_SIZE = 1024

DOWNLOAD_DIR = r"C:\Users\user\OneDrive\שולחן העבודה\לימודים\תקשורת\project"


def calculate_checksum(data):
    return sum(data)


with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client_socket:
    filename = input("Enter the filename to request (e.g., parsha.txt): ")
    if not filename:
        filename = "parsha.txt"

    request_message = f"REQ|{filename}".encode()
    server_address = (SERVER_HOST, SERVER_PORT)
    client_socket.sendto(request_message, server_address)
    print(f"Sent request for file: {filename}")

    save_path = os.path.join(DOWNLOAD_DIR, f"received_{filename}")

    # זה המשתנה היחיד שהלקוח צריך לעקוב אחריו ב-GBN
    expected_seq_num = 1

    try:
        with open(save_path, 'wb') as f:
            print(f"Waiting for data... Saving to {save_path}")

            while True:
                packet, _ = client_socket.recvfrom(BUFFER_SIZE)

                if packet == b'END':
                    print("Received END signal. File transfer complete.")
                    break

                if packet.startswith(b'ERROR|'):
                    print(f"Server error: {packet.decode()}")
                    break

                try:
                    parts = packet.split(b'|', 3)
                    if len(parts) < 4 or parts[0] != b'SEQ':
                        print(f"Received malformed packet. Ignoring.")
                        continue

                    seq_num = int(parts[1].decode())
                    received_checksum = int(parts[2].decode())
                    data = parts[3]

                    expected_checksum = calculate_checksum(data)

                    # --- לוגיקת הליבה של GBN Receiver ---

                    # 1. בדיקה אם החבילה היא *בדיוק* זו שציפינו לה (בסדר, ותקינה)
                    if seq_num == expected_seq_num and received_checksum == expected_checksum:
                        print(f"Received SEQ {seq_num} (OK). Writing to file. Sending ACK {seq_num}")
                        f.write(data)

                        # שלח ACK עבור החבילה שקיבלת
                        ack_message = f"ACK|{seq_num}".encode()
                        client_socket.sendto(ack_message, server_address)

                        # קדם את המספר המצופה
                        expected_seq_num += 1

                    # 2. אם החבילה *אינה* זו שציפינו לה (פגומה, כפולה, או לא בסדר)
                    else:
                        if received_checksum != expected_checksum:
                            print(f"Received SEQ {seq_num} but CHECKSUM FAILED. Discarding.")
                        elif seq_num < expected_seq_num:
                            print(f"Received DUPLICATE SEQ {seq_num}. Discarding.")
                        else:  # seq_num > expected_seq_num
                            print(f"Received OUT-OF-ORDER SEQ {seq_num} (expected {expected_seq_num}). Discarding.")

                        # --- הפעולה הקריטית ב-GBN ---
                        # שלח ACK עבור החבילה האחרונה *שכן קיבלת בסדר*
                        # (אם עוד לא קיבלנו כלום, expected_seq_num-1 יהיה 0)
                        last_good_ack_num = expected_seq_num - 1
                        print(f"Resending last good ACK: {last_good_ack_num}")
                        ack_message = f"ACK|{last_good_ack_num}".encode()
                        client_socket.sendto(ack_message, server_address)

                except (ValueError, IndexError):
                    print(f"Error parsing packet. Ignoring.")

    except IOError as e:
        print(f"Error writing to file: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

print("Client shutting down.")