#!/usr/bin/env python3
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/webcgps
# SPDX-License-Identifier: MIT
"""
Web version of cgps, so I can point a web browser at some IOT device running
gpsd and see what it's doing. Fear my early 90's web1.0 html table skills.
"""
import logging
import re
import socket
import threading
from argparse import ArgumentParser, Namespace
from json import dumps as jdumps
from json import loads as jloads
from time import monotonic, sleep
from typing import Any, Dict

from flask import Flask, jsonify

NAV: Dict[str, Any] = {
    "TIME": None,
    "TS": None,
    "CON": False,
    "TPV": dict(),
    "SKY": dict(),
}
ARGS: Namespace = Namespace()
RUN: bool = True
app: Flask = Flask(__name__)
logging.basicConfig(level=logging.INFO)


def get_args() -> Namespace:
    global ARGS
    ap = ArgumentParser()
    ap.add_argument(
        "-g",
        "--gpsd",
        type=str,
        default="gpsd://localhost:2947/dev/ttyACM0",
        help="[%(default)s]",
    )
    ap.add_argument(
        "-i",
        "--web-refresh-interval",
        metavar="SEC",
        default=2.0,
        help="how often the web page updates in seconds [%(default)s]",
    )
    ap.add_argument(
        "-l",
        "--listen",
        type=str,
        default="127.0.0.1",
        help="[%(default)s]",
    )
    ap.add_argument(
        "-p",
        "--port",
        type=str,
        default=4773,
        help="[%(default)s]",
    )
    ap.add_argument(
        "-t",
        "--timeout",
        default=3,
        metavar="SEC",
        help="GPSD socket timeout in seconds [%(default)s]",
    )
    ap.add_argument(
        "-v",
        "--verbose",
        default=0,
        action="count",
        help="[%(default)s]",
    )
    ARGS = ap.parse_args()
    return ARGS


def gps_thread():
    global NAV
    global ARGS
    global RUN
    last_data_time = 0
    while RUN:
        try:
            with socket.create_connection((ARGS.gpsd["host"], ARGS.gpsd["port"]), ARGS.timeout) as s:
                s.setblocking(False)
                gpsfd = s.makefile("rw")
                watch_args = {"enable": True, "json": True}
                if ARGS.gpsd["dev"]:
                    watch_args["device"] = ARGS.gpsd["dev"]
                watch = "?WATCH=" + jdumps(watch_args)
                print(watch, file=gpsfd, flush=True)
                while RUN:
                    line = gpsfd.readline().strip()
                    now = monotonic()
                    if not line:
                        if now - last_data_time > ARGS.timeout:
                            raise TimeoutError
                        sleep(0.2)
                        continue
                    if NAV["CON"] is False:
                        logging.info("connected to gpsd")
                        NAV["CON"] = True
                    x = jloads(line)
                    last_data_time = now
                    mt = x["class"]
                    # Only care about these two message types
                    if mt not in ["TPV", "SKY"]:
                        continue
                    # Skip old data
                    ft = x.get("time", None)
                    if ft:
                        NAV["TS"] = ft
                    if mt == "TPV":
                        if ft != NAV["TIME"]:
                            NAV["TIME"] = ft
                        x["cep"] = x.pop("eph", "")
                    if mt == "SKY" and "satellites" in x:
                        # Sort satellites in decreasing order of quality
                        x["satellites"].sort(key=lambda s: s.get("qual",0) * 100 + s.get("ss", 0), reverse=True)
                    x.pop("class", None)
                    NAV[mt].update(x)
        except KeyboardInterrupt:
            RUN = False
            return
        except (InterruptedError, TimeoutError):
            pass
        except Exception as e:
            logging.exception(e)
        finally:
            if NAV["CON"]:
                logging.info("disconnected from gpsd")
            NAV["CON"] = False
        sleep(0.5)


@app.route("/", methods=["GET"])
def do_index():
    return index_html()


@app.route("/data", methods=["GET"])
def do_data():
    if RUN is False:
        raise SystemExit
    return jsonify(NAV)


def main():
    global ARGS
    get_args()
    m = re.match(
        r"^gpsd://(?P<host>[-1-9a-zA-Z_.-]+)(:(?P<port>\d+))?(?P<dev>/[a-zA-Z0-9/_.-]+[a-zA-Z0-9])?", ARGS.gpsd
    )
    if m is None:
        raise ValueError("couldn't parse gpsd url")
    else:
        d = m.groupdict()
        d["port"] = 2947 if d["port"] is None else d["port"]
        ARGS.gpsd = d
    global NAV
    g = threading.Thread(target=gps_thread)
    g.daemon = True
    g.start()
    try:
        app.run(debug=ARGS.verbose, port=ARGS.port, host=ARGS.listen)
    except KeyboardInterrupt:
        global RUN
        RUN = False
        g.join(2)


def index_html() -> str:
    return (
        """
<html>
<body>
<tt>
<!-- 
<table id="main" border="0">
<tr> <td align="center"><b>Navigation Solution</b></td> <td align="center"><b>Skyview</b></td> </tr>
<tr><td valign="top">
-->
<table id="tpv" border="0" cellpadding="2"><h2>Navigation Solution</h2></td>
<tr><td colspan="3" id="connected"></td></tr>
<tr><td><b>Message Time</b></td><td colspan="2"> <output id="ts"></output></td></tr>
<tr><td><b>Time</b></td><td colspan="2"> <output id="time"></output> (<output id="leapseconds"></output>)</td></tr>
<tr><td><b>Latitude</b></td><td colspan=2><output id="lat"></output></td></tr>
<tr><td><b>Longitude</b></td><td colspan=2><output id="lon"></output></td></tr>
<tr><td><b>Altitude</b></td><td><output id="altHAE"></output>m HAE</td><td><output id="altMSL"></output>m MSL</td></tr>
<tr><td><b>Speed</b></td><td colspan=2><output id="speed"></output>m/s</td></tr>
<tr><td><b>Track</b></td> <td><output id="track"></output></td>  <td><output id="magvar"></output></td> </tr>
<tr><td><b>Climb</b></td><td colspan=2><output id="climb"></output>m/s</td></tr>
<tr><td><b>Fix Mode</b></td><td colspan=2><output id="mode"></output></td></tr>
<tr><td><b>Satellites Used / Seen</b></td> <td colspan="2"><output id="uSat"></output> / <output id="nSat"></output></td> </tr>
<tr><td><b>Lon  Err</b> (XDOP, EPX)</td><td><output id="xdop"></output></td> <td><output id="epx"></output>m</td></tr>
<tr><td><b>Lat  Err</b> (YDOP, EPY)</td><td><output id="ydop"></output></td> <td><output id="epy"></output>m</td></tr>
<tr><td><b>Alt  Err</b> (VDOP, EPV)</td><td><output id="vdop"></output></td> <td><output id="epv"></output>m</td></tr>
<tr><td><b>2D   Err</b> (HDOP, CEP)</td><td><output id="hdop"></output></td> <td><output id="cep"></output>m</td></tr>
<tr><td><b>3D   Err</b> (PDOP, SEP)</td><td><output id="pdop"></output></td> <td><output id="sep"></output>m</td></tr>
<tr><td><b>Speed Err</b> (EPS)</td><td colspan="2"><output id="eps"></output>m/s</td> </tr>
<tr><td><b>Time Err</b> (TDOP)</td><td colspan="2"><output id="tdop"></output></td> </td></tr>
<tr><td><b>Geo  Err</b> (GDOP)</td><td colspan="2"><output id="gdop"></output></td> </tr>
<tr><td><b>ECEF X, VX</b></td><td><output id=ecefx></output>m</td>  <td><output id=ecefvx></output>m/s</td> </tr>
<tr><td><b>ECEF Y, VY</b></td><td><output id=ecefy></output>m</td>  <td><output id=ecefvy></output>m/s</td> </tr>
<tr><td><b>ECEF Z, VZ</b></td><td><output id=ecefz></output>m</td>  <td><output id=ecefvz></output>m/s</td> </tr>
</table>
<!--
</td><td valign="top">
-->

  <table id="sky" border="1"><h2>Skyview</h2>
    <!-- computed table contents go here -->
  </table>
  </td></tr>
<!--
</table>
-->
</tt>
<script type="text/javascript" id="gpsloader">
  function fetchGpsData() {
    var httpRequest = new XMLHttpRequest();
    gnss = ["GP", "SB", "GA", "BD", "IM", "QZ", "GL", "IR"];
    qtype = ["none", "search", "acquired", "detected", "code/time", "code/carrier/time", "code/carrier/time", "code/carrier/time" ]
    httpRequest.addEventListener("readystatechange", (url) => {
      if (httpRequest.readyState === 4 && httpRequest.status === 200) {
        var gpsInfo = JSON.parse(httpRequest.responseText);
        if (gpsInfo["CON"]) {
            cs = "Connected";
            cc = "green";
        } else {
            cs = "Disconnected";
            cc = "red";
        }
        document.getElementById("connected").innerHTML = `<center><strong><font size="+2" color="${cc}">GPSD ${cs}</font></strong></center>`;
        document.getElementById("ts").innerText = gpsInfo["TS"];
        gt = gpsInfo["TPV"]
        gs = gpsInfo["SKY"]
        f = ["time", "leapseconds", "lat", "lon", "altHAE", "altMSL", "mode", "climb", "speed", "track", "magvar", "epx", "epy", "epv", "eps", "cep", "sep"]
        for(i=0; i<f.length; i++){
          n = f[i]
          document.getElementById(n).innerText= gt[n];
        }
        f = ["x", "y", "z"];
        for(i=0; i<f.length; i++) {
          d = "ecef"+f[i]
          document.getElementById(d).innerText = gt[d];
          d = "ecefv"+f[i]
          document.getElementById(d).innerText = gt[d];
        }

        // useful quantities to be copied from the SKY message
        f = ["xdop", "ydop", "hdop", "vdop", "pdop", "tdop", "gdop", "nSat", "uSat"];
        for(i=0; i<f.length; i++) {
          n = f[i]
          document.getElementById(n).innerText = gpsInfo["SKY"][n];
        }

        // nasty stuff to compute the table contents
        sky_table = document.getElementById("sky");
        table_content = "<tr> <td><b>GNSS</b></td> <td><b>PRN</b></td> <td><b>Azim</b></td> <td><b>Elev</b></td> <td><b>SNR</b></td> <td><b>Used</b></td> <td><b>Quality</b></td> </tr>"
        for(i=0; i<gs["satellites"].length; i++){
          s = gs["satellites"][i];
          s['used'] = s['used']?"Y":"N";
          if (s['health'] != 1){
            s['used'] += 'x';
          }
          q = qtype[s['qual']];
          if (s['el'] === undefined){ s['el'] = -1; }
          if (s['az'] === undefined){ s['az'] = -1; }
          table_content += `<tr> <td>${gnss[s['gnssid']]} ${s['svid']}</td> <td>${s['PRN']}</td> <td>${s['az']}</td> <td>${s['el']}</td> <td>${s['ss']}</td> <td>${s['used']}</td> <td>${q} </td> </tr>`;
        }
        sky_table.innerHTML = table_content;
      }
    });
    httpRequest.open("GET", "/data", true);
    httpRequest.send();
  }
  var gpsUpdateInterval = """
        + str(round(float(ARGS.web_refresh_interval) * 1000))
        + """;
  var gpsTimer = setInterval(fetchGpsData, gpsUpdateInterval);
  fetchGpsData();
</script>
</body>
</html>
"""
    )


if __name__ == "__main__":
    main()
