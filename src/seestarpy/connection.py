import json
import socket

DEFAULT_PORT = 4700
DEFAULT_IP = "192.168.1.243"
VERBOSE_LEVEL = 1


def send_command(params):
    if not IS_SEESTAR_ONLINE:
        return {"error": "Seestar is not online"}

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((DEFAULT_IP, DEFAULT_PORT))

    # params = {"method":"scope_park","params":{"equ_mode":self.is_EQ_mode}}
    cmd = {"id": 1}
    cmd.update(params)

    message = json.dumps(cmd) + "\r\n"
    if VERBOSE_LEVEL >= 1: print(f"\nSending: {message.strip()}")
    s.sendall(message.encode())

    # Read until we get a complete message (ends with \r\n)
    response = ""
    while "\r\n" not in response:
        chunk = s.recv(4096).decode("utf-8")
        if not chunk:
            break
        response += chunk

    if VERBOSE_LEVEL >= 1: print(f"\nRecieved: {response}")
    s.close()

    try:
        parsed = json.loads(response.split("\r\n")[0])
        method = parsed.get("method")
        result = parsed.get("result")
        code = parsed.get("code")
        error = parsed.get("error")

        if VERBOSE_LEVEL >= 2:
            print("\n✅ Response:")
            print(f"  method: {method}")
            print(f"  result: {json.dumps(result, indent=2)}")
            print(f"  code  : {code}")
            print(f"  error : {error}")
        return parsed

    except json.JSONDecodeError:
        print("⚠️ Could not parse response as JSON.")
        print("Raw response:\n", response)

        return response


def is_port_open(ip=DEFAULT_IP, port=DEFAULT_PORT, timeout=2):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((ip, port))
            return True
        except (socket.timeout, socket.error):
            return False


IS_SEESTAR_ONLINE = is_port_open()
