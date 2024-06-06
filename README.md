# webcgps

[gpsd](https://gpsd.io) isn't the easiest thing to monitor from a phone, and I needed to check the state of the GPS on a little IoT thing I built.
Here's a hacky little python script to roughly approximate the output of `cgps`, but in a web page.

NB: in the same way that `gpsd` only listens to localhost by default, this server also only listens on localhost by default.

```
usage: webcgps.py [-h] [-g GPSD] [-i SEC] [-l LISTEN] [-p PORT] [-t SEC] [-v]

options:
  -h, --help                             show this help message and exit
  -g GPSD, --gpsd GPSD                   [gpsd://localhost:2947/dev/ttyACM0]
  -i SEC, --web-refresh-interval SEC     how often the web page updates in seconds [2.0]
  -l LISTEN, --listen LISTEN             [127.0.0.1]
  -p PORT, --port PORT                   [4773]
  -t SEC, --timeout SEC                  GPSD socket timeout in seconds [3]
  -v, --verbose                          [0]
```

![Web GPS](webgps.jpg?raw=true "WebGPS")
![curses GPS](cgps.jpg?raw=true "cGPS")