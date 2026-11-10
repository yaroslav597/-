"""Manage only the project's Linux SITL; keep its standard input open in WSL."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


STATE = Path.home() / '.local/state/aero-sitl'
BINARY = Path.home() / 'ardupilot/build/sitl/bin/arducopter'
DEFAULTS = Path.home() / 'ardupilot/Tools/autotest/default_params/copter.parm'
PID_FILE = STATE / 'sitl.pid'
INSTANCE = 0
SPEEDUP = 1


def status():
    try:
        pid = int(PID_FILE.read_text())
        args = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        running = args[0] == os.fsencode(BINARY) and b'--instance' in args and args[args.index(b'--instance') + 1] == str(INSTANCE).encode()
        return {'running': running, 'pid': pid if running else None}
    except (OSError, ValueError, IndexError):
        return {'running': False, 'pid': None}


def run():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'launcher.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Project SITL is already running in this distribution.')
        child = subprocess.Popen([
            str(BINARY), '--model', 'quad', '--home', '55.755,37.59,150,0',
            '--instance', str(INSTANCE), '--serial0', 'tcp:0', '--speedup', str(SPEEDUP),
            '--defaults', str(DEFAULTS),
        ], cwd=STATE, stdin=subprocess.PIPE)
        PID_FILE.write_text(str(child.pid))

        def stop(signum, frame):
            if child.poll() is None:
                child.terminate()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            return child.wait()
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait()
            PID_FILE.unlink(missing_ok=True)


def main():
    global STATE, PID_FILE, INSTANCE, SPEEDUP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'status', 'run'])
    parser.add_argument('--instance', type=int, choices=range(10), default=0)
    parser.add_argument('--speedup', type=int, choices=range(1, 11), default=1)
    args = parser.parse_args()
    INSTANCE, SPEEDUP = args.instance, args.speedup
    if INSTANCE:
        STATE = STATE.with_name(f'aero-sitl-test-{INSTANCE}')
        PID_FILE = STATE / 'sitl.pid'
    if args.action == 'check':
        if not os.access(BINARY, os.X_OK) or not DEFAULTS.is_file():
            raise SystemExit(f'Build ArduPilot SITL first: {BINARY}')
        print(json.dumps({'binary': str(BINARY), 'state': str(STATE)}))
    elif args.action == 'status':
        print(json.dumps(status()))
    else:
        sys.exit(run())


if __name__ == '__main__':
    main()
