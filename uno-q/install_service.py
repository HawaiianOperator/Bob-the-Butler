#!/usr/bin/env python3
"""Run once on UNO Q: sudo python3 install_service.py. No third-party packages."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import shutil
import hashlib

SERVICE = 'bob-butler.service'
APP_DIR = Path('/opt/bob-the-butler')
UNIT_PATH = Path('/etc/systemd/system') / SERVICE


def atomic_write(path, data):
    if path.is_symlink():
        raise RuntimeError(f'Refusing to replace a symbolic link: {path}')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            os.fchmod(handle.fileno(), 0o644)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def ready():
    try:
        if subprocess.run(['systemctl', 'is-active', '--quiet', SERVICE]).returncode:
            return False
        pid = subprocess.run(['systemctl', 'show', '--property=MainPID', '--value', SERVICE],
                             check=True, text=True, capture_output=True).stdout.strip()
        with socket.create_connection(('127.0.0.1', 8765), timeout=0.5) as connection:
            connection.sendall(b'{"type":"hello","protocol":1,"nonce":"boot-check"}\n')
            pending = bytearray()
            while b'\n' not in pending and len(pending) < 8192:
                data = connection.recv(1024)
                if not data:
                    return False
                pending.extend(data)
            reply = json.loads(pending.split(b'\n', 1)[0])
            return (reply.get('type') == 'hello_ack' and reply.get('nonce') == 'boot-check'
                    and reply.get('device') == 'device-companion' and reply.get('protocol') == 1
                    and int(pid) > 0 and reply.get('process_id') == int(pid))
    except (OSError, ValueError, subprocess.CalledProcessError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Show the plan without changing files or starting services.')
    parser.add_argument('--with-ai', action='store_true', help='Install the staged quantized model and pinned runtime from /home/arduino/bob-ai.')
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    script = (source / 'bob_service.py').read_bytes()
    unit = (source / SERVICE).read_bytes()
    compile(script, 'bob_service.py', 'exec')  # Syntax validation, without running the receiver.
    print(f'Install receiver: {APP_DIR / "bob_service.py"}')
    print(f'Install boot unit: {UNIT_PATH}')
    print('Enable at boot and restart the receiver now.')
    if args.dry_run:
        print('Dry run only: no files changed and no service started.')
        return
    if sys.platform != 'linux' or not hasattr(os, 'geteuid') or os.geteuid() != 0:
        parser.error('Run this on the UNO Q with: sudo python3 install_service.py')
    if not Path('/run/systemd/system').is_dir() or not Path('/usr/bin/python3').is_file():
        parser.error('This installer requires Debian/systemd and /usr/bin/python3.')
    if APP_DIR.is_symlink():
        raise RuntimeError(f'Refusing to install into a symbolic link: {APP_DIR}')
    APP_DIR.mkdir(mode=0o755, parents=True, exist_ok=True)
    os.chmod(APP_DIR, 0o755)
    atomic_write(APP_DIR / 'bob_service.py', script)
    (APP_DIR / 'ai').mkdir(exist_ok=True)
    for name in ('__init__.py', 'planner.py', 'tool_plan.py', 'search_workflow.py'):
        atomic_write(APP_DIR / 'ai' / name, (source / 'ai' / name).read_bytes())
    if args.with_ai:
        staging = Path('/home/arduino/bob-ai')
        model = staging / 'bob-q4_k_m.gguf'
        manifest = json.loads((staging / 'bob-model-manifest.json').read_text())
        with model.open('rb') as handle:
            if handle.read(4) != b'GGUF':
                raise RuntimeError('Model is not GGUF.')
            handle.seek(0)
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        if digest != manifest['sha256']:
            raise RuntimeError('Model checksum does not match the conversion manifest.')
        (APP_DIR / 'model').mkdir(exist_ok=True)
        shutil.copy2(model, APP_DIR / 'model' / model.name)
        os.chmod(APP_DIR / 'model' / model.name, 0o644)
        atomic_write(APP_DIR / 'model' / 'manifest.json', (staging / 'bob-model-manifest.json').read_bytes())
        shutil.copytree(staging / 'runtime' / 'llama-b11869', APP_DIR / 'runtime', symlinks=True, dirs_exist_ok=True)
        atomic_write(Path('/etc/systemd/system/bob-planner.service'), (source / 'bob-planner.service').read_bytes())
    atomic_write(UNIT_PATH, unit)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    if args.with_ai:
        subprocess.run(['systemctl', 'enable', '--now', 'bob-planner.service'], check=True)
    subprocess.run(['systemctl', 'enable', SERVICE], check=True)
    subprocess.run(['systemctl', 'restart', SERVICE], check=True)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if ready():
            print('Bob is running and enabled for future boots. You can close this terminal.')
            print('Status: sudo systemctl status bob-butler --no-pager')
            print('Logs:   sudo journalctl -u bob-butler -f')
            return
        time.sleep(0.4)
    raise RuntimeError('Receiver did not become ready. Stop any manually started receiver using port 8765, then check: sudo journalctl -u bob-butler -n 40 --no-pager')


if __name__ == '__main__':
    main()
