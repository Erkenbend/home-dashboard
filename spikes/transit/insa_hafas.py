"""Spike: evaluate INSA HAFAS (mgate) as live departure source for Halle (Saale).

Throwaway code, stdlib only. Outcome documented in docs/decisions/0003-transit-data-source.md.

Usage:
    python3 spikes/transit/insa_hafas.py [--save DIR]
"""

import argparse
import json
import pathlib
import urllib.request
from datetime import datetime

ENDPOINT = "https://reiseauskunft.insa.de/bin/mgate.exe"
BASE = {
    "auth": {"type": "AID", "aid": "nasa-apps"},
    "client": {"type": "IPH", "id": "NASA", "v": "4000200", "name": "nasaPROD"},
    "ver": "1.44",
    "lang": "de",
}
# (stop, via) - via restricts departures to trips passing that stop ("direction")
CASES = [
    ("Rannischer Platz, Halle (Saale)", "Marktplatz, Halle (Saale)"),
    ("Franckeplatz, Halle (Saale)", "Hauptbahnhof, Halle (Saale)"),
]


def call(meth: str, req: dict) -> dict:
    body = json.dumps({**BASE, "svcReqL": [{"meth": meth, "req": req}]}).encode()
    request = urllib.request.Request(
        ENDPOINT, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def loc_match(name: str) -> dict:
    return call(
        "LocMatch",
        {"input": {"loc": {"type": "S", "name": name + "?"}, "maxLoc": 3, "field": "S"}},
    )


def station_board(lid: str, now: datetime, via_lid: str | None = None, dur: int = 60) -> dict:
    req = {
        "type": "DEP",
        "date": now.strftime("%Y%m%d"),
        "time": now.strftime("%H%M%S"),
        "stbLoc": {"lid": lid, "type": "S"},
        "dur": dur,
        "maxJny": 30,
    }
    if via_lid:
        req["dirLoc"] = {"lid": via_lid, "type": "S"}
    return call("StationBoard", req)


def print_board(board: dict) -> None:
    res = board["svcResL"][0]["res"]
    prods = res["common"]["prodL"]
    for jny in res.get("jnyL", []):
        stb = jny["stbStop"]
        print(
            f"  {prods[stb['dProdX']]['name']:>8} -> {jny['dirTxt']:<34}"
            f" plan {stb['dTimeS']}  rt {stb.get('dTimeR', '-')}"
            f"  cncl={stb.get('dCncl', False)}  plat={stb.get('dPltfS', {}).get('txt')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", type=pathlib.Path, help="directory for raw responses")
    args = parser.parse_args()

    now = datetime.now()
    for stop_name, via_name in CASES:
        stop_match = loc_match(stop_name)
        via_match = loc_match(via_name)
        stop = stop_match["svcResL"][0]["res"]["match"]["locL"][0]
        via = via_match["svcResL"][0]["res"]["match"]["locL"][0]
        print(f"== {stop['name']} ({stop['extId']}) via {via['name']} ({via['extId']})")
        board_all = station_board(stop["lid"], now)
        board_via = station_board(stop["lid"], now, via["lid"])
        print_board(board_via)
        if args.save:
            args.save.mkdir(parents=True, exist_ok=True)
            files = {
                f"locmatch_{stop['extId']}.json": stop_match,
                f"locmatch_{via['extId']}.json": via_match,
                f"stationboard_{stop['extId']}.json": board_all,
                f"stationboard_{stop['extId']}_via_{via['extId']}.json": board_via,
            }
            for filename, content in files.items():
                (args.save / filename).write_text(
                    json.dumps(content, indent=1, ensure_ascii=False) + "\n"
                )


if __name__ == "__main__":
    main()
