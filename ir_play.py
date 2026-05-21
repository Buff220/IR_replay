#!/usr/bin/env python3
"""
ir_play.py  —  Load all saved IR signals and replay them on demand.

Usage:
    python ir_play.py [--port COM3] [--baud 115200] [--reps 3]
"""

import serial
import serial.tools.list_ports
import json
import time
import glob
import os
import sys
import argparse

SAVE_DIR = "ir_saved"

# ── colours ───────────────────────────────────────────────────────────────────
def c(text, code): return f"\033[{code}m{text}\033[0m"
def green(t):  return c(t, "92")
def yellow(t): return c(t, "93")
def red(t):    return c(t, "91")
def cyan(t):   return c(t, "96")
def bold(t):   return c(t, "1")
def dim(t):    return c(t, "2")

# ── serial ────────────────────────────────────────────────────────────────────
def auto_detect_port():
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if any(k in desc for k in ("arduino", "ch340", "cp210", "ftdi", "usb serial")):
            return p.device
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return ports[0] if ports else None

def choose_port(preferred=None):
    if preferred:
        return preferred
    port = auto_detect_port()
    if port:
        print(f"  {dim('auto-detected:')} {cyan(port)}")
        return port
    ports = [p.device for p in serial.tools.list_ports.comports()]
    if not ports:
        print(red("  No serial ports found. Is the Arduino plugged in?"))
        sys.exit(1)
    for i, p in enumerate(ports):
        print(f"  [{i}] {p}")
    return ports[int(input("  Choose port index: ").strip())]

def open_serial(port, baud):
    ser = serial.Serial(port, baud, timeout=2)
    time.sleep(2)                    # wait for Arduino reset
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

def wait_ready(ser):
    print(f"  Waiting for Arduino READY... ", end="", flush=True)
    deadline = time.time() + 6
    while time.time() < deadline:
        line = ser.readline().decode(errors="replace").strip()
        if line == "READY":
            print(green("OK"))
            return
    # not fatal — Arduino may already be running
    print(yellow("(no READY received, continuing)"))

# ── load signals ──────────────────────────────────────────────────────────────
def load_all_signals():
    files = sorted(glob.glob(os.path.join(SAVE_DIR, "*.json")))
    if not files:
        print(red(f"  No .json files found in {SAVE_DIR}/"))
        print(f"  Run ir_capture.py first.")
        sys.exit(1)

    signals = []
    for fpath in files:
        try:
            with open(fpath) as f:
                db = json.load(f)
            name = db.get("name") or os.path.splitext(os.path.basename(fpath))[0]
            for sig in db.get("signals", []):
                signals.append({
                    "name":     name,
                    "protocol": sig["protocol"],
                    "address":  sig["address"],
                    "command":  sig["command"],
                })
        except Exception as e:
            print(yellow(f"  Could not read {fpath}: {e}"))
    return signals

# ── inject all signals into Arduino RAM ───────────────────────────────────────
def inject_all(ser, signals):
    """
    Send 'clear' then inject each signal one by one so Arduino assigns
    them indices 0, 1, 2, ... matching our list positions.
    """
    send(ser, "clear")
    resp = read_line(ser, timeout=2)
    if "cleared" not in resp.lower():
        print(yellow(f"  clear response: {resp}"))

    for i, sig in enumerate(signals):
        cmd = f"inject {sig['protocol']} {sig['address']} {sig['command']}"
        send(ser, cmd)
        resp = read_line(ser, timeout=2)
        if resp.startswith("ERR"):
            print(red(f"  inject [{i}] failed: {resp}"))
            return False
        # expect "OK injected idx=N"
    return True

# ── replay one signal by its Arduino index ────────────────────────────────────
def replay(ser, arduino_idx, reps):
    send(ser, f"setreps {reps}")
    read_line(ser, timeout=2)           # drain "OK N=..."

    send(ser, f"replay {arduino_idx}")
    print(f"  {dim('Sending')} ", end="", flush=True)
    timeout = reps * 0.6 + 3
    while True:
        line = read_line(ser, timeout=timeout)
        if line.startswith("TX"):
            print(f"{green('▶')} ", end="", flush=True)
        elif line == "REPLAY_DONE":
            print(green("  done"))
            return True
        elif line.startswith("ERR") or line == "":
            print(red(f"  error: {line or 'timeout'}"))
            return False

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=None)
    parser.add_argument("--baud", default=115200, type=int)
    parser.add_argument("--reps", default=1,      type=int)
    args = parser.parse_args()

    print(f"\n{cyan('━'*48)}")
    print(f"  {bold('IR Player')}  —  replay saved commands")
    print(f"{cyan('━'*48)}\n")

    # 1. load all saved signals
    signals = load_all_signals()
    print(f"  Loaded {green(str(len(signals)))} signal(s) from {cyan(SAVE_DIR+'/'):}")
    for i, sig in enumerate(signals):
        print(f"    [{cyan(str(i))}]  {bold(sig['name']):<20}  "
              f"{dim(sig['protocol'])}  addr={dim(sig['address'])}  cmd={dim(sig['command'])}")

    # 2. connect to Arduino
    print()
    port = choose_port(args.port)
    print(f"  Connecting to {cyan(port)}... ", end="", flush=True)
    try:
        ser = open_serial(port, args.baud)
        print(green("connected"))
    except serial.SerialException as e:
        print(red(f"failed\n  {e}"))
        sys.exit(1)

    wait_ready(ser)

    # 3. inject all signals into Arduino RAM
    print(f"  Injecting {len(signals)} signal(s) into Arduino RAM... ", end="", flush=True)
    if inject_all(ser, signals):
        print(green("OK"))
    else:
        print(red("some signals failed to inject — check sketch has 'inject' command"))
        sys.exit(1)

    # 4. replay loop
    print(f"\n  {dim('─'*44)}")
    print(f"  {bold('Ready.')}  Type an index to replay, or {yellow('q')} to quit.")
    print(f"  {dim('Reps: '+str(args.reps)+'   (pass --reps N to change)')}")
    print(f"  {dim('─'*44)}\n")

    try:
        while True:
            # always reprint the menu so user doesn't have to remember
            for i, sig in enumerate(signals):
                print(f"  [{cyan(str(i))}] {bold(sig['name'])}")

            raw = input(f"\n  {cyan('>')} ").strip().lower()

            if raw in ("q", "quit", "exit", ""):
                break

            try:
                idx = int(raw)
            except ValueError:
                print(red(f"  '{raw}' is not a number. Try again.\n"))
                continue

            if idx < 0 or idx >= len(signals):
                print(red(f"  Index {idx} out of range (0–{len(signals)-1})\n"))
                continue

            sig = signals[idx]
            print(f"\n  Replaying [{idx}] {bold(sig['name'])}  "
                  f"× {args.reps}  "
                  f"{dim(sig['protocol']+'  '+sig['address']+'  '+sig['command'])}")
            replay(ser, idx, args.reps)
            print()

    except KeyboardInterrupt:
        print(f"\n  {yellow('Ctrl+C — exiting.')}")
    finally:
        ser.close()
        print(f"  {dim('Serial closed.')}")

if __name__ == "__main__":
    main()