// CYD Offline BLE Backup Script for Shelly Gen3/Gen4 (Firmware 2.2.1+)
// Managed by CYD Tiled Display Configurator - zero persistent BLE connections.
// Uses 16-bit BLE Service Data (AD Type 0x16):
//   0xC753: Hub -> Shelly Command (14 B)
//   0xC754: Shelly -> Hub State Beacon (14 B)
//   0xC755: Shelly -> Hub Detached Input Event (14 B)

var CFG = {
  networkKey: "__NETWORK_KEY__",
  heartbeatNormalMs: 30000,
  heartbeatOfflineMs: 10000,
  coverMovePollMs: 1500
};

var UUID_CMD = "c753";
var UUID_STATE = "c754";
var UUID_INPUT = "c755";

var KIND_SWITCH = 1;
var KIND_COVER = 2;
var KIND_INPUT_TOGGLE = 3;

var OP_SW_OFF = 1;
var OP_SW_ON = 2;
var OP_SW_TOGGLE = 3;
var OP_COV_OPEN = 4;
var OP_COV_CLOSE = 5;
var OP_COV_STOP = 6;
var OP_COV_POS = 7;
var OP_QUERY_STATE = 8;

// Exact 32-bit FNV-1a in mJS (16-bit split multiply avoids IEEE-754 float precision loss)
function fnv1aByte(h, b) {
  h = (h ^ (b & 0xff)) >>> 0;
  var lo = (h & 0xffff) * 0x0193;
  var hi = ((h >>> 16) * 0x0193 + (h & 0xffff) * 0x0100 + (lo >>> 16)) & 0xffff;
  return ((hi << 16) | (lo & 0xffff)) >>> 0;
}

function fnv1aStr(s, seed) {
  var h = (typeof seed === "number") ? (seed >>> 0) : 2166136261;
  for (var i = 0; i < s.length; i++) {
    h = fnv1aByte(h, s.charCodeAt(i));
  }
  return h >>> 0;
}

function normalizeMac(mac) {
  var s = (mac || "").toLowerCase();
  var out = "";
  for (var i = 0; i < s.length; i++) {
    var c = s.charCodeAt(i);
    if ((c >= 48 && c <= 57) || (c >= 97 && c <= 102)) {
      out += s.charAt(i);
    }
  }
  return out;
}

function u16le(v) {
  return String.fromCharCode(v & 0xff, (v >>> 8) & 0xff);
}

function u32le(v) {
  return String.fromCharCode(
    v & 0xff,
    (v >>> 8) & 0xff,
    (v >>> 16) & 0xff,
    (v >>> 24) & 0xff
  );
}

function readU16le(s, off) {
  return (s.charCodeAt(off) & 0xff) | ((s.charCodeAt(off + 1) & 0xff) << 8);
}

function readU32le(s, off) {
  return (
    (s.charCodeAt(off) & 0xff) |
    ((s.charCodeAt(off + 1) & 0xff) << 8) |
    ((s.charCodeAt(off + 2) & 0xff) << 16) |
    ((s.charCodeAt(off + 3) & 0xff) << 24)
  ) >>> 0;
}

var KEY_SEED = fnv1aStr(CFG.networkKey, 2166136261);

function computeAuthTag(payload10) {
  return fnv1aStr(payload10, KEY_SEED);
}

var DEV_INFO = Shelly.getDeviceInfo();
var MY_MAC = normalizeMac(DEV_INFO.mac);
var MY_ID = fnv1aStr(MY_MAC, 2166136261);
var txSeq = (typeof Math !== "undefined" && typeof Math.random === "function")
  ? ((Math.floor(Math.random() * 65534) + 1) & 0xffff)
  : 1;
var wifiDown = false;

// Dedup ring buffer for incoming (target_id, seq)
var DEDUP_CAP = 8;
var dedupIds = [];
var dedupSeqs = [];
var dedupIdx = 0;

function acceptSeq(id, seq) {
  for (var i = 0; i < dedupIds.length; i++) {
    if (dedupIds[i] === id && dedupSeqs[i] === seq) return false;
  }
  dedupIds[dedupIdx] = id;
  dedupSeqs[dedupIdx] = seq;
  dedupIdx = (dedupIdx + 1) % DEDUP_CAP;
  return true;
}

function nextSeq() {
  var s = txSeq;
  txSeq = (txSeq + 1) & 0xffff;
  if (txSeq === 0) txSeq = 1;
  return s;
}

// Detect device components (switch, light, cover, detached inputs)
var hasCover = false;
var switchChannels = [];
var lightChannels = [];
var detachedInputTypes = {};  // ch -> "switch" | "button"

function probeComponents() {
  var wifiSt = Shelly.getComponentStatus("wifi");
  wifiDown = !(wifiSt && wifiSt.status === "got ip");

  var cov0 = Shelly.getComponentStatus("cover", 0);
  if (cov0) {
    hasCover = true;
  }
  for (var ch = 0; ch < 2; ch++) {
    if (Shelly.getComponentStatus("switch", ch)) {
      switchChannels.push(ch);
    } else if (Shelly.getComponentStatus("light", ch)) {
      lightChannels.push(ch);
    }
    var inCfg = Shelly.getComponentConfig("input", ch);
    if (inCfg) {
      var swCfg = Shelly.getComponentConfig("switch", ch);
      var ltCfg = Shelly.getComponentConfig("light", ch);
      var isDetached =
        (swCfg && swCfg.in_mode === "detached") ||
        (ltCfg && ltCfg.in_mode === "detached") ||
        (!swCfg && !ltCfg && !hasCover);
      if (isDetached) {
        detachedInputTypes[ch] = inCfg.type || "switch";
      }
    }
  }
}

var advBurstTimer = null;
function advertiseBurst(uuidHex, payload14, repeats) {
  if (typeof BLE === "undefined" || typeof BLE.AdvBuilder === "undefined") return;
  BLE.AdvBuilder.reset();
  if (!BLE.AdvBuilder.addServiceData(uuidHex, payload14)) return;
  var pkt = BLE.AdvBuilder.build();
  if (!pkt) return;
  if (advBurstTimer !== null) {
    Timer.clear(advBurstTimer);
    advBurstTimer = null;
  }
  BLE.advertiseOnce(pkt, "");
  var rem = (typeof repeats === "number" && repeats > 1) ? (repeats - 1) : 2;
  advBurstTimer = Timer.set(60, true, function () {
    BLE.advertiseOnce(pkt, "");
    rem--;
    if (rem <= 0 && advBurstTimer !== null) {
      Timer.clear(advBurstTimer);
      advBurstTimer = null;
    }
  });
}

function sendBeacon(uuidHex, ch, kind, stateFlags, position, repeats) {
  var seq = nextSeq();
  var body =
    u32le(MY_ID) +
    String.fromCharCode(ch & 0xff, kind & 0xff, stateFlags & 0xff, position & 0xff) +
    u16le(seq);
  var tag = computeAuthTag(body);
  advertiseBurst(uuidHex, body + u32le(tag), repeats);
}

function broadcastCoverState(ch) {
  var st = Shelly.getComponentStatus("cover", ch);
  if (!st) return false;
  var pos = (typeof st.current_pos === "number") ? st.current_pos : 0;
  if (pos < 0) pos = 0;
  if (pos > 100) pos = 100;
  var motion = 0;
  if (st.state === "opening") motion = 1;
  else if (st.state === "closing") motion = 2;
  var isOpen = (pos > 0 || st.state === "open" || motion === 1) ? 1 : 0;
  var flags = (isOpen ? 1 : 0) | ((motion & 3) << 1) | (wifiDown ? 0x80 : 0);
  sendBeacon(UUID_STATE, ch, KIND_COVER, flags, pos);
  return motion !== 0;
}

function broadcastSwitchState(ch) {
  var st = Shelly.getComponentStatus("switch", ch);
  if (!st) st = Shelly.getComponentStatus("light", ch);
  if (!st) return;
  var isOn = st.output ? 1 : 0;
  var flags = (isOn ? 1 : 0) | (wifiDown ? 0x80 : 0);
  sendBeacon(UUID_STATE, ch, KIND_SWITCH, flags, 255);
}

function broadcastAllStates() {
  if (hasCover) {
    broadcastCoverState(0);
    return;
  }
  for (var i = 0; i < switchChannels.length; i++) {
    broadcastSwitchState(switchChannels[i]);
  }
  for (var j = 0; j < lightChannels.length; j++) {
    broadcastSwitchState(lightChannels[j]);
  }
}

// Cover motion periodic position updates
var coverMoveTimer = null;
function ensureCoverMovePolling(active) {
  if (active && coverMoveTimer === null) {
    coverMoveTimer = Timer.set(CFG.coverMovePollMs, true, function () {
      if (!broadcastCoverState(0)) {
        Timer.clear(coverMoveTimer);
        coverMoveTimer = null;
      }
    });
  } else if (!active && coverMoveTimer !== null) {
    Timer.clear(coverMoveTimer);
    coverMoveTimer = null;
  }
}

// Low-rate heartbeat timer (30s normal / 10s while wifiDown)
var heartbeatTimer = null;
function scheduleHeartbeat() {
  if (heartbeatTimer !== null) Timer.clear(heartbeatTimer);
  var ms = wifiDown ? CFG.heartbeatOfflineMs : CFG.heartbeatNormalMs;
  heartbeatTimer = Timer.set(ms, true, function () {
    broadcastAllStates();
  });
}

function handleCommand(ch, op, arg) {
  if (op === OP_QUERY_STATE) {
    if (hasCover) broadcastCoverState(ch);
    else broadcastSwitchState(ch);
    return;
  }
  if (op === OP_SW_OFF || op === OP_SW_ON || op === OP_SW_TOGGLE) {
    var useLight = (switchChannels.indexOf(ch) === -1 && lightChannels.indexOf(ch) !== -1);
    var prefix = useLight ? "Light" : "Switch";
    if (op === OP_SW_TOGGLE) {
      Shelly.call(prefix + ".Toggle", { id: ch });
    } else {
      Shelly.call(prefix + ".Set", { id: ch, on: op === OP_SW_ON });
    }
    return;
  }
  if (op === OP_COV_OPEN) {
    Shelly.call("Cover.Open", { id: ch });
  } else if (op === OP_COV_CLOSE) {
    Shelly.call("Cover.Close", { id: ch });
  } else if (op === OP_COV_STOP) {
    Shelly.call("Cover.Stop", { id: ch });
  } else if (op === OP_COV_POS) {
    var p = arg < 0 ? 0 : (arg > 100 ? 100 : arg);
    Shelly.call("Cover.GoToPosition", { id: ch, pos: p });
  }
}

function onScanResult(ev, res) {
  if (ev !== BLE.Scanner.SCAN_RESULT || !res || !res.service_data) return;
  var raw = res.service_data[UUID_CMD];
  if (!raw || raw.length !== 14) return;

  var targetId = readU32le(raw, 0);
  if (targetId !== MY_ID) return;

  var body10 = raw.slice(0, 10);
  var tag = readU32le(raw, 10);
  if (computeAuthTag(body10) !== tag) return;

  var seq = readU16le(raw, 8);
  if (!acceptSeq(targetId, seq)) return;

  var ch = raw.charCodeAt(4) & 0xff;
  var op = raw.charCodeAt(5) & 0xff;
  var arg = raw.charCodeAt(6) & 0xff;
  handleCommand(ch, op, arg);
}

// Status & event hooks
Shelly.addStatusHandler(function (ev) {
  if (!ev || !ev.component) return;
  if (ev.component === "wifi" && ev.delta && typeof ev.delta.status === "string") {
    var nextDown = (ev.delta.status !== "got ip");
    if (nextDown !== wifiDown) {
      wifiDown = nextDown;
      scheduleHeartbeat();
      broadcastAllStates();
    }
    return;
  }
  if (ev.component === "cover:0" && ev.delta && typeof ev.delta.state === "string") {
    var moving = broadcastCoverState(0);
    ensureCoverMovePolling(moving);
    return;
  }
  if ((ev.component.indexOf("switch:") === 0 || ev.component.indexOf("light:") === 0) &&
      ev.delta && typeof ev.delta.output === "boolean") {
    broadcastSwitchState(ev.id || 0);
    return;
  }
  if (ev.component.indexOf("input:") === 0 && ev.delta && typeof ev.delta.state === "boolean") {
    var ich = ev.id || 0;
    if (detachedInputTypes[ich] === "switch") {
      var flags = (ev.delta.state ? 1 : 0) | (wifiDown ? 0x80 : 0);
      sendBeacon(UUID_INPUT, ich, KIND_INPUT_TOGGLE, flags, 255, 6);
    }
  }
});

Shelly.addEventHandler(function (ev) {
  if (!ev || !ev.info || !ev.component) return;
  if (ev.component.indexOf("input:") === 0 && ev.info.event === "single_push") {
    var ich = ev.id || 0;
    if (detachedInputTypes[ich] === "button") {
      var flags = 1 | (wifiDown ? 0x80 : 0);
      sendBeacon(UUID_INPUT, ich, KIND_INPUT_TOGGLE, flags, 255, 6);
    }
  }
});

probeComponents();
scheduleHeartbeat();
broadcastAllStates();

if (typeof BLE !== "undefined" && typeof BLE.Scanner !== "undefined") {
  BLE.Scanner.Start(
    { duration_ms: BLE.Scanner.INFINITE_SCAN, active: false },
    onScanResult
  );
} else {
  print("CYD BLE backup: BLE.Scanner unavailable (Zigbee firmware?) - outbound beacons only");
}
