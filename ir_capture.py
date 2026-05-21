#!/usr/bin/env python3
"""
ir_capture.py  —  Capture IR signals from Arduino, replay them,
                   and save each working one individually with a user-given name.

Usage:
    python ir_capture.py [--port COM3] [--baud 115200] [--reps 3]
"""

import serial
import serial.tools.list_ports
import json
import time
import argparse
import sys
import os
import threading
from datetime import datetime

# ── colour helpers ───────────────────────────────────────────────────────────
def c(text, code): return f"\033[{code}m{text}\033[0m"
def green(t):  return c(t, "92")
def yellow(t): return c(t, "93")
def red(t):    return c(t, "91")
def cyan(t):   return c(t, "96")
def bold(t):   return c(t, "1")
def dim(t):    return c(t, "2")

BANNER = f"""
{cyan('━'*52)}
  {bold('IR Capture & Save')}  —  Arduino serial bridge
{cyan('━'*52)}
"""

SAVE_DIR = "ir_saved"

# ── serial helpers ────────────────────────────────────────────────────────────
def auto_detect_port():
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if any(k in desc for k in ("arduino", "ch340", "cp210", "ftdi", "usb serial")):
            return p.device
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return ports[0] if ports else None

def open_serial(port, baud):
    ser = serial.Serial(port, baud, timeout=1)
    time.sleep(2)
    ser.reset_input_buffer()
    return ser

def send(ser, cmd):
    ser.write((cmd + "\n").encode())

def read_line(ser, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = ser.readline().decode(errors="replace").strip()
        if line:
            return line
    return ""

def wait_for_ready(ser):
    deadline = time.time() + 5
    while time.time() < deadline:
        line = ser.readline().decode(errors="replace").strip()
        if line == "READY":
            return True
    return False

# ── signal parsing ────────────────────────────────────────────────────────────
def parse_signal_line(line):
    # SIGNAL <idx> <proto> <addr_hex> <cmd_hex>
    parts = line.split()
    if len(parts) == 5 and parts[0] == "SIGNAL":
        return {
            "index":    int(parts[1]),
            "protocol": parts[2],
            "address":  parts[3],
            "command":  parts[4],
        }
    return None

# ── file helpers ──────────────────────────────────────────────────────────────
def ensure_dir():
    os.makedirs(SAVE_DIR, exist_ok=True)

def save_path(name):
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_ ").strip().replace(" ", "_")
    return os.path.join(SAVE_DIR, f"{safe}.json")

def load_file(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"name": "", "created": "", "signals": []}

def save_file(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ── port selection ────────────────────────────────────────────────────────────
def choose_port(preferred=None):
    if preferred:
        return preferred
    port = auto_detect_port()
    if port:
        print(f"  {dim('auto-detected port:')} {cyan(port)}")
        return port
    ports = [p.device for p in serial.tools.list_ports.comports()]
    if not ports:
        print(red("  No serial ports found. Is the Arduino plugged in?"))
        sys.exit(1)
    for i, p in enumerate(ports):
        print(f"  [{i}] {p}")
    idx = input("  Choose port index: ").strip()
    return ports[int(idx)]

# ── capture phase ─────────────────────────────────────────────────────────────
def capture_phase(ser):
    captured = []
    print(f"\n{bold('── CAPTURE ──')}")
    input(f"  Press {green('Enter')} to start capturing, then press buttons on your remote...")
    send(ser, "capture")
    resp = read_line(ser)
    if "OK" not in resp:
        print(red(f"  Unexpected: {resp}"))
        return []

    print(f"  {green('Listening')} — press remote buttons. Press {yellow('Enter')} to stop.\n")

    stop_event = threading.Event()

    def reader():
        while not stop_event.is_set():
            line = ser.readline().decode(errors="replace").strip()
            if not line:
                continue
            sig = parse_signal_line(line)
            if sig:
                captured.append(sig)
                print(f"  {green('●')} [{sig['index']}]  "
                      f"{cyan(sig['protocol'])}  "
                      f"addr={sig['address']}  cmd={sig['command']}")
            elif line.startswith("DUP"):
                print(f"  {dim('○  duplicate skipped')}")
            elif line == "FULL":
                print(yellow("  Storage full (8 max)"))
                stop_event.set()
            elif line.startswith("UNKNOWN"):
                print(yellow("  Unknown protocol — skipped"))

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    input()
    stop_event.set()

    send(ser, "stop")
    time.sleep(0.3)
    ser.reset_input_buffer()

    print(f"\n  Captured {green(str(len(captured)))} unique signal(s).")
    return captured

# ── replay & save phase ───────────────────────────────────────────────────────
def replay_and_save(ser, captured, reps):
    """
    Iterate through every captured signal:
      1. Replay it x reps
      2. Ask: did it work? (y / n / s)
      3. If y → ask for a name for THIS signal → save to ir_saved/<name>.json
      4. Move on to the next signal
    Each working signal gets its own individually named file.
    """
    if not captured:
        print(yellow("  Nothing to replay."))
        return

    print(f"\n{bold('── REPLAY & SAVE ──')}")
    print(f"  {dim(f'Replaying each signal × {reps}. Name each one that works.')}\n")

    send(ser, f"setreps {reps}")
    time.sleep(0.2)
    ser.reset_input_buffer()

    ensure_dir()
    saved_count = 0
    total = len(captured)

    for i, sig in enumerate(captured):
        print(f"  {dim('─'*46)}")
        print(f"  {bold(f'Signal {i+1}/{total}')}  "
              f"[Arduino idx {sig['index']}]  "
              f"{cyan(sig['protocol'])}  "
              f"addr={sig['address']}  cmd={sig['command']}")
        print(f"  {dim('Sending × ' + str(reps) + '...')} ", end="", flush=True)

        send(ser, f"replay {sig['index']}")

        # drain TX progress lines
        while True:
            line = read_line(ser, timeout=reps * 0.5 + 3)
            if line.startswith("TX"):
                print(f"{green('▶')} ", end="", flush=True)
            elif line == "REPLAY_DONE" or line.startswith("ERR") or line == "":
                break
        print()

        # ── did it work? ──────────────────────────────────────────────────
        while True:
            answer = input(
                f"  Did it work?  "
                f"{green('[y]')}es  {red('[n]')}o  {yellow('[s]')}kip:  "
            ).strip().lower()
            if answer in ("y", "yes", "n", "no", "s", "skip"):
                break
            print(f"  {red('Type y, n, or s')}")

        if answer in ("n", "no"):
            print(f"  {red('✗')} Not working — moving on.")
            continue

        if answer in ("s", "skip"):
            print(f"  {dim('Skipped.')}")
            continue

        # ── it worked → ask for a name for this signal ────────────────────
        print(f"  {green('✓ It worked!')}  Give this signal a name:")
        print(f"  {dim('Examples: tv_power  volume_up  mute  input_hdmi1  sleep_timer')}")
        while True:
            sig_name = input(f"  {cyan('Name>')} ").strip()
            if sig_name:
                break
            print(f"  {red('Name cannot be empty.')}")

        # each signal saved to its own file named by the user
        path = save_path(sig_name)
        db = load_file(path)
        if not db["name"]:
            db["name"] = sig_name
            db["created"] = datetime.now().isoformat()

        existing = {(s["protocol"], s["address"], s["command"]) for s in db["signals"]}
        key = (sig["protocol"], sig["address"], sig["command"])

        if key in existing:
            print(f"  {dim('Already in')} {cyan(path)} {dim('— skipped.')}")
        else:
            db["signals"].append({
                "protocol": sig["protocol"],
                "address":  sig["address"],
                "command":  sig["command"],
                "saved_at": datetime.now().isoformat(),
            })
            save_file(path, db)
            saved_count += 1
            print(f"  {green('✓ Saved')} → {cyan(path)}")

    print(f"\n  {dim('─'*46)}")
    print(f"  All done. {green(str(saved_count))}/{total} signal(s) saved.")

# ── entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="IR capture & save")
    parser.add_argument("--port", default=None)
    parser.add_argument("--baud", default=115200, type=int)
    parser.add_argument("--reps", default=3,      type=int, help="Replay reps per signal (default 3)")
    args = parser.parse_args()

    print(BANNER)
    port = choose_port(args.port)

    print(f"  Connecting to {cyan(port)} at {args.baud} baud...")
    try:
        ser = open_serial(port, args.baud)
    except serial.SerialException as e:
        print(red(f"  Failed: {e}"))
        sys.exit(1)

    print(f"  Waiting for Arduino... ", end="", flush=True)
    if wait_for_ready(ser):
        print(green("ready!"))
    else:
        print(yellow("(no READY — continuing)"))

    try:
        while True:
            captured = capture_phase(ser)
            if captured:
                replay_and_save(ser, captured, args.reps)
            again = input(f"\n  Capture more signals? {green('[y]')} / {red('[n]')}:  ").strip().lower()
            if again not in ("y", "yes"):
                break
    except KeyboardInterrupt:
        print(f"\n  {yellow('Interrupted.')}")
    finally:
        send(ser, "stop")
        ser.close()
        print(f"  {dim('Serial closed. Bye.')}")

if __name__ == "__main__":
    main()