# 📡 IR Replay Attack — Arduino IR Remote Cloner

A complete toolkit for **capturing, saving, and replaying infrared (IR) remote control signals** using an Arduino. Point any IR remote at the receiver, capture its signals, verify they work, save them with custom names, and replay them on demand — either from a command-line interface or a graphical remote control window.

---

## 🗂️ Project Structure

```
replay_attack/
├── ir_capture.py        # CLI tool: capture IR signals & save the ones that work
├── ir_play.py           # CLI tool: load saved signals and replay them on demand
├── ir_gui.pyw           # GUI tool: visual remote control window (pygame)
├── wiring.txt           # Hardware wiring reference
├── ir_saved/            # Saved IR signal files (JSON), one per button
│   ├── power.json
│   ├── mute.json
│   ├── volume_up.json
│   ├── volume_down.json
│   ├── ch_up.json
│   ├── ch_down.json
│   └── ok.json
└── inos/
    ├── ir_controller.ino  # Main Arduino sketch (use this one)
    └── mini_replay.ino    # Older/simpler Arduino sketch (for reference)
```

---

## ⚙️ How It Works

The system has two parts that communicate over USB serial at 115200 baud:

**Arduino (firmware)** — handles the hardware:
- Listens for IR signals via the receiver on **pin D2**
- Transmits IR signals via the LED on **pin D3**
- Stores up to **8 signals in RAM**
- Accepts simple text commands over Serial (`capture`, `stop`, `replay N`, `inject`, `clear`, etc.)

**Python scripts (host)** — provide the user interface:
- `ir_capture.py` sends the `capture` command, receives decoded signals, lets you test-replay them, and saves the ones that work to `ir_saved/` as JSON files
- `ir_play.py` reads all JSON files, injects the signals back into Arduino RAM using the `inject` command, then lets you replay any of them by index
- `ir_gui.pyw` does the same as `ir_play.py` but with a graphical remote control window

---

## 🔧 Hardware Requirements

| Component | Details |
|---|---|
| Arduino | Uno, Nano, Pro Mini, or any AVR-based board |
| IR Receiver | 3-pin module (e.g. VS1838B, TSOP38238) |
| IR LED | 950 nm infrared LED |
| Resistor | 100 Ω resistor (for the IR LED) |

### Wiring

**IR Receiver** (3-pin module):
```
Pin 1 (OUT) → Arduino D2
Pin 2 (VCC) → Arduino 5V
Pin 3 (GND) → Arduino GND
```

**IR LED (transmitter)**:
```
IR LED (+) → 100Ω resistor → Arduino D3
IR LED (-) → Arduino GND
```

> ⚠️ The 100 Ω resistor is required between the IR LED anode and D3. Without it you risk damaging the Arduino pin.

---

## 💻 Software Requirements

### Arduino
- [Arduino IDE](https://www.arduino.cc/en/software) 1.8+ or 2.x
- [IRremote library](https://github.com/Arduino-IRremote/Arduino-IRremote) — install via Arduino Library Manager (`Sketch → Include Library → Manage Libraries → search "IRremote"`)

### Python
- Python 3.7+
- `pyserial` — for serial communication
- `pygame` — only needed for the GUI (`ir_gui.pyw`)

Install dependencies:
```bash
pip install pyserial pygame
```

---

## 🚀 Getting Started

### Step 1 — Flash the Arduino

1. Open `inos/ir_controller.ino` in the Arduino IDE
2. Select your board under `Tools → Board`
3. Select the correct port under `Tools → Port`
4. Click **Upload**

Once uploaded, open the Serial Monitor at **115200 baud** — you should see `READY`.

> **Note:** `mini_replay.ino` is an older, simpler sketch kept for reference. Use `ir_controller.ino` for all Python scripts.

### Step 2 — Capture IR Signals

Run the capture script:

```bash
python ir_capture.py
```

Optional arguments:
```
--port COM3       Serial port (auto-detected if omitted)
--baud 115200     Baud rate (default: 115200)
--reps 3          How many times to replay each signal during verification (default: 3)
```

**Workflow:**
1. The script connects to the Arduino and waits for it to be ready
2. Press **Enter** to start capturing, then press buttons on your remote
3. Each captured signal is printed with its protocol, address, and command
4. Press **Enter** again to stop capturing
5. The script replays each signal and asks: **Did it work?**
   - `y` → prompts you for a name (e.g. `tv_power`, `volume_up`) and saves it to `ir_saved/<name>.json`
   - `n` → discards the signal
   - `s` → skips without saving
6. You can capture more signals or quit

Each working signal is saved as its own JSON file in `ir_saved/`.

### Step 3 — Replay Signals (CLI)

```bash
python ir_play.py
```

Optional arguments:
```
--port COM3       Serial port (auto-detected if omitted)
--baud 115200     Baud rate (default: 115200)
--reps 1          How many times to send each signal (default: 1)
```

**Workflow:**
1. Loads all `.json` files from `ir_saved/`
2. Injects all signals into Arduino RAM
3. Displays a numbered menu of all saved signals
4. Type the index number of the signal you want to send, press **Enter**
5. Type `q` to quit

### Step 4 — Replay Signals (GUI)

```bash
python ir_gui.pyw
```

or double-click `ir_gui.pyw` on Windows.

Opens a 320×520 pixel remote control window with buttons for:
`POWER`, `MUTE`, `CH UP`, `CH DOWN`, `VOLUME UP`, `VOLUME DOWN`, `OK`

- **Click** a button to send the signal once
- **Hold** a button to send it repeatedly (with 150 ms spacing)
- Status indicator at the bottom shows `CONNECTED` or `OFFLINE`

> The GUI expects exactly the 7 signal files listed above (`power.json`, `mute.json`, etc.) in `ir_saved/`. Missing files are silently skipped and shown as inactive.

---

## 📁 Saved Signal Format

Each file in `ir_saved/` follows this JSON structure:

```json
{
  "name": "power",
  "created": "2026-05-21T14:34:19.384237",
  "signals": [
    {
      "protocol": "NEC2",
      "address": "0x4",
      "command": "0x8",
      "saved_at": "2026-05-21T14:34:19.384278"
    }
  ]
}
```

You can manually create or edit these files if you already know your device's IR codes. The filename (without `.json`) is used as the display name if the `"name"` field is absent.

---

## 📟 Arduino Serial Command Reference

You can also control the Arduino directly from any serial terminal at 115200 baud:

| Command | Description |
|---|---|
| `capture` | Start listening for IR signals on pin D2 |
| `stop` | Stop capturing |
| `list` | Print all signals currently stored in RAM |
| `replay <idx>` | Replay signal at index `idx`, repeated N times |
| `replayonce <idx>` | Replay signal exactly once regardless of N |
| `setreps <n>` | Set the repeat count N (default 1) |
| `inject <proto> <addr_hex> <cmd_hex>` | Load a signal into RAM by value (used by Python scripts) |
| `clear` | Wipe all signals from RAM |
| `help` | Print command list |

Example session:
```
> capture
OK capturing
SIGNAL 0 NEC2 0x4 0x8
SIGNAL 1 NEC2 0x4 0x10
> stop
OK stopped count=2
> setreps 3
OK N=3
> replay 0
TX 1/3
TX 2/3
TX 3/3
REPLAY_DONE
> clear
OK cleared
```

---

## 🛠️ Troubleshooting

**No serial port detected**
- Make sure the Arduino is plugged in via USB
- On Linux you may need to add yourself to the `dialout` group: `sudo usermod -aG dialout $USER`
- On Windows, check Device Manager for the COM port number and pass it with `--port COM3`

**"No READY received"**
- The script continues anyway. This just means the Arduino had already booted before the script connected — the firmware is running fine.

**Signals captured but replay doesn't work**
- Aim the IR LED directly at the device's sensor, within ~1–2 metres
- Try increasing `--reps` to send the signal more times
- Some protocols (e.g. NEC repeat frames) need specific timing; try pressing the original remote button once vs. holding it during capture

**Unknown protocol warning**
- Not all remotes use standard protocols. Raw-mode capture is not supported by this sketch. If your remote consistently shows `UNKNOWN`, it may use a non-standard or proprietary protocol.

**GUI shows OFFLINE**
- The Arduino was not detected at startup. Make sure it is plugged in before launching `ir_gui.pyw`.

---

## 📚 Dependencies & Acknowledgements

- [IRremote for Arduino](https://github.com/Arduino-IRremote/Arduino-IRremote) — IR encoding/decoding library
- [pyserial](https://pyserial.readthedocs.io/) — Python serial communication
- [pygame](https://www.pygame.org/) — GUI rendering for `ir_gui.pyw`

---

## 📄 License

This project is provided as-is for educational and personal use. Use responsibly — only capture and replay signals for devices you own.
