"""Wardyn's link copy -> devices and entities, and the alerts between two of them. Pure Python (tested on its own).

The copy (made in Wardyn's Settings → Home Assistant, web/siteline/wardyn/hass.js; written by each Wardyn Agent 2.11+, the site repo's
agents/NetlineAgent/Home/HaModule.cs):
  { format: 1, wardyn: 1, name, by, controls,
    state: { v: 1, nodes: { agentId: { name, os, ver, t, nets, parts, upd?, sec?, held?, reboot?, failed?, threats?, av?, checks: { n, bad, warn } } },
             nets:  { netKey: { name, by, t, at?, up?, ms?, out24?, out7?, devs?, on? } } },
    presence: [{ id (hardware address), name, home, last, ip, net }],   (the devices tracked in Wardyn: Devices → 🏠 Track presence)
    newdevs: [{ t, mac, net, name, maker, ip }],                         (new on the networks in the last 7 days)
    requests: [{ id, t, node, kind }], done: { requestId: t } }           (the buttons here, and what the nodes have taken)
A node writes its line at least every 5 minutes, so a line older than CONNECTED_FOR means it is off or can't reach the server.
Fields a node doesn't have (no Patches, no antivirus, a network it doesn't measure) are left out, and so are their entities; buttons only
while Wardyn lets Home Assistant control the nodes (controls), and only for the parts a node has on.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .model import (ALERTS, BINARY, BUTTON, CONNECTIVITY, COUNT, EVENT, LATENCY, PRESENCE, PRESS, PROBLEM, SENSOR, TIMESTAMP,
                    Device, Parsed, Thing)

ROOT = "wardyn"
CONNECTED_FOR = timedelta(minutes=15)
HOME_FOR = timedelta(minutes=20)   # as Wardyn Agent (Devices/DevicesModule.cs HomeFor)
# the buttons: kind (what the node is asked), the part it needs on (None: every node), translation key, icon
BUTTONS = [("update", None, "node_update", "mdi:update"), ("restart", None, "node_restart_agent", "mdi:restart"),
           ("patch_scan", "patch", "node_patch_scan", "mdi:package-variant-closed-check"), ("install", "patch", "node_install", "mdi:package-down"),
           ("checks", "checks", "node_run_checks", "mdi:clipboard-play-outline"), ("av_scan", "av", "node_av_scan", "mdi:shield-search"),
           ("speed", "speed", "node_speed_test", "mdi:speedometer"), ("scan", "devices", "node_scan_devices", "mdi:radar")]
ALERT_TYPES = ["node_offline", "node_back", "internet_down", "internet_back", "new_device", "threat_found", "check_failing"]


def slug(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())[:40] or "x"


def _num(v) -> int | float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _at(v, tz) -> datetime | None:
    n = _num(v)
    return datetime.fromtimestamp(n / 1000, tz=tz) if n and n > 0 else None


def is_link(doc: Any) -> bool:
    return isinstance(doc, dict) and doc.get("wardyn") == 1


def parse(doc: Any, now: datetime) -> Parsed:
    out = Parsed()
    if not is_link(doc):
        return out
    tz = now.tzinfo
    state = doc.get("state") if isinstance(doc.get("state"), dict) else {}
    nodes = {k: v for k, v in (state.get("nodes") or {}).items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(state.get("nodes"), dict) else {}
    nets = {k: v for k, v in (state.get("nets") or {}).items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(state.get("nets"), dict) else {}
    controls = doc.get("controls") is True
    out.add_device(Device(ROOT, "Wardyn", "Network monitor"))
    issues: list[dict] = []
    snap: dict[str, Any] = {"nodes": {}, "nets": {}, "newdev_t": 0}
    connected = {k: (lambda at: at is not None and now - at <= CONNECTED_FOR)(_at(n.get("t"), tz)) for k, n in nodes.items()}
    names = {k: str(n.get("name") or "A node") for k, n in nodes.items()}

    # ---- networks ----
    for k, n in sorted(nets.items()):
        dev, name = f"net.{slug(k)}", str(n.get("name") or "A network")
        out.add_device(Device(dev, name, "Network", via=ROOT))
        measured = _at(n.get("at"), tz)
        attrs = {"network": k, "measured": measured.isoformat() if measured else None, "by": names.get(n.get("by"))}
        up = None
        if isinstance(n.get("up"), bool):
            # (a measurement over 15 minutes old says nothing about now: the node measuring it has gone quiet)
            up = n["up"] and measured is not None and now - measured <= CONNECTED_FOR
            out.add(Thing(f"{dev}.internet", dev, BINARY, CONNECTIVITY, "net_internet", up, {}, attrs, "mdi:web" if up else "mdi:web-off"))
            if not up:
                issues.append({"level": "serious", "what": "Internet down" if n["up"] is False else "No recent reading", "where": name})
            out.add(Thing(f"{dev}.latency", dev, SENSOR, LATENCY, "net_latency", _num(n.get("ms")) if up else None, {}, {}, "mdi:timer-outline"))
            o24, o7 = _num(n.get("out24")) or 0, _num(n.get("out7")) or 0
            out.add(Thing(f"{dev}.outages", dev, SENSOR, COUNT, "net_outages", o24, {}, {"last_7_days": o7}, "mdi:lan-disconnect"))
            if o24:
                issues.append({"level": "worth a look", "what": f"{o24} outage{'s' if o24 != 1 else ''} in the last day", "where": name})
        if _num(n.get("devs")) is not None:
            out.add(Thing(f"{dev}.devices", dev, SENSOR, COUNT, "net_devices_online", _num(n.get("on")) or 0, {}, {"known": n["devs"]}, "mdi:devices"))
        snap["nets"][k] = {"name": name, "up": up}

    # ---- nodes ----
    waiting = security = 0
    for k, n in sorted(nodes.items()):
        dev, name, on = f"node.{slug(k)}", names[k], connected[k]
        out.add_device(Device(dev, name, "Node" + (f" · {n['os']}" if isinstance(n.get("os"), str) else ""), via=ROOT))
        seen = _at(n.get("t"), tz)
        out.add(Thing(f"{dev}.connected", dev, BINARY, CONNECTIVITY, "node_connected", on, {},
                      {"version": n.get("ver"), "last_seen": seen.isoformat() if seen else None}, "mdi:lan-connect" if on else "mdi:lan-disconnect"))
        out.add(Thing(f"{dev}.seen", dev, SENSOR, TIMESTAMP, "node_last_seen", seen, {}, {}, "mdi:clock-check-outline", enabled=False))
        if not on:
            issues.append({"level": "worth a look", "what": "Not reporting", "where": name})
        if _num(n.get("upd")) is not None:
            u, s = int(n["upd"]), int(_num(n.get("sec")) or 0)
            waiting += u; security += s
            out.add(Thing(f"{dev}.updates", dev, SENSOR, COUNT, "node_updates", u, {},
                          {"security": s, "held_or_put_off": _num(n.get("held")) or 0, "failed_lately": _num(n.get("failed")) or 0}, "mdi:package-up"))
            out.add(Thing(f"{dev}.restart", dev, BINARY, PROBLEM, "node_restart", bool(n.get("reboot")), {}, {}, "mdi:restart-alert"))
            if s:
                issues.append({"level": "worth a look", "what": f"{s} security update{'s' if s != 1 else ''} waiting", "where": name})
            if n.get("reboot"):
                issues.append({"level": "worth a look", "what": "Restart needed to finish updates", "where": name})
            if _num(n.get("failed")):
                issues.append({"level": "worth a look", "what": f"{n['failed']} update{'s' if n['failed'] != 1 else ''} failed to install", "where": name})
        threats = None
        if _num(n.get("threats")) is not None:
            threats = int(n["threats"])
            out.add(Thing(f"{dev}.threats", dev, SENSOR, COUNT, "node_threats", threats, {}, {"antivirus_on": n.get("av")},
                          "mdi:shield-bug-outline" if threats else "mdi:shield-check-outline"))
            if threats:
                issues.append({"level": "serious", "what": f"{threats} active threat{'s' if threats != 1 else ''}", "where": name})
        c = n.get("checks") if isinstance(n.get("checks"), dict) else {}
        bad = [x for x in c.get("bad") or [] if isinstance(x, str)]
        if _num(c.get("n")):
            warn = [x for x in c.get("warn") or [] if isinstance(x, str)]
            out.add(Thing(f"{dev}.checks", dev, SENSOR, COUNT, "node_checks_failing", len(bad), {}, {"failing": bad, "warnings": warn, "checks": c["n"]},
                          "mdi:clipboard-alert-outline" if bad else "mdi:clipboard-check-outline"))
            issues.extend({"level": "worth a look", "what": f"Check failing: {b}", "where": name} for b in bad)
        if controls:
            parts = {p for p in n.get("parts") or [] if isinstance(p, str)}
            for kind, part, tk, icon in BUTTONS:
                if part is None or part in parts:
                    out.add(Thing(f"{dev}.btn.{kind}", dev, BUTTON, PRESS, tk, None, {}, {}, icon, data={"node": k, "kind": kind}))
        snap["nodes"][k] = {"name": name, "on": on, "threats": threats or 0, "bad": sorted(bad)}

    # ---- tracked devices: home or away ----
    pres = [p for p in doc.get("presence") or [] if isinstance(p, dict) and isinstance(p.get("id"), str)]
    home = 0
    for p in pres:
        at = _at(p.get("last"), tz)
        h = at is not None and now - at <= HOME_FOR
        home += h
        out.add(Thing(f"presence.{slug(p['id'])}", ROOT, BINARY, PRESENCE, "device_home", h, {"name": str(p.get("name") or "Device")},
                      {"last_seen": at.isoformat() if at else None, "ip": p.get("ip"), "hardware_address": p["id"]},
                      "mdi:home-account" if h else "mdi:home-export-outline"))
    if pres:
        out.add(Thing(f"{ROOT}.home", ROOT, SENSOR, COUNT, "devices_home", home, {}, {}, "mdi:home-group"))

    # ---- Wardyn as a whole ----
    if nodes and not any(connected.values()):
        issues.insert(0, {"level": "serious", "what": "No node is connected", "where": "Wardyn"})
    issues.sort(key=lambda i: i["level"] != "serious")
    out.add(Thing(f"{ROOT}.issues", ROOT, SENSOR, COUNT, "wardyn_issues", len(issues), {}, {"issues": issues[:40]},
                  "mdi:alert-circle-outline" if issues else "mdi:check-circle-outline"))
    serious = [i for i in issues if i["level"] == "serious"]
    out.add(Thing(f"{ROOT}.problem", ROOT, BINARY, PROBLEM, "wardyn_problem", bool(serious), {}, {"serious": serious[:20]},
                  "mdi:shield-alert-outline" if serious else "mdi:shield-check-outline"))
    if nodes:
        out.add(Thing(f"{ROOT}.nodes", ROOT, SENSOR, COUNT, "wardyn_nodes_connected", sum(connected.values()), {},
                      {"nodes": len(nodes), "not_connected": [names[k] for k, v in connected.items() if not v]}, "mdi:server-network"))
    if any(_num(n.get("upd")) is not None for n in nodes.values()):
        out.add(Thing(f"{ROOT}.updates", ROOT, SENSOR, COUNT, "wardyn_updates", waiting, {}, {"security": security}, "mdi:package-up"))
    out.add(Thing(f"{ROOT}.alerts", ROOT, EVENT, ALERTS, "wardyn_alerts", None, {}, {}, "mdi:bell-ring-outline"))

    newdevs = [d for d in doc.get("newdevs") or [] if isinstance(d, dict) and _num(d.get("t"))]
    snap["newdev_t"] = max((d["t"] for d in newdevs), default=0)
    snap["newdevs"] = newdevs
    out.snapshot = snap
    return out


def alerts(prev: dict | None, cur: dict) -> list[tuple[str, dict]]:
    """What changed between two snapshots, as alerts (event type, details). Nothing on the first look (prev None)."""
    if not prev or not cur:
        return []
    out: list[tuple[str, dict]] = []
    for k, n in cur.get("nodes", {}).items():
        p = prev.get("nodes", {}).get(k)
        if p is None:
            continue
        if p["on"] and not n["on"]:
            out.append(("node_offline", {"node": n["name"]}))
        elif not p["on"] and n["on"]:
            out.append(("node_back", {"node": n["name"]}))
        if n["threats"] > p["threats"]:
            out.append(("threat_found", {"node": n["name"], "threats": n["threats"]}))
        for b in sorted(set(n["bad"]) - set(p["bad"])):
            out.append(("check_failing", {"node": n["name"], "check": b}))
    for k, n in cur.get("nets", {}).items():
        p = prev.get("nets", {}).get(k)
        if p is None or p["up"] is None or n["up"] is None:
            continue
        if p["up"] and not n["up"]:
            out.append(("internet_down", {"network": n["name"]}))
        elif not p["up"] and n["up"]:
            out.append(("internet_back", {"network": n["name"]}))
    seen = prev.get("newdev_t", 0)
    nets = cur.get("nets", {})
    for d in sorted(cur.get("newdevs", []), key=lambda d: d["t"]):
        if d["t"] > seen:
            out.append(("new_device", {"name": d.get("name") or d.get("maker") or "Unknown device", "maker": d.get("maker"), "ip": d.get("ip"),
                                       "hardware_address": d.get("mac"), "network": (nets.get(d.get("net")) or {}).get("name")}))
    return out
