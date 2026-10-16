#!/usr/bin/env python3
"""Generate local credentials and SQL for a restricted MariaDB application user."""
import json, os, secrets
from pathlib import Path
root = Path(__file__).resolve().parents[1]
data = root / 'data'
data.mkdir(mode=0o700, exist_ok=True)
os.chmod(data, 0o700)
p = data / 'database.json'
if not p.exists():
    p.write_text(json.dumps({'user': 'hcsim_local', 'password': secrets.token_hex(32)}))
    p.chmod(0o600)
key = data / 'proxy-key'
if not key.exists():
    key.write_text(secrets.token_hex(32))
    key.chmod(0o600)
s = json.loads(p.read_text())
assert s['user'] == 'hcsim_local' and all(c in '0123456789abcdef' for c in s['password'])
sql = data / 'bootstrap.sql'
sql.write_text(f"CREATE USER IF NOT EXISTS 'hcsim_local'@'localhost' IDENTIFIED BY '{s['password']}';\n"
               f"ALTER USER 'hcsim_local'@'localhost' IDENTIFIED BY '{s['password']}';\n"
               "GRANT ALL PRIVILEGES ON `hcsim\\_%`.* TO 'hcsim_local'@'localhost';\n")
sql.chmod(0o600)
print('Local credentials prepared (data/, mode 0600).')
