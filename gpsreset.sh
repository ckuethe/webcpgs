#!/bin/bash

# Hacky little script to restart gpsd if somehow the receiver is disconnected
# and reconnected. Not sure why this happens; all the connectors have rigid
# reinforcements/clamps to keep them in place and dmesg doesn't say anything
# about electrical noise. Anyway, once webcgps says "no device", use this to
# reset the affected subsystems

[ $(id -u) -eq 0 ] || exec sudo $BASH_ARGV0

# Assumption: u-blox GPS connected via its native CDC-ACM USB interface.
USB_ID="1546:01a8"
TTY="/dev/ttyACM0"

set -x
systemctl stop gpsd
usbreset ${USB_ID}
while : ; do
	test -c "${TTY}" && break
	sleep 1
done
systemctl start gpsd
