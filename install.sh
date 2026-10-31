#!/bin/bash
# Install IR face unlock stack (run as root: sudo bash install.sh)
set -e
cd "$(dirname "$0")"

# rebuild bridge from source
gcc -O2 -o /usr/local/bin/ir_bridge src/ir_bridge.c
install -m755 usr/local/bin/ir_bridge_run.sh /usr/local/bin/
install -m755 usr/local/bin/setup_ipu3.sh /usr/local/bin/
install -m755 usr/local/libexec/howdy/howdy-compare /usr/local/libexec/howdy/

install -m644 etc/modprobe.d/v4l2loopback.conf /etc/modprobe.d/
install -m644 etc/udev/rules.d/99-surface-ir-i2c.rules /etc/udev/rules.d/
install -m644 etc/systemd/system/surface_ir_bridge.service /etc/systemd/system/
install -m644 usr/share/pam-configs/howdy /usr/share/pam-configs/
install -m644 etc/howdy/config.ini /usr/local/etc/howdy/ 2>/dev/null || true

# face enroll UI
install -m755 home/.local/bin/face-enroll.py ~sy/.local/bin/
install -m644 home/.local/share/applications/face-enroll.desktop ~sy/.local/share/applications/

udevadm control --reload; udevadm trigger -s i2c-dev
systemctl daemon-reload
systemctl enable surface_ir_bridge.service
pam-auth-update --package || true

echo "Done. Enroll with: sudo howdy add (or the 'Enroll Face' app)"
