# surface-ir-face-unlock

Windows Hello-style face unlock on Microsoft Surface Pro 6 (and other IPU3/OV7251 devices)
using [howdy-next](https://codeberg.org/nathawat/howdy-next) + v4l2loopback.

Hardware: OV7251 IR sensor behind Intel IPU3 → raw ip3y → C bridge → /dev/video42 → PAM.
IR emitter driven via direct I2C write (0x3005=0x08) — works in darkness.

Features:
- on-demand camera (spawns only during auth, PR_SET_PDEATHSIG self-cleanup)
- ALS-adaptive exposure/gain, 3-band
- native PAM module (howdy-next, YuNet+SFace) — no pam-python
- GTK4 enroll/manage UI (`face-enroll.py`)

## Install

Requires: howdy-next installed (build from source on Ubuntu 24.04 — see docs/ir-face-unlock.md),
v4l2loopback-dkms, media-ctl (v4l-utils), opencv.

    sudo bash install.sh

Then enroll: `sudo howdy add` or open the "Enroll Face" app.

See docs/ir-face-unlock.md for the full architecture, file map, and known quirks.
Forked from https://github.com/lksmasin/surface-howdy-sp5 (Surface Pro 5 version).
