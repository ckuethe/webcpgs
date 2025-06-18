#!/bin/bash

# Hacky little script to restart gpsd if somehow the receiver is disconnected
# and reconnected. Not sure why this happens; all the connectors have rigid
# reinforcements/clamps to keep them in place and dmesg doesn't say anything
# about electrical noise. Anyway, once webcgps says "no device", use this to
# reset the affected subsystems

[ $(id -u) -eq 0 ] || exec sudo $BASH_ARGV0 $1

# Assumption: u-blox GPS connected via its native CDC-ACM USB interface.
USB_ID="1546:01a8"
TTY="/dev/ttyACM0"

bounce_gps () {
	systemctl stop gpsd
	# usbreset ${USB_ID}
	usbreset $1
	while : ; do
		#test -c "$TTY" && break
		test -c "$2" && break
		sleep 1
		test -c "$2" || usbreset $1
	done
	systemctl start gpsd
}

if [ "x$1" == "xmonitor" ] ; then
	echo "Watching for ${USB_ID} connected as ${TTY}"
	while : ; do
		echo '?WATCH={"enable":True,"json":True,"dev":"'${TTY}'"}' |nc localhost 2947 | head -3 | grep devices | grep -q $TTY
		if [ $? -ne 0 ] ; then
			bounce_gps $USB_ID $TTY
		fi
		sleep 5
	done
else
	echo "resetting ${USB_ID} to restore ${TTY}"
	bounce_gps $USB_ID $TTY
fi
