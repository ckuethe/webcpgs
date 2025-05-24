#!/usr/bin/env python3
# Author: Chris Kuethe <chris.kuethe@gmail.com> , https://github.com/ckuethe/webcgps
# SPDX-License-Identifier: MIT
"""
Web version of cgps, so I can point a web browser at some IOT device running
gpsd and see what it's doing. Fear my early 90's web1.0 html table skills.
"""
import logging
import os
import re
import socket
from argparse import ArgumentParser, Namespace
from json import dumps as jdumps
from json import loads as jloads
from threading import Thread
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
APP_RUN: bool = True
app: Flask = Flask(__name__)
logging.basicConfig(level=logging.WARNING)


def get_args() -> Namespace:
    global ARGS
    ap: ArgumentParser = ArgumentParser()
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
        type=float,
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


def gps_thread() -> None:
    global NAV
    global ARGS
    global APP_RUN
    connected = False
    while APP_RUN:
        try:
            with socket.create_connection((ARGS.gpsd["host"], ARGS.gpsd["port"]), ARGS.timeout) as gpssock:
                gpssock.setblocking(False)
                gpsfd = gpssock.makefile("rw")
                watch_args: dict[str, bool] = {"enable": True, "json": True}
                if ARGS.gpsd["dev"]:
                    NAV["DEV"] = watch_args["device"] = ARGS.gpsd["dev"]
                else:
                    NAV["DEV"] = "any"
                watch: str = "?WATCH=" + jdumps(watch_args)
                print(watch, file=gpsfd, flush=True)
                connected = True
                last_data_time = 0.0
                while connected:
                    line: str = gpsfd.readline().strip()
                    if "No such device" in line:
                        NAV["CON"] = False
                        NAV["DEV"] = "No GPS Device"

                    monotime: float = monotonic()
                    if not line:
                        if last_data_time and (monotime - last_data_time > ARGS.timeout):
                            connected = False
                            raise TimeoutError("No data")
                        sleep(0.2)
                        continue
                    if NAV["CON"] is False:
                        logging.info("connected to gpsd")
                        NAV["CON"] = True
                    message: dict[str, Any] = jloads(line)
                    last_data_time = monotime
                    message_type: str = message["class"]

                    # Only care about these two message types
                    if message_type not in ["TPV", "SKY"]:
                        continue

                    # Skip old data
                    fix_timestamp: Any = message.get("time", "")
                    if fix_timestamp:
                        NAV["TS"] = fix_timestamp
                    if message_type == "TPV":
                        if fix_timestamp != NAV["TIME"]:
                            NAV["TIME"] = fix_timestamp
                        try:
                            # this won't exist if there is no valid fix
                            message["cep"] = message.pop("eph")
                            message["climb_fpm"] = round(message["climb"] * 196.85, 1)
                        except KeyError:
                            pass
                    if message_type == "SKY":
                        if "satellites" in message:
                            # Sort satellites in decreasing order of quality
                            message["satellites"].sort(
                                key=lambda s: s.get("qual", 0) * 100 + s.get("ss", 0), reverse=True
                            )
                        else:
                            continue
                    message.pop("class", None)
                    NAV[message_type].update(message)
        except KeyboardInterrupt:
            APP_RUN = False
            return
        except Exception:
            """
            not terribly concerned about anything else going wrong, just
            hide it and retry the connection. Stuff that might go wrong:
            - network errors
            - gpsd loses connection to the device
            - device reboots and emits garbage
            """
            pass
        finally:
            if NAV["CON"]:
                print(f"disconnected from gpsd - {NAV['DEV']}")
            NAV["CON"] = False
            connected = False
            try:
                gpsfd.close()
                gpssock.close()
            except Exception:
                pass  # we tried.

        sleep(0.5)


@app.route("/", methods=["GET"])
def do_index() -> str:
    if APP_RUN is False:
        raise SystemExit
    return index_html()


@app.route("/gpsreset", methods=["GET"])
def do_gps_reset():
    return jsonify({"error": "gps reset not yet implemented"})


@app.route("/data", methods=["GET"])
def do_data():
    if APP_RUN is False:
        raise SystemExit
    return jsonify(NAV)


def main() -> None:
    global ARGS
    get_args()
    m = re.match(
        r"^gpsd://(?P<host>[-1-9a-zA-Z_.-]+)(:(?P<port>\d+))?(?P<dev>/[a-zA-Z0-9/_.-]+[a-zA-Z0-9])?", ARGS.gpsd
    )
    if m is None:
        raise ValueError("couldn't parse gpsd url")
    else:
        d: dict[str, str | int | None] = m.groupdict()
        d["port"] = 2947 if d["port"] is None else d["port"]
        ARGS.gpsd = d  # pyrefly: ignore  (it doesn't know that args.gpsd does exist)
    global NAV
    g: Thread = Thread(target=gps_thread)
    g.daemon = True
    g.start()
    try:
        app.logger.setLevel(logging.INFO if ARGS.verbose else logging.ERROR)
        app.run(debug=ARGS.verbose, port=ARGS.port, host=ARGS.listen)
    except KeyboardInterrupt:
        global APP_RUN
        APP_RUN = False
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
<tr><td><b>Climb</b></td><td><output id="climb"></output>m/s</td><td><output id="climb_fpm"></output>ft/min</td></tr>
<tr><td><b>Fix Mode</b></td><td colspan=2><output id="mode"></output></td></tr>
<tr><td><b>Satellites Used / Seen</b></td> <td colspan="2"><output id="uSat"></output> / <output id="nSat"></output></td> </tr>
<tr><td><b>Lon  Err</b> (XDOP, EPX)</td><td><output id="xdop"></output></td> <td><output id="epx"></output>m</td></tr>
<tr><td><b>Lat  Err</b> (YDOP, EPY)</td><td><output id="ydop"></output></td> <td><output id="epy"></output>m</td></tr>
<tr><td><b>Alt  Err</b> (VDOP, EPV)</td><td><output id="vdop"></output></td> <td><output id="epv"></output>m</td></tr>
<tr><td><b>2D   Err</b> (HDOP, CEP)</td><td><output id="hdop"></output></td> <td><output id="cep"></output>m</td></tr>
<tr><td><b>3D   Err</b> (PDOP, SEP)</td><td><output id="pdop"></output></td> <td><output id="sep"></output>m</td></tr>
<tr><td><b>Speed Err</b> (EPS)</td><td colspan="2"><output id="eps"></output>m/s</td> </tr>
<tr><td><b>Time Err</b> (TDOP)</td><td colspan="2"><output id="tdop"></output>s</td> </td></tr>
<tr><td><b>Geo  Err</b> (GDOP)</td><td colspan="2"><output id="gdop"></output>m</td> </tr>
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
        console.log(gpsInfo);
        if (gpsInfo["CON"]) {
            if (gpsInfo["DEV"] == "No GPS Device") {
                cs = "Degraded - no device";
                cc = "orange";
                emoji = "⚠️️";
            } else {
                cs = "Connected";
                cc = "green";
                emoji = "🛰️";
            }
        } else {
            cs = "Disconnected";
            cc = "red";
            emoji = "⛔";
        }
        document.getElementById("connected").innerHTML = `<center><strong><font size="+2"><font color="${cc}">GPSD ${cs}</font> ${emoji}</font></strong></center>`;
        document.getElementById("ts").innerText = gpsInfo["TS"];
        gps_tpv = gpsInfo["TPV"]
        gps_sky = gpsInfo["SKY"]

        // I made the HTML element names match the JSON element names so I could
        // do a loop just like this.
        fields = ["time", "leapseconds", "lat", "lon", "altHAE", "altMSL", "mode",
                  "climb", "climb_fpm", "speed", "track", "magvar", "epx", "epy",
                  "epv", "eps", "cep", "sep"]
        for(i=0; i<fields.length; i++){
          fieldname = fields[i]
          if (gps_tpv[fieldname] === undefined){
            document.getElementById(fieldname).innerText = " --- ";
          } else {
            document.getElementById(fieldname).innerText = gps_tpv[fieldname];
          }
        }
        // ECEF state vector
        axis = ["x", "y", "z"];
        vz = ["", "v"];
        for(i=0; i<axis.length; i++) {
          for(j=0; j<vz.length; j++) {
            fieldname = "ecef"+vz[j]+axis[i]
            if (gps_tpv[fieldname] === undefined) {
                document.getElementById(fieldname).innerText = " --- ";
            } else {
                document.getElementById(fieldname).innerText = gps_tpv[fieldname];
            }
          }
        }

        // useful quantities to be copied from the SKY message
        fields = ["xdop", "ydop", "hdop", "vdop", "pdop", "tdop", "gdop", "nSat", "uSat"];
        for(i=0; i<fields.length; i++) {
          fieldname = fields[i]
          if (gpsInfo["SKY"][fieldname] === undefined) {
            document.getElementById(fieldname).innerText = " --- ";
          } else {
            document.getElementById(fieldname).innerText = gpsInfo["SKY"][fieldname];
          }
        }

        // nasty stuff to compute the table contents
        sky_table = document.getElementById("sky");
        table_content = "<tr> <td><b>GNSS</b></td> <td><b>PRN</b></td> <td><b>Azim</b></td> <td><b>Elev</b></td> <td><b>SNR</b></td> <td><b>Used</b></td> <td><b>Quality</b></td> </tr>"
        if (gps_sky["satellites"] === undefined) {
          1 == 1 ; // do nothing
        } else {
          for(i=0; i<gps_sky["satellites"].length; i++){
            s = gps_sky["satellites"][i];
            s['used'] = s['used']?"Y":"N";
            if (s['health'] != 1){
                s['used'] += 'x';
            }
            q = qtype[s['qual']];
            if (s['el'] === undefined){ s['el'] = -1; }
            if (s['az'] === undefined){ s['az'] = -1; }
            table_content += `<tr> <td>${gnss[s['gnssid']]} ${s['svid']}</td> <td>${s['PRN']}</td> <td>${s['az']}</td> <td>${s['el']}</td> <td>${s['ss']}</td> <td>${s['used']}</td> <td>${q} </td> </tr>`;
          }
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
