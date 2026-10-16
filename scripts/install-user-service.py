#!/usr/bin/env python3
"""Install a user-owned loopback service; no root privileges or credentials needed."""
import os, shutil, subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
unit=Path.home()/'.config/systemd/user/hotcrp-sim.service'
unit.parent.mkdir(parents=True,exist_ok=True)
def quote(s): return '"'+str(s).replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
unit.write_text(f'''[Unit]
Description=Local HotCRP Codex review simulator
After=network.target

[Service]
Type=simple
WorkingDirectory={str(root).replace('%','%%')}
Environment={quote('PATH='+os.environ['PATH'])}
Environment={quote('CODEX_BIN='+(shutil.which('codex') or 'codex'))}
ExecStart={quote(root/'scripts/start.sh')}
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
UMask=0077

[Install]
WantedBy=default.target
''')
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','enable','--now','hotcrp-sim.service'],check=True)
print('Started http://127.0.0.1:8765 (systemctl --user status hotcrp-sim)')
