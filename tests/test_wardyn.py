"""Wardyn for HA's pure parts: the link copy's sealing (against the page's JavaScript), and the copy -> entities and alerts.
agent_line.json is what Wardyn Agent 2.11 itself makes of Wardyn's tour demo data (NetlineAgent --wardyn-ha, at AGENT_NOW);
the copies below put it where the agent does (HaModule.ToWardyn)."""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.model import BINARY, BUTTON, CONNECTIVITY, COUNT, EVENT, LATENCY, PRESENCE, PROBLEM
from core.parse import alerts, parse
from hpcrypto import SealError, keys_for, open_doc, seal_doc

HERE = Path(__file__).parent
AGENT = json.loads((HERE / "agent_line.json").read_text(encoding="utf-8"))
AGENT_NOW = 1793700000000
NOW = datetime.fromtimestamp(AGENT_NOW / 1000, tz=timezone.utc)
NODE, NET = "demo", "b0:19:21:c9:02:68"


def link(t=AGENT_NOW, controls=True, presence=(), newdevs=None, me=None, nets=None):
    n = dict(me if me is not None else AGENT["me"], t=t)
    w = nets if nets is not None else {k: dict(v, by=NODE, t=t) for k, v in AGENT["nets"].items()}
    return {"format": 1, "wardyn": 1, "name": "Wardyn", "by": "agents", "controls": controls, "state": {"v": 1, "nodes": {NODE: n}, "nets": w},
            "presence": list(presence), "newdevs": AGENT["newdevs"] if newdevs is None else newdevs, "requests": [], "done": {}}


# ---------- sealing ----------
def test_opens_the_pages_copy():
    v = json.loads((HERE / "vector.json").read_text(encoding="utf-8"))
    k = keys_for(v["code"])
    assert k.id == v["id"]
    assert open_doc(v["doc"], k)["wardyn"] == 1
    assert keys_for(v["code"].lower().replace("0", "o")).id == v["id"]   # typed loosely: the same code


def test_round_trip_and_wrong_code():
    k = keys_for("ABCD-EFGH-JKMN-PQRS-TVWX")
    assert open_doc(seal_doc({"wardyn": 1}, k), k) == {"wardyn": 1}
    with pytest.raises(SealError):
        open_doc(seal_doc({"wardyn": 1}, k), keys_for("ABCD-EFGH-JKMN-PQRS-TVWY"))
    assert keys_for("X").id != keys_for("X", "halink").id   # never the same copy as Appline's link


# ---------- entities ----------
def test_from_the_agent():
    p = parse(link(), NOW)
    t = p.things
    node, net = "node.demo", "net.b01921c90268"
    assert p.devices[node].name == "Office PC" and p.devices[node].via == "wardyn" and p.devices[net].name == "The network via 192.168.1.1"
    assert (t[f"{node}.connected"].platform, t[f"{node}.connected"].kind, t[f"{node}.connected"].state) == (BINARY, CONNECTIVITY, True)
    assert t[f"{node}.updates"].state == 4 and t[f"{node}.updates"].attrs["failed_lately"] == 1
    assert t[f"{node}.restart"].kind == PROBLEM and t[f"{node}.restart"].state is False
    assert t[f"{node}.checks"].attrs["failing"] == ["Disk space"]
    assert (t[f"{net}.latency"].kind, t[f"{net}.latency"].state) == (LATENCY, 9) and t[f"{net}.internet"].state is True
    assert t[f"{net}.devices"].state == 2 and t[f"{net}.outages"].state == 2
    assert t["wardyn.nodes"].state == 1 and t["wardyn.updates"].state == 4 and t["wardyn.problem"].state is False
    assert t["wardyn.issues"].kind == COUNT and t["wardyn.alerts"].platform == EVENT


def test_buttons_follow_controls_and_parts():
    t = parse(link(), NOW).things
    kinds = {x.data["kind"] for x in t.values() if x.platform == BUTTON}
    # the demo node runs av, devices, patch, speed (and others) but not checks
    assert kinds == {"update", "restart", "patch_scan", "install", "av_scan", "speed", "scan"}
    assert t["node.demo.btn.install"].data == {"node": NODE, "kind": "install"}
    assert not [x for x in parse(link(controls=False), NOW).things.values() if x.platform == BUTTON]


def test_presence():
    home = {"id": "aa:bb:cc:00:00:01", "name": "Sam’s phone", "last": AGENT_NOW - 5 * 60000, "ip": "192.168.1.77"}
    away = {"id": "aa:bb:cc:00:00:02", "name": "Laptop", "last": AGENT_NOW - 35 * 60000}
    t = parse(link(presence=[home, away]), NOW).things
    a, b = t["presence.aabbcc000001"], t["presence.aabbcc000002"]
    assert (a.platform, a.kind, a.state, a.placeholders["name"]) == (BINARY, PRESENCE, True, "Sam’s phone")
    assert b.state is False and t["wardyn.home"].state == 1


def test_quiet_node_and_old_reading():
    old = AGENT_NOW - 20 * 60000
    t = parse(link(t=old, nets={k: dict(v, by=NODE, t=old, at=old) for k, v in AGENT["nets"].items()}), NOW).things
    assert t["node.demo.connected"].state is False and t["net.b01921c90268.latency"].state is None
    serious = [i["what"] for i in t["wardyn.problem"].attrs["serious"]]
    assert t["wardyn.problem"].state is True and "No node is connected" in serious and "No recent reading" in serious


def test_not_a_link():
    for doc in (None, {}, {"link": 1}, {"wardyn": 2}):
        assert not parse(doc, NOW).things


# ---------- alerts ----------
def test_alerts():
    first = parse(link(), NOW)
    assert alerts(None, first.snapshot) == []   # nothing on the first look
    me = dict(AGENT["me"], threats=1, checks={"n": 3, "bad": ["Disk space", "Service up"], "warn": []})
    nets = {NET: dict(AGENT["nets"][NET], by=NODE, t=AGENT_NOW, up=False)}
    newer = dict(AGENT["newdevs"][0], t=AGENT["newdevs"][0]["t"] + 60000, mac="aa:aa:aa:aa:aa:09", name="Doorbell")
    second = parse(link(me=me, nets=nets, newdevs=[newer, *AGENT["newdevs"]]), NOW)
    got = alerts(first.snapshot, second.snapshot)
    kinds = [k for k, _ in got]
    assert kinds == ["threat_found", "check_failing", "internet_down", "new_device"]
    assert dict(got)["new_device"]["name"] == "Doorbell" and dict(got)["check_failing"]["check"] == "Service up"
    # and back again; then the node goes quiet
    third = parse(link(), NOW)
    assert [k for k, _ in alerts(second.snapshot, third.snapshot)] == ["internet_back"]
    quiet = parse(link(t=AGENT_NOW - 20 * 60000), NOW)
    assert ("node_offline", {"node": "Office PC"}) in alerts(third.snapshot, quiet.snapshot)
    assert ("node_back", {"node": "Office PC"}) in alerts(quiet.snapshot, third.snapshot)


def test_no_alerts_without_change():
    a = parse(link(), NOW)
    assert alerts(a.snapshot, parse(copy.deepcopy(link()), NOW).snapshot) == []
