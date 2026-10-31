#!/bin/bash
export PATH=/usr/local/bin:/usr/bin:/bin

# ALS 自适应曝光/增益：暗环境拉满，亮环境保守
ALS=$(cat /sys/bus/iio/devices/iio:device*/in_illuminance_raw 2>/dev/null | head -1)
ALS=${ALS:-50}
if [ "$ALS" -lt 20 ]; then
	GAIN=128; EXP=1500
elif [ "$ALS" -lt 100 ]; then
	GAIN=96;  EXP=1200
else
	GAIN=32;  EXP=600
fi

for dev in /dev/media*; do
	if media-ctl -d "$dev" -p 2>/dev/null | grep -q "ov7251"; then
		media-ctl -d "$dev" -l '"ov7251 3-0060":0->"ipu3-csi2 2":0[1]' 2>/dev/null
		media-ctl -d "$dev" -V '"ipu3-csi2 2":0 [fmt:Y10_1X10/640x480 field:none]' 2>/dev/null
		media-ctl -d "$dev" -V '"ipu3-csi2 2":1 [fmt:Y10_1X10/640x480 field:none]' 2>/dev/null
		for s in /sys/class/video4linux/v4l-subdev*; do
			if grep -q "ov7251" "$s/name" 2>/dev/null; then
				v4l2-ctl -d "/dev/$(basename "$s")" --set-ctrl exposure=$EXP,analogue_gain=$GAIN 2>/dev/null
				break
			fi
		done
		V=$(media-ctl -d "$dev" -e "ipu3-cio2 2")
		exec /usr/local/bin/ir_bridge "$V"
	fi
done
exit 1
