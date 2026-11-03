"""Wardyn's link copy -> devices and entities, and the alerts between two of them. Pure Python (tested on its own).

The copy (made in Wardyn's Settings → Home Assistant, web/siteline/wardyn/hass.js; written by each Wardyn Agent 2.11+, the site repo's
agents/NetlineAgent/Home/HaModule.cs):
  { format: 1, wardyn: 1, name, by, controls,
    state: { v: 1, nodes: { agentId: { name, os, ver, t, nets, parts, upd?, sec?, held?, reboot?, failed?, threats?, av?, checks: { n, bad, warn } } },
             nets:  { netKey: { name, by, t, at?, up?, ms?, out24?, out7?, devs?, on? } } },
    presence: [{ id (hardware address), name, home, last, ip, net }],   (the devices tracked in Wardyn: Devices → 🏠 Track presence)
    newdevs: [{ t, mac, net, name, maker, ip }],                         (new on the networks in the last 7 days)
    requests: [{ id, t, node, kind, key?, value? }], done: { requestId: t },   (the controls here, and what the nodes have taken)
    cat: { v: 1, t, by, devs: [{ id, n, m, via }], ents: [{ id, p, d, n, s, u, dc, sc, ic, off, cat, a, o, min, max, step, w | do }] } }
  cat is Wardyn's catalogue (Wardyn Agent 2.13+, Home/Catalogue.cs): everything else Wardyn shows and every setting it has, described,
  so a new Wardyn feature appears here with no new integration. Its controls send { node: "*", kind: "set" | "press", key, value }.
A node writes its line at least every 5 minutes, so a line older than CONNECTED_FOR means it is off or can't reach the server.
Fields a node doesn't have (no Patches, no antivirus, a network it doesn't measure) are left out, and so are their entities; buttons only
while Wardyn lets Home Assistant control the nodes (controls), and only for the parts a node has on.
Devices here (0.3.0; the user: "I was expecting just the 3 nodes I had to list all the things they could do and see"): one per node, with
everything it does and sees, its network included (the node that measures it); and Wardyn's own, for what's Wardyn-wide (issues, alerts,
tracked devices, and Wardyn's settings, check library and plans as configuration). The gadgets on a network are a list in the node's
Devices online, not devices of their own.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .model import (ALERTS, BINARY, BUTTON, CAT, CONNECTIVITY, COUNT, EVENT, LATENCY, NUMBER, PRESENCE, PRESS, PROBLEM, SELECT, SENSOR,
                    SWITCH, TIMESTAMP, Device, Parsed, Thing)

ROOT = "wardyn"
CONNECTED_FOR = timedelta(minutes=15)
HOME_FOR = timedelta(minutes=20)   # as Wardyn Agent (Devices/DevicesModule.cs HomeFor)
# the buttons: kind (what the node is asked), the part it needs on (None: every node), translation key, icon
BUTTONS = [("update", None, "node_update", "mdi:update"), ("restart", None, "node_restart_agent", "mdi:restart"),
           ("patch_scan", "patch", "node_patch_scan", "mdi:package-variant-closed-check"), ("install", "patch", "node_install", "mdi:package-down"),
           ("checks", "checks", "node_run_checks", "mdi:clipboard-play-outline"), ("av_scan", "av", "node_av_scan", "mdi:shield-search"),
           ("speed", "speed", "node_speed_test", "mdi:speedometer"), ("scan", "devices", "node_scan_devices", "mdi:radar")]
# Wardyn's issue levels (sitetools.html ISSUE_KINDS, siteline_severity_v1): 3 serious, 2 worth a look, 1 note, 0 not shown
LEVELS = {3: "serious", 2: "worth a look", 1: "note"}


def issue(kind: str, lvl: int, area: str, what: str, where: str, iid: str | None = None) -> dict:
    """One of Wardyn's issues, in Wardyn's own words, with the key Wardyn dismisses it by (sitetools.html issueKey)."""
    return {"kind": kind, "lvl": lvl, "what": what, "where": where, "key": iid or "|".join([area, where, re.sub(r"[\d.]+", "#", what)])}


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

    for k, n in sorted(nodes.items()):
        out.add_device(Device(f"node.{slug(k)}", names[k], "Node" + (f" · {n['os']}" if isinstance(n.get("os"), str) else ""), via=ROOT))
    # a network goes on the node that measured it last (Wardyn's own device if that node isn't here); named only where a node has several
    snap["netdev"] = {}
    per_node: dict[str, int] = {}
    for k, n in nets.items():
        d = f"node.{slug(n.get('by'))}" if n.get("by") in nodes else ROOT
        snap["netdev"][slug(k)] = d
        per_node[d] = per_node.get(d, 0) + 1

    # ---- networks ----
    for k, n in sorted(nets.items()):
        dev, name = snap["netdev"][slug(k)], str(n.get("name") or "A network")
        many = per_node[dev] > 1 or dev == ROOT
        key = f"net.{slug(k)}"
        named = (lambda label: f"{name}: {label}") if many else (lambda label: None)
        measured = _at(n.get("at"), tz)
        attrs = {"network": k, "measured": measured.isoformat() if measured else None, "by": names.get(n.get("by"))}
        up = None
        if isinstance(n.get("up"), bool):
            # (a measurement over 15 minutes old says nothing about now: the node measuring it has gone quiet)
            up = n["up"] and measured is not None and now - measured <= CONNECTED_FOR
            out.add(Thing(f"{key}.internet", dev, BINARY, CONNECTIVITY, "net_internet", up, {}, attrs, "mdi:web" if up else "mdi:web-off", name=named("Internet")))
            if not up:
                issues.append(issue("down", 3, "Health", "The internet isn’t answering", name) if n["up"] is False else issue("noreadings", 2, "Health", "No readings lately", name))
            out.add(Thing(f"{key}.latency", dev, SENSOR, LATENCY, "net_latency", _num(n.get("ms")) if up else None, {}, {}, "mdi:timer-outline", name=named("Internet latency")))
            o24, o7 = _num(n.get("out24")) or 0, _num(n.get("out7")) or 0
            out.add(Thing(f"{key}.outages", dev, SENSOR, COUNT, "net_outages", o24, {}, {"last_7_days": o7}, "mdi:lan-disconnect", name=named("Outages (24 hours)")))
            if o24:
                issues.append(issue("outages", 2, "Health", f"{o24} outage{'s' if o24 != 1 else ''} in the last day", name))
        if _num(n.get("devs")) is not None:
            out.add(Thing(f"{key}.devices", dev, SENSOR, COUNT, "net_devices_online", _num(n.get("on")) or 0, {}, {"known": n["devs"]}, "mdi:devices", name=named("Devices online")))
        snap["nets"][k] = {"name": name, "up": up}

    # ---- nodes ----
    waiting = security = 0
    for k, n in sorted(nodes.items()):
        dev, name, on = f"node.{slug(k)}", names[k], connected[k]
        seen = _at(n.get("t"), tz)
        out.add(Thing(f"{dev}.connected", dev, BINARY, CONNECTIVITY, "node_connected", on, {},
                      {"version": n.get("ver"), "last_seen": seen.isoformat() if seen else None}, "mdi:lan-connect" if on else "mdi:lan-disconnect"))
        out.add(Thing(f"{dev}.seen", dev, SENSOR, TIMESTAMP, "node_last_seen", seen, {}, {}, "mdi:clock-check-outline", enabled=False))
        if not on:
            issues.append(issue("quiet", 2, "Computers", "Not reporting", name))
        if _num(n.get("upd")) is not None:
            u, s = int(n["upd"]), int(_num(n.get("sec")) or 0)
            waiting += u; security += s
            out.add(Thing(f"{dev}.updates", dev, SENSOR, COUNT, "node_updates", u, {},
                          {"security": s, "held_or_put_off": _num(n.get("held")) or 0, "failed_lately": _num(n.get("failed")) or 0}, "mdi:package-up"))
            out.add(Thing(f"{dev}.restart", dev, BINARY, PROBLEM, "node_restart", bool(n.get("reboot")), {}, {}, "mdi:restart-alert"))
            if s:
                issues.append(issue("security", 2, "Patches", f"{s} security update{'s' if s != 1 else ''} waiting", name))
            if n.get("reboot"):
                issues.append(issue("reboot", 2, "Patches", "Restart needed to finish updates", name))
            if _num(n.get("failed")):
                issues.append(issue("failed", 2, "Patches", f"{n['failed']} update{'s' if n['failed'] != 1 else ''} failed to install", name))
        threats = None
        if _num(n.get("threats")) is not None:
            threats = int(n["threats"])
            out.add(Thing(f"{dev}.threats", dev, SENSOR, COUNT, "node_threats", threats, {}, {"antivirus_on": n.get("av")},
                          "mdi:shield-bug-outline" if threats else "mdi:shield-check-outline"))
            if threats:
                issues.append(issue("threat", 3, "Security", f"{threats} threat{'s' if threats != 1 else ''} found", name))
        c = n.get("checks") if isinstance(n.get("checks"), dict) else {}
        bad = [x for x in c.get("bad") or [] if isinstance(x, str)]
        if _num(c.get("n")):
            warn = [x for x in c.get("warn") or [] if isinstance(x, str)]
            out.add(Thing(f"{dev}.checks", dev, SENSOR, COUNT, "node_checks_failing", len(bad), {}, {"failing": bad, "warnings": warn, "checks": c["n"]},
                          "mdi:clipboard-alert-outline" if bad else "mdi:clipboard-check-outline"))
            ids = [x for x in c.get("badIds") or [] if isinstance(x, str)]
            issues.extend(issue("checkfail", 2, "Checks", f"{b}: failing", name, f"chk|{k}|{ids[i]}" if i < len(ids) else None) for i, b in enumerate(bad))
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
        issues.insert(0, issue("quiet", 3, "Computers", "No node is connected", "Wardyn"))
    # as Wardyn shows them: your issue levels (0: not shown), and what you dismissed there left out
    levels = doc.get("levels") if isinstance(doc.get("levels"), dict) else {}
    dismissed = {x for x in doc.get("dismissed") or [] if isinstance(x, str)}
    shown = []
    for i in issues:
        lvl = levels.get(i["kind"], i["lvl"])
        lvl = lvl if isinstance(lvl, int) and not isinstance(lvl, bool) and 0 <= lvl <= 3 else i["lvl"]
        if lvl and i["key"] not in dismissed:
            shown.append({"level": LEVELS[lvl], "what": i["what"], "where": i["where"], "kind": i["kind"]})
    issues = sorted(shown, key=lambda i: ["serious", "worth a look", "note"].index(i["level"]))
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

    catalogue(doc.get("cat"), controls, out, tz, snap["netdev"])

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


CAT_PLATFORMS = {"sensor": SENSOR, "binary_sensor": BINARY, "switch": SWITCH, "select": SELECT, "number": NUMBER, "button": BUTTON}
CONTROLS = {SWITCH, SELECT, NUMBER, BUTTON}


def catalogue(cat: Any, controls: bool, out: Parsed, tz, netdev: dict[str, str] | None = None) -> None:
    """Wardyn's catalogue -> things (keys "c.<id>") on the nodes and Wardyn's own device: a network's go on the node that measures it,
    Wardyn-wide ones (settings, checks, plans, uptime) on Wardyn's; the gadgets on a network (the catalogue's "dev.*") become a list in
    that network's Devices online. Controls only while Wardyn lets Home Assistant change things."""
    if not isinstance(cat, dict) or cat.get("v") != 1:
        return
    netdev = netdev or {}
    names = {d["id"]: str(d.get("n") or d["id"]) for d in cat.get("devs") or [] if isinstance(d, dict) and isinstance(d.get("id"), str)}
    via = {d["id"]: d.get("via") for d in cat.get("devs") or [] if isinstance(d, dict) and isinstance(d.get("id"), str)}
    gadgets: dict[str, list] = {}

    def place(d: Any) -> str | None:
        d = str(d or "")
        if d.startswith("node."):
            return d if d in out.devices else None
        if d.startswith("net."):
            return netdev.get(d[4:], ROOT)
        return None if d.startswith("dev.") else ROOT

    for e in cat.get("ents") or []:
        if not isinstance(e, dict) or not isinstance(e.get("id"), str):
            continue
        d = str(e.get("d") or "")
        if d.startswith("dev."):
            if e.get("p") == "binary_sensor" and e["id"].endswith(".online"):
                a = e.get("a") or {}
                gadgets.setdefault(str(via.get(d) or ""), []).append({"name": names.get(d, a.get("hardware_address")), "online": bool(e.get("s")), "ip": a.get("ip"),
                                                                        "maker": a.get("maker"), "hardware_address": a.get("hardware_address"), "known": a.get("known")})
            continue
        platform, dev = CAT_PLATFORMS.get(e.get("p")), place(d)
        if platform is None or dev is None or (platform in CONTROLS and not controls):
            continue
        state = e.get("s")
        if e.get("dc") == "timestamp":
            state = _at(state, tz)
        meta = {k: e[k] for k in ("u", "dc", "sc", "cat", "o", "min", "max", "step") if k in e}
        if dev == ROOT and not d.startswith("net.") and d not in ("", ROOT) and platform in (SENSOR, BINARY) and "cat" not in meta:
            meta["cat"] = "diagnostic"   # (Wardyn-wide readings beside its settings: kept out of the way)
        out.add(Thing(f"c.{e['id']}", dev, platform, CAT, "", state, {}, dict(e.get("a") or {}), e.get("ic"),
                      data={"key": e["id"]} if platform in CONTROLS else None, enabled=not e.get("off"), name=str(e.get("n") or e["id"]), meta=meta))
    for net, items in gadgets.items():
        t = out.things.get(f"{net}.devices")
        if t is not None:
            items.sort(key=lambda x: (not x["online"], str(x["name"] or "").lower()))
            t.attrs["devices"] = items[:200]
