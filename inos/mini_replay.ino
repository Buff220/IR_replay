#include <IRremote.hpp>

const int RX_PIN = 2;
const int TX_PIN = 3;
const int MAX_SIGNALS = 10;
int N = 1;  // global replay count

struct IRSignal {
    IRData data;
    bool used = false;
};

IRSignal signals[MAX_SIGNALS];
int signalCount = 0;
bool capturing = false;

void setup() {
    Serial.begin(115200);
    IrSender.begin(TX_PIN);
    Serial.println("IR Controller ready. Firmware v2.0");
    Serial.println("Commands: capture | stop | list | replay <idx> | setreps <n> | clear | help");
}

bool isDuplicate(IRData &incoming) {
    for (int i = 0; i < signalCount; i++) {
        if (signals[i].data.protocol == incoming.protocol &&
            signals[i].data.address == incoming.address &&
            signals[i].data.command == incoming.command) {
            return true;
        }
    }
    return false;
}

void doCapture() {
    if (IrReceiver.decode()) {
        IRData d = IrReceiver.decodedIRData;
        IrReceiver.resume();

        if (d.protocol == UNKNOWN) {
            Serial.println("[WARN] Unknown protocol — skipped");
            return;
        }
        if (isDuplicate(d)) {
            Serial.print("[DUP]  proto="); Serial.print(getProtocolString(d.protocol));
            Serial.print(" addr=0x"); Serial.print(d.address, HEX);
            Serial.print(" cmd=0x"); Serial.println(d.command, HEX);
            return;
        }
        if (signalCount >= MAX_SIGNALS) {
            Serial.println("[WARN] Storage full (20 signals max)");
            return;
        }
        signals[signalCount].data = d;
        signals[signalCount].used = true;
        Serial.print("[SAVED idx="); Serial.print(signalCount);
        Serial.print("]  proto="); Serial.print(getProtocolString(d.protocol));
        Serial.print(" addr=0x"); Serial.print(d.address, HEX);
        Serial.print(" cmd=0x"); Serial.println(d.command, HEX);
        signalCount++;
    }
}

void doReplay(int idx) {
    if (idx < 0 || idx >= signalCount) {
        Serial.print("[ERR] Index "); Serial.print(idx);
        Serial.print(" out of range (0–"); Serial.print(signalCount - 1); Serial.println(")");
        return;
    }
    IrReceiver.stop();
    Serial.print("[REPLAY] index="); Serial.print(idx);
    Serial.print(" x"); Serial.println(N);

    for (int i = 0; i < N; i++) {
        Serial.print("  TX ["); Serial.print(i + 1);
        Serial.print("/"); Serial.print(N); Serial.println("]");
        IrSender.write(&signals[idx].data);
        delay(200);
    }

    Serial.println("[DONE]");
    if (capturing) IrReceiver.start();
}

void handleSerial() {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    cmd.toLowerCase();

    if (cmd == "capture") {
        capturing = true;
        IrReceiver.begin(RX_PIN);
        Serial.println("[OK] Capturing — send 'stop' to end");

    } else if (cmd == "stop") {
        capturing = false;
        IrReceiver.stop();
        Serial.print("[OK] Stopped. "); Serial.print(signalCount); Serial.println(" signal(s) stored.");

    } else if (cmd == "list") {
        if (signalCount == 0) { Serial.println("[INFO] No signals stored"); return; }
        Serial.print("[INFO] "); Serial.print(signalCount); Serial.println(" signal(s):");
        for (int i = 0; i < signalCount; i++) {
            Serial.print("  ["); Serial.print(i); Serial.print("]  ");
            Serial.print(getProtocolString(signals[i].data.protocol));
            Serial.print("  addr=0x"); Serial.print(signals[i].data.address, HEX);
            Serial.print("  cmd=0x"); Serial.println(signals[i].data.command, HEX);
        }

    } else if (cmd.startsWith("replay ")) {
        int idx = cmd.substring(7).toInt();
        doReplay(idx);

    } else if (cmd.startsWith("setreps ")) {
        int n = cmd.substring(8).toInt();
        if (n < 1) { Serial.println("[ERR] reps must be >= 1"); return; }
        N = n;
        Serial.print("[OK] Repetitions set to "); Serial.println(N);

    } else if (cmd == "clear") {
        signalCount = 0;
        memset(signals, 0, sizeof(signals));
        Serial.println("[OK] All signals cleared");

    } else if (cmd == "help") {
        Serial.println("Commands:");
        Serial.println("  capture        start receiving on PIN 2");
        Serial.println("  stop           stop capturing");
        Serial.println("  list           show stored signals");
        Serial.println("  replay <idx>   replay signal N times");
        Serial.println("  setreps <n>    set repeat count (currently N=" + String(N) + ")");
        Serial.println("  clear          wipe all signals");

    } else {
        Serial.print("[ERR] Unknown: "); Serial.println(cmd);
    }
}

void loop() {
    if (Serial.available()) handleSerial();
    if (capturing) doCapture();
}
