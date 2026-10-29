"""J03-only synthetic HTTPS state upstream, never actual Finn acceptance evidence."""
import base64
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import ssl
import time

import jwt

if os.environ.get("J03_SYNTHETIC_AUTHORITY") != "1":
    raise RuntimeError("Isolated J03 fixture required")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        if (self.path != "/api/v1/identity/introspect"
                or self.headers.get("X-Service-Key-ID") != os.environ["IDENTITY_STATE_KEY_ID"]
                or not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + os.environ["IDENTITY_STATE_SECRET"])):
            status, result = 401, {"error": "invalid_service_credential"}
        else:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError
                body = json.loads(self.rfile.read(length))
                claims = jwt.decode(body["token"], base64.b64decode(os.environ["JWT_SECRET_KEY"]),
                                    algorithms=["HS256"], audience="jakeai-service", issuer="finnapigo")
                if claims["tid"] != body["tenant_id"]:
                    raise ValueError
                result = {k: claims[k] for k in ("contract_ver", "tid", "sub", "sid", "jti", "pwdver", "auth_epoch")}
                result.update(active=True, checked_at=int(time.time()), max_cache_seconds=15)
                status = 200
            except (ValueError, KeyError, jwt.PyJWTError):
                status, result = 401, {"active": False}
        data = json.dumps(result).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


server = ThreadingHTTPServer(("0.0.0.0", 8443), Handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.minimum_version = ssl.TLSVersion.TLSv1_2
context.load_cert_chain("/run/j03/cert.pem", "/run/j03/key.pem")
server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
