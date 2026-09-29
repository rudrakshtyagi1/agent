"""Create local deployment secrets without displaying or overwriting them."""

import argparse
import json
import os
import re
import secrets

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--domain",
    required=True,
    help="DNS hostname; use localhost for local HTTP verification",
)
args = parser.parse_args()
if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}", args.domain):
    parser.error("Use a hostname, not a URL or port")
site = "http://localhost" if args.domain == "localhost" else args.domain
body = f"SITE_ADDRESS={site}\nPOSTGRES_PASSWORD={secrets.token_hex(32)}\nMONITOR_KEYS='{json.dumps({'portfolio': secrets.token_urlsafe(36)})}'\n"
if args.domain == "localhost":
    body += "HTTP_BIND=127.0.0.1\nHTTPS_BIND=127.0.0.1\n"
fd = os.open(".env.deploy", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write(body)
print(
    "Created private .env.deploy. Values were not printed. Keep this file outside Git."
)
