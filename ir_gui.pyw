#!/usr/bin/env python3
import sys
import os
import glob
import json
import time
import serial
import serial.tools.list_ports
import pygame

# --- Configuration & Initialization ---
SAVE_DIR = "ir_saved"
BAUD_RATE = 115200

pygame.init()
# Safe font fallback initialization
try:
    FONT = pygame.font.SysFont("Arial", 16, bold=True)
except Exception:
    FONT = pygame.font.Font(None, 24)

# Window layout configuration
WIDTH, HEIGHT = 320, 520
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("IR Remote Controller")
clock = pygame.time.Clock()

# Theme Colors (RGB)
BG_COLOR = (30, 30, 35)       # Dark charcoal
BTN_COLOR = (50, 50, 60)      # Sleek gray
BTN_HOVER = (70, 70, 85)      # Lighter gray for hover state
POWER_COLOR = (180, 40, 40)   # Reddish for power
POWER_HOVER = (220, 50, 50)   # Brighter red for power hover
TEXT_COLOR = (240, 240, 240)  # Off-white
STATUS_COLOR = (100, 200, 100)# Pale green

# --- Serial Communication Helpers ---
def auto_detect_port():
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if any(k in desc for k in ("arduino", "ch340", "cp210", "ftdi", "usb serial")):
            return p.device
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return ports[0] if ports else None

def open_serial():
    port = auto_detect_port()
    if not port:
        print("Error: No serial port detected. Plug in your Arduino!")
        return None
    try:
        print(f"Connecting to Arduino on {port}...")
        ser = serial.Serial(port, BAUD_RATE, timeout=0.5)
        time.sleep(2)  # Wait for Arduino reboot
        ser.reset_input_buffer()
        return ser
    except Exception as e:
        print(f"Serial connection error: {e}")
        return None

def send_cmd(ser, cmd):
    if ser:
        try:
            ser.write((cmd + "\n").encode())
        except Exception:
            pass

def load_signals():
    """Finds and indexes the exact 7 files required, mapping them to standard indices."""
    files = sorted(glob.glob(os.path.join(SAVE_DIR, "*.json")))
    
    # We want to catch names matching your specific files
    target_names = ["ok", "ch_down", "ch_up", "mute", "power", "volume_down", "volume_up"]
    
    # Pre-populate empty slots so indices always match exactly 
    signals_map = {name: None for name in target_names}

    for fpath in files:
        try:
            with open(fpath) as f:
                db = json.load(f)
            name = db.get("name") or os.path.splitext(os.path.basename(fpath))[0]
            name_lower = name.lower().strip()
            
            if name_lower in signals_map:
                for sig in db.get("signals", []):
                    signals_map[name_lower] = {
                        "name": name,
                        "protocol": sig["protocol"],
                        "address": sig["address"],
                        "command": sig["command"],
                    }
        except Exception as e:
            print(f"Error reading {fpath}: {e}")

    # Order them strictly matching indices 0 through 6
    ordered_list = []
    for n in target_names:
        if signals_map[n] is not None:
            ordered_list.append(signals_map[n])
        else:
            # Fallback mock object if a specific file is missing from the directory
            ordered_list.append({
                "name": n,
                "protocol": "UNKNOWN",
                "address": "0x0",
                "command": "0x0"
            })
    return ordered_list

def inject_all_signals(ser, signals):
    if not ser:
        return False
    send_cmd(ser, "clear")
    time.sleep(0.1)
    for sig in signals:
        cmd = f"inject {sig['protocol']} {sig['address']} {sig['command']}"
        send_cmd(ser, cmd)
        time.sleep(0.05) # small delay to let Arduino RAM process it safely
    return True

# --- Main Application Logic ---
def main():
    # 1. Load data & connection
    signals = load_signals()
    ser = open_serial()
    if ser:
        print("Injecting signals into Arduino...")
        inject_all_signals(ser, signals)
        send_cmd(ser, "setreps 1") 

    # 2. Build layout geometric grid for standard 7-button remote layout
    button_layouts = []
    
    def get_idx_by_name(name_str):
        for idx, s in enumerate(signals):
            if s['name'].lower() == name_str: return idx
        return None

    # Define physical layout zones
    layout_definitions = [
        ("power", (40, 30, 240, 45)),
        ("mute", (40, 95, 240, 40)),
        ("ch_up", (40, 160, 110, 50)),
        ("volume_up", (170, 160, 110, 50)),
        ("ok", (40, 230, 240, 60)),
        ("ch_down", (40, 310, 110, 50)),
        ("volume_down", (170, 310, 110, 50)),
    ]

    for name, rect in layout_definitions:
        a_idx = get_idx_by_name(name)
        if a_idx is not None:
            button_layouts.append({"name": name.upper().replace("_", " "), "idx": a_idx, "rect": pygame.Rect(rect)})

    # Timing variables for handling hold inputs smoothly without spamming data too fast
    last_tx_time = 0
    TX_DELAY = 0.15 # Delay spacing (seconds) while holding down a button

    running = True
    active_button_idx = None # Tracks which button is currently being clicked/held

    while running:
        mouse_pos = pygame.mouse.get_pos()
        mouse_pressed = pygame.mouse.get_pressed()[0] # Left click state

        # Event Loop
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Check what button was clicked initially
                for btn in button_layouts:
                    if btn["rect"].collidepoint(mouse_pos):
                        active_button_idx = btn["idx"]
                        break
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                active_button_idx = None

        # Reset selection if player drags mouse out away from clicked button boundaries
        if active_button_idx is not None and mouse_pressed:
            current_hover_btn = None
            for btn in button_layouts:
                if btn["rect"].collidepoint(mouse_pos):
                    current_hover_btn = btn["idx"]
            if current_hover_btn != active_button_idx:
                active_button_idx = None # User dragged away

        # Continuous execution logic while user holds the button
        if active_button_idx is not None:
            current_time = time.time()
            if current_time - last_tx_time > TX_DELAY:
                print(f"Replaying signal index: [{active_button_idx}]")
                send_cmd(ser, f"replay {active_button_idx}")
                last_tx_time = current_time

        # --- Draw Screen ---
        screen.fill(BG_COLOR)

        # Draw Title Banner Area
        title_text = FONT.render("ARDUINO REMOTE", True, TEXT_COLOR)
        screen.blit(title_text, (WIDTH // 2 - title_text.get_width() // 2, 10))
        
        status_str = "CONNECTED" if ser else "OFFLINE"
        status_text = FONT.render(status_str, True, STATUS_COLOR if ser else POWER_COLOR)
        screen.blit(status_text, (WIDTH // 2 - status_text.get_width() // 2, HEIGHT - 25))

        # Render Interactive Remote Buttons
        for btn in button_layouts:
            is_hovered = btn["rect"].collidepoint(mouse_pos)
            is_active = (active_button_idx == btn["idx"])

            if "POWER" in btn["name"]:
                color = POWER_HOVER if (is_hovered or is_active) else POWER_COLOR
            else:
                color = BTN_HOVER if (is_hovered or is_active) else BTN_COLOR

            pygame.draw.rect(screen, color, btn["rect"], border_radius=8)
            
            if is_active:
                pygame.draw.rect(screen, (255, 255, 255), btn["rect"], width=2, border_radius=8)

            # Draw Text Labels inside boxes
            text_surface = FONT.render(btn["name"], True, TEXT_COLOR)
            text_x = btn["rect"].x + (btn["rect"].width // 2) - (text_surface.get_width() // 2)
            text_y = btn["rect"].y + (btn["rect"].height // 2) - (text_surface.get_height() // 2)
            screen.blit(text_surface, (text_x, text_y))

        pygame.display.flip()
        clock.tick(60)

    if ser:
        ser.close()
    pygame.quit()

if __name__ == "__main__":
    main()