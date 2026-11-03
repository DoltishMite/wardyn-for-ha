# Wardyn for HA: design notes

For whoever changes this next: read it first.

## Decisions (2026-11-03, with the owner)
- **Its own integration**, not part of Appline for HA: domain `wardyn`, name "Wardyn for HA", repo `DoltishMite/wardyn-for-ha` (public: HACS).
  Minimum HA 2025.8 (as Appline's).
- **Its own link code**, made in Wardyn (Settings → Home Assistant, the site repo's `web/siteline/wardyn/hass.js`), "so you can share
  that independently": not the sync code and not Appline's link. Saved synced as `siteline_halink_v1 { on, code, controls, at }`, so the
  nodes see it; Wardyn's sharing never passes it on (agents `Share/ShareRules.cs` lists the keys a share gets).
- **Features:** sidebar panel, sensors per network and node, presence (tracked devices home/away), controls (buttons), alerts as events.
- **Controls** only while Wardyn allows them (`controls`, a tick box in Wardyn's Settings → Home Assistant; on when connecting, unless
  unticked). Anyone with the code can press the buttons: the page says so where it shows the code.

## How it works
```
Wardyn page ── makes ──▶ link copy (/api/sync, "wardyn-" keys) ◀── each Wardyn Agent writes its line (state, presence, new devices) ─┐
                               │  ▲                                                                                              │
         GET + wss /api/live ──┘  └── PUT requests [{ id, t, node, kind }] (a button) ── node takes it within 20 s, marks done ──┘
```
- Sealing: `hpcrypto.py` (kind "wardyn"); the page's JavaScript makes the test vector (`tests/make_vector.mjs` → `tests/vector.json`).
- The copy's shape and the agents' part: `core/parse.py`'s top comment and the site repo's `agents/NetlineAgent/Home/HaModule.cs`.
- `core/` is pure Python (no HA imports): `pytest tests`. `tests/agent_line.json` is the agent's real output for Wardyn's tour data
  (`NetlineAgent --wardyn-ha <synced copy> <node id> <now ms>`).
- A request is marked done in the link copy (and in the node's settings) **before** the node acts: a restart or an update ends the
  agent straight after, and the next run must not do it again (seen in testing, 2026-11-03).
- Alerts: `core/parse.alerts(previous, current)` compares two snapshots (never on the first look); the coordinator runs it on every
  build (a live change, a pull, the minute tick) and fires the event entity and `wardyn_alert`.
- The server lets a Home Assistant client in by `X-Appline-Client: ha/<version>` (the same rule as Appline's; read, save over an
  existing copy, watch). Only the page makes or deletes the copy.

## The catalogue (0.2.0, Wardyn Agent 2.13)
The user asked for "all of Wardyn's info … surfaced and controllable … every feature Wardyn has and will have", and chose a
self-describing design: Wardyn Agent publishes `cat` (the site repo's `agents/NetlineAgent/Home/Catalogue.cs`) and `core/parse.catalogue`
turns each entry into a Thing (key `c.<id>`, kind CAT, its name, unit, device class, options and limits in `meta`). switch / select /
number / button send `{ node: "*", kind: "set" | "press", key, value }`; the keeper node checks it against the catalogue it builds itself
and makes the change in the synced copy. The state changes here at once (optimistic) until the next catalogue. Controls only while the
copy's `controls` is true. Entries for a platform or device this version doesn't know are skipped, so the agent can add new kinds first.
Uptime results are in the agent but need the server to let a node read its list (not yet).

## Entities (keys; unique_id `<entry id>_<key>`)
| Device | Key | Entity | translation_key |
|---|---|---|---|
| Wardyn (`wardyn`) | `wardyn.issues` / `.problem` / `.nodes` / `.updates` / `.home` / `.alerts` | count / problem / count / count / count / event | `wardyn_issues`, `wardyn_problem`, `wardyn_nodes_connected`, `wardyn_updates`, `devices_home`, `wardyn_alerts` |
| | `presence.<hardware address>` | presence | `device_home` (`{name}`) |
| a network (`net.<router MAC>`) | `….internet` / `.latency` / `.outages` / `.devices` | connectivity / ms / count / count | `net_internet`, `net_latency`, `net_outages`, `net_devices_online` |
| a node (`node.<node id>`) | `….connected` / `.seen` / `.updates` / `.restart` / `.threats` / `.checks` | connectivity / timestamp / count / problem / count / count | `node_*` |
| | `….btn.<kind>` | button: update, restart, patch_scan, install, checks, av_scan, speed, scan | `node_update` … |

## Changelog
- 0.2.0 (2026-11-03): Wardyn's catalogue: every network device, node detail and setting, with switches, selects and numbers (needs Wardyn Agent 2.13).
- 0.1.0 (2026-11-03): first version (needs Wardyn Agent 2.11).
