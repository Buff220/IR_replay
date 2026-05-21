#include <IRremote.hpp>

const int RX_PIN    = 2;
const int TX_PIN    = 3;
const int MAX_SIGS  = 8;
int N = 1;

struct TinySignal {
    uint8_t  protocol;
    uint16_t address;
    uint16_t command;
};

TinySignal signals[MAX_SIGS];
int  signalCount = 0;
bool capturing   = false;

// ── helpers ────────────────────────────────────────────────────────────────
bool isDuplicate(uint8_t proto, uint16_t addr, uint16_t cmd) {
    for (int i = 0; i < signalCount; i++)
        if (signals[i].protocol == proto &&
            signals[i].address  == addr  &&
            signals[i].command  == cmd)
            return true;
    return false;
}

void replayOne(int idx) {
    IRData d;
    d.protocol = (decode_type_t)signals[idx].protocol;
    d.address  = signals[idx].address;
    d.command  = signals[idx].command;
    d.flags    = IRDATA_FLAGS_EMPTY;
    IrSender.write(&d);
}

// ── capture ────────────────────────────────────────────────────────────────
void doCapture() {
    if (!IrReceiver.decode()) return;
    uint8_t  proto = IrReceiver.decodedIRData.protocol;
    uint16_t addr  = IrReceiver.decodedIRData.address;
    uint16_t cmd   = IrReceiver.decodedIRData.command;
    IrReceiver.resume();

    if (proto == UNKNOWN) { Serial.println(F("UNKNOWN")); return; }
    if (isDuplicate(proto, addr, cmd)) {
        Serial.print(F("DUP 0x")); Serial.print(addr,HEX);
        Serial.print(F(" 0x"));   Serial.println(cmd,HEX);
        return;
    }
    if (signalCount >= MAX_SIGS) { Serial.println(F("FULL")); return; }

    signals[signalCount] = {proto, addr, cmd};
    // Machine-readable line Python can parse:
    // SIGNAL <idx> <proto> <addr_hex> <cmd_hex>
    Serial.print(F("SIGNAL "));
    Serial.print(signalCount); Serial.print(F(" "));
    Serial.print(getProtocolString((decode_type_t)proto)); Serial.print(F(" "));
    Serial.print(F("0x")); Serial.print(addr, HEX); Serial.print(F(" "));
    Serial.print(F("0x")); Serial.println(cmd, HEX);
    signalCount++;
}

// ── replay N times ─────────────────────────────────────────────────────────
void doReplay(int idx) {
    if (idx < 0 || idx >= signalCount) {
        Serial.print(F("ERR bad index 0-")); Serial.println(signalCount-1);
        return;
    }
    IrReceiver.stop();
    for (int i = 0; i < N; i++) {
        replayOne(idx);
        Serial.print(F("TX ")); Serial.print(i+1);
        Serial.print(F("/")); Serial.println(N);
        delay(200);
    }
    Serial.println(F("REPLAY_DONE"));
    if (capturing) IrReceiver.start();
}

// ── replay exactly once (used by the Python saved-commands player) ─────────
void doReplayOnce(int idx) {
    if (idx < 0 || idx >= signalCount) {
        Serial.print(F("ERR bad index 0-")); Serial.println(signalCount-1);
        return;
    }
    IrReceiver.stop();
    replayOne(idx);
    Serial.println(F("REPLAY_DONE"));
    if (capturing) IrReceiver.start();
}

// ── serial command parser ──────────────────────────────────────────────────
void handleSerial() {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.equalsIgnoreCase(F("capture"))) {
        capturing = true;
        IrReceiver.begin(RX_PIN);
        Serial.println(F("OK capturing"));

    } else if (cmd.equalsIgnoreCase(F("stop"))) {
        capturing = false;
        IrReceiver.stop();
        Serial.print(F("OK stopped count=")); Serial.println(signalCount);

    } else if (cmd.equalsIgnoreCase(F("list"))) {
        Serial.print(F("COUNT ")); Serial.println(signalCount);
        for (int i = 0; i < signalCount; i++) {
            Serial.print(F("SIGNAL "));
            Serial.print(i); Serial.print(F(" "));
            Serial.print(getProtocolString((decode_type_t)signals[i].protocol));
            Serial.print(F(" 0x")); Serial.print(signals[i].address, HEX);
            Serial.print(F(" 0x")); Serial.println(signals[i].command, HEX);
        }
        Serial.println(F("LIST_DONE"));

    } else if (cmd.startsWith(F("replay "))) {
        doReplay(cmd.substring(7).toInt());

    } else if (cmd.startsWith(F("replayonce "))) {
        doReplayOnce(cmd.substring(11).toInt());

    } else if (cmd.startsWith(F("setreps "))) {
        int n = cmd.substring(8).toInt();
        if (n < 1) { Serial.println(F("ERR reps>=1")); return; }
        N = n;
        Serial.print(F("OK N=")); Serial.println(N);

    } else if (cmd.startsWith(F("inject "))) {
        // inject <proto_name_or_num> <addr_hex> <cmd_hex>
        // Used by ir_play.py to reload saved signals into RAM.
        if (signalCount >= MAX_SIGS) { Serial.println(F("ERR FULL")); return; }
        // format: inject NEC 0x40 0x8
        int s1 = cmd.indexOf(' ', 7);
        int s2 = cmd.indexOf(' ', s1 + 1);
        if (s1 < 0 || s2 < 0) { Serial.println(F("ERR inject format")); return; }
        String protoStr = cmd.substring(7, s1);
        String addrStr  = cmd.substring(s1+1, s2);
        String cmdStr   = cmd.substring(s2+1);
        addrStr.trim(); cmdStr.trim();
        uint16_t addr = (uint16_t)strtol(addrStr.c_str(), nullptr, 16);
        uint16_t icmd = (uint16_t)strtol(cmdStr.c_str(),  nullptr, 16);
        // resolve protocol name to number
        uint8_t proto = UNKNOWN;
        for (uint8_t p = 1; p < 30; p++) {
            if (protoStr.equalsIgnoreCase(getProtocolString((decode_type_t)p))) {
                proto = p; break;
            }
        }
        signals[signalCount++] = {proto, addr, icmd};
        Serial.print(F("OK injected idx=")); Serial.println(signalCount-1);

    } else if (cmd.equalsIgnoreCase(F("clear"))) {
        signalCount = 0;
        Serial.println(F("OK cleared"));

    } else if (cmd.equalsIgnoreCase(F("help"))) {
        Serial.println(F("capture|stop|list|replay N|replayonce N|setreps N|clear"));

    } else {
        Serial.print(F("ERR unknown: ")); Serial.println(cmd);
    }
}

void setup() {
    Serial.begin(115200);
    IrSender.begin(TX_PIN);
    Serial.println(F("READY"));
}

void loop() {
    if (Serial.available()) handleSerial();
    if (capturing) doCapture();
}
