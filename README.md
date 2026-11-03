# Wardyn for HA

[Wardyn](https://wardyn.hedgepig.uk/) in Home Assistant: your networks and nodes as devices and sensors, alerts for automations, the
devices you track home or away, buttons to update, restart and scan your nodes, and Wardyn in the sidebar.

It has a link code of its own, made in Wardyn: not your sync code, and not Appline's Home Assistant link. You can give it to a Home
Assistant on its own, and take it back any time.

## What you get

| Device | Entities |
|---|---|
| **Wardyn** | **Issues** (the list in its attributes), **Problem** (anything serious: internet down, active threats, no node connected), **Nodes connected**, **Updates waiting**, **Devices at home**, each tracked device **home or away**, and **Alerts** |
| **each network** | **Internet** (connected), **Internet latency**, **Outages (24 hours)**, **Devices online** |
| **each node** | **Connected**, **Updates waiting**, **Restart needed**, **Active threats**, **Checks failing**, **Last check-in** (off at first), and buttons: **Update Wardyn Agent**, **Restart Wardyn Agent**, **Look for updates**, **Install updates**, **Run checks**, **Quick antivirus scan**, **Speed test**, **Scan for devices** (only those the node's parts can answer) |

**Everything else Wardyn has** (Wardyn Agent 2.13 or later), drawn from Wardyn's own description of itself, so new Wardyn features
appear here when your nodes update, with no new integration:
- **every device on your networks** as its own device: **Online**, **Wake**, and (off at first) address, last seen, open ports, and
  switches for **Known**, **Hidden in Wardyn**, **Track presence**
- **each node**: its parts as switches, its **Group**, scan and speed test settings, processor, memory, disks, system details, the
  updates waiting by name, antivirus state and scans, each check, **Restart the computer**
- **each network**: router, ISP and DNS latency, lost pings, jitter, public address, traffic now, line speeds, UPnP forwards, the last speed test
- the **check library** and **maintenance plans** as switches, and **Wardyn settings**: outage thresholds, issue levels, speed test
  server and package, uptime checks

Switches, selects, numbers and buttons only appear while Wardyn lets Home Assistant control your nodes. Each change is made by one of
your nodes within about 20 seconds, exactly as if you'd made it in Wardyn.

**Alerts** is an event entity: *a node stopped reporting*, *a node is back*, *internet down*, *internet back*, *new device*, *threat
found*, *check failing*. Trigger an automation on it (the type is in `event_type`), or on the `wardyn_alert` event on the bus.

Each Wardyn Agent (2.11 or later) sends its own state every few minutes, so everything stays current with no Wardyn page open. A node
that hasn't sent anything for 15 minutes shows as not connected.

## Install

1. HACS → ⋮ → Custom repositories → `https://github.com/DoltishMite/wardyn-for-ha`, type **Integration** → Download, then restart Home Assistant.
2. In Wardyn: **Settings → Home Assistant → Connect to Home Assistant**. Choose whether Home Assistant may control your nodes.
3. In Home Assistant: **Settings → Devices & services → Add integration → Wardyn for HA**, and type the code in.

Made a new code in Wardyn (↻ New code)? Use **Reconfigure** on the integration: everything stays. **Configure** switches the sidebar panel.
The sidebar panel works when Home Assistant is opened at its `https://…hedgepig.uk` address.

## Privacy

The link copy is sealed with the link code before it leaves your nodes: the server stores only ciphertext. Home Assistant keeps the code
in its configuration (`.storage` on your Home Assistant machine) and never logs it; diagnostics leave it out. Anyone with the code sees
your networks and nodes and, if you allowed it in Wardyn, can press the buttons. Disconnect in Wardyn and the copy is deleted.
