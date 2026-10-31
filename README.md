# surface-ir-face-unlock

Windows Hello-style face unlock on **Microsoft Surface Pro 6** (verified) — should
also apply to other IPU3/OV7251 devices (SP5, SP7 etc.).

Uses [howdy-next](https://codeberg.org/nathawat/howdy-next) (C++ rewrite of Howdy) +
v4l2loopback. Hardware path: OV7251 IR sensor → Intel IPU3 → raw ip3y → C bridge →
`/dev/video42` → PAM. IR emitter driven by direct I2C write (`0x3005=0x08`) — works
in total darkness.

Forked/adapted from **[lksmasin/surface-howdy-sp5](https://github.com/lksmasin/surface-howdy-sp5)**
(Surface Pro 5 version). Changes vs upstream:

- ported/verified on Surface Pro 6
- `IR_BRIDGE_LIFETIME_SEC` env: configurable self-timeout (15s auth / 8h preview)
- `PR_SET_PDEATHSIG`: bridge dies with parent (crash/kill/logout safe)
- LED-fail fallback: keeps outputting frames when I2C strobe fails (daylight use)
- `WARMUP_FRAMES` 5→3 + ALS-adaptive exposure/gain (3 bands)
- per-auth media-graph re-link in `ir_bridge_run.sh` (survives libcamera resets)
- GTK4 enroll/manage UI with preview, face guide circle, model list/remove

## Features

- On-demand camera: spawns only during auth, self-cleans via PDEATHSIG + lifetime cap
- Native PAM module — no pam-python privilege quirks
- Coverage: sudo, su, polkit, GDM login, GNOME lock screen — password always falls back
- Management UI (`face-enroll.py`): live preview, Windows Hello-style guide, enroll/remove

## Install

Requires howdy-next (build from source on Ubuntu 24.04 — see `docs/ir-face-unlock.md`),
`v4l2loopback-dkms`, `media-ctl`, OpenCV ≥5.

    sudo bash install.sh

Then enroll: `sudo howdy add`, or open the **Enroll Face** app.

See `docs/ir-face-unlock.md` for architecture, file map, and known quirks.
