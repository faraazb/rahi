#!/usr/bin/env python3
"""Testbench UI for the built timetable (not the real app).

Pick a station, pick a direction, see the next trains from a given time.

  mise run testbench [-- path/to.sqlite --port 8000]   (from the repo root)
  then open http://127.0.0.1:8000

Standard library only. Read-only access to the SQLite file.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SERVICE_DAY_START = 180  # 03:00, same boundary the parser uses
DB_PATH = Path(__file__).resolve().parents[1] / "build" / "mumbai-local.sqlite"


def q(sql: str, *args):
    db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute(sql, args)]
    finally:
        db.close()


def api_stations(_):
    return q("""SELECT s.code, s.name, l.code AS line FROM line_station ls
                JOIN station s ON s.id=ls.station_id JOIN line l ON l.id=ls.line_id
                ORDER BY l.id, ls.seq""")


def api_directions(p):
    code = p["station"]
    # Ends of each line this station is on, to label directions by where they go.
    ends = q("""SELECT l.id AS line_id,
                  (SELECT s.name FROM line_station x JOIN station s ON s.id=x.station_id
                    WHERE x.line_id=l.id ORDER BY x.seq ASC LIMIT 1) AS first,
                  (SELECT s.name FROM line_station x JOIN station s ON s.id=x.station_id
                    WHERE x.line_id=l.id ORDER BY x.seq DESC LIMIT 1) AS last
                FROM line l JOIN line_station ls ON ls.line_id=l.id
                JOIN station s ON s.id=ls.station_id WHERE s.code=?""", code)
    out = []
    for e in ends:
        for d, label in ((1, f"Up, towards {e['first']}"), (2, f"Down, towards {e['last']}")):
            n = q("""SELECT COUNT(*) AS n FROM stop_time st JOIN train t ON t.id=st.train_id
                     JOIN station s ON s.id=st.station_id
                     WHERE s.code=? AND t.direction=? AND t.line_id=?
                       AND (st.seq < (SELECT MAX(seq) FROM stop_time x WHERE x.train_id=t.id)
                            OR t.dest_time_missing=1)""", code, d, e["line_id"])[0]["n"]
            if n:
                out.append({"dir": d, "line_id": e["line_id"], "label": label, "trains": n})
    return out


def api_trains(p):
    t = int(p["t"])            # minutes after midnight, 0..1439
    dow = int(p["dow"])        # 0 = Monday
    limit = min(int(p.get("limit", 40)), 200)
    # Before 03:00 we are still in the previous day's service.
    if t < SERVICE_DAY_START:
        t += 1440
        dow = (dow - 1) % 7
    rows = q("""
        SELECT t.id, t.number, t.variant, t.is_fast, t.is_ac, t.ac_weekdays_only,
               t.ladies_special, t.cars, t.dest_time_missing, t.notes,
               sv.days, sv.not_on_holidays, st.time_min AS dep, st.seq,
               os.name AS origin, ds.name AS dest,
               (SELECT x.time_min FROM stop_time x WHERE x.train_id=t.id
                ORDER BY x.seq DESC LIMIT 1) AS last_time,
               (SELECT MAX(x.seq) FROM stop_time x WHERE x.train_id=t.id) AS last_seq
        FROM stop_time st
        JOIN train t ON t.id=st.train_id
        JOIN service sv ON sv.id=t.service_id
        JOIN station s ON s.id=st.station_id
        LEFT JOIN station os ON os.id=t.origin_station_id
        LEFT JOIN station ds ON ds.id=t.dest_station_id
        WHERE s.code=? AND t.direction=? AND t.line_id=? AND st.time_min>=?
          AND substr(sv.days, ?, 1)='1'
          AND (st.seq < (SELECT MAX(x.seq) FROM stop_time x WHERE x.train_id=t.id)
               OR t.dest_time_missing=1)
        ORDER BY st.time_min, t.number
        LIMIT ?""", p["station"], int(p["dir"]), int(p["line_id"]), t, dow + 1, limit)
    for r in rows:
        r["in_min"] = r["dep"] - t
        r["stops_after"] = r["last_seq"] - r["seq"]
    return {"service_minute": t, "service_dow": dow, "trains": rows}


def api_train(p):
    return q("""SELECT st.seq, s.code, s.name, st.time_min FROM stop_time st
                JOIN station s ON s.id=st.station_id WHERE st.train_id=? ORDER BY st.seq""",
             int(p["id"]))


def api_meta(_):
    return {r["key"]: r["value"] for r in q("SELECT key, value FROM meta")}


ROUTES = {"/api/stations": api_stations, "/api/directions": api_directions,
          "/api/trains": api_trains, "/api/train": api_train, "/api/meta": api_meta}

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Timetable testbench</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{font:14px/1.4 system-ui,sans-serif;margin:16px;max-width:1000px}
 select,input,button{font:inherit;padding:4px 6px;margin-right:6px}
 .row{margin:8px 0} .dirs button{margin:4px 6px 4px 0}
 .dirs button.on{background:#222;color:#fff}
 table{border-collapse:collapse;width:100%;margin-top:10px}
 th,td{border-bottom:1px solid #ddd;padding:4px 6px;text-align:left;white-space:nowrap}
 th{background:#f4f4f4} tr.t{cursor:pointer} tr.t:hover{background:#fafafa}
 .fast{font-weight:600;color:#b00} .muted{color:#888} td.stops{white-space:normal;background:#fbfbfb;font-size:13px}
 .tag{display:inline-block;padding:0 5px;border-radius:3px;background:#eee;margin-right:3px;font-size:12px}
 .ac{background:#cde8f6} .lad{background:#f6d6e8}
</style></head><body>
<h3>Timetable testbench <span class="muted" id="meta"></span></h3>
<div class="row">From
 <select id="station"><option value="">choose a station</option></select>
 at <input type="time" id="time"> on
 <select id="dow">
  <option value="0">Mon</option><option value="1">Tue</option><option value="2">Wed</option>
  <option value="3">Thu</option><option value="4">Fri</option><option value="5">Sat</option><option value="6">Sun</option>
 </select>
 <button id="now">Now</button>
</div>
<div class="row dirs" id="dirs"></div>
<div id="out"></div>
<script>
const $ = s => document.querySelector(s);
const hm = m => { m = ((m % 1440) + 1440) % 1440; return String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0'); };
const DAYS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
let dir = null;
const api = (p, args) => fetch(p + '?' + new URLSearchParams(args || {})).then(r => r.json());

function setNow(){
  const d = new Date();
  $('#time').value = hm(d.getHours()*60 + d.getMinutes());
  $('#dow').value = (d.getDay() + 6) % 7;
}
function days(s){
  if (s === '1111111') return 'daily';
  if (s === '1111110') return 'not Sun';
  if (s === '0000001') return 'Sun only';
  return [...s].map((c,i)=>c==='1'?DAYS[i]:'').filter(Boolean).join(' ');
}

async function loadDirs(){
  dir = null; $('#out').innerHTML = '';
  const code = $('#station').value; if (!code) { $('#dirs').innerHTML=''; return; }
  const ds = await api('/api/directions', {station: code});
  $('#dirs').innerHTML = ds.length ? '' : '<span class="muted">No departures from this station.</span>';
  for (const d of ds){
    const b = document.createElement('button');
    b.textContent = `${d.label} (${d.trains})`;
    b.onclick = () => { dir = d; [...$('#dirs').children].forEach(x=>x.classList.remove('on')); b.classList.add('on'); loadTrains(); };
    $('#dirs').appendChild(b);
  }
  if (ds.length === 1) $('#dirs').firstChild.click();
}

async function loadTrains(){
  if (!dir) return;
  const [h, m] = $('#time').value.split(':').map(Number);
  const res = await api('/api/trains', {station: $('#station').value, dir: dir.dir, line_id: dir.line_id,
                                        t: h*60+m, dow: $('#dow').value, limit: 40});
  const rows = res.trains.map(t => `
    <tr class="t" data-id="${t.id}">
      <td><b>${hm(t.dep)}</b></td>
      <td class="muted">${t.in_min} min</td>
      <td>${t.number}${t.variant ? ' <span class="muted">/'+t.variant+'</span>' : ''}</td>
      <td class="${t.is_fast?'fast':''}">${t.is_fast?'Fast':'Slow'}</td>
      <td>${t.dest}${t.dest_time_missing?' <span class="muted">(no arr. time)</span>':''}</td>
      <td>${hm(t.last_time)}</td>
      <td>${t.stops_after}</td>
      <td>${t.cars||''}</td>
      <td>${t.is_ac?'<span class="tag ac">AC'+(t.ac_weekdays_only?' Mon-Fri':'')+'</span>':''}${t.ladies_special?'<span class="tag lad">Ladies</span>':''}</td>
      <td>${days(t.days)}${t.not_on_holidays?', not hol.':''}</td>
    </tr>`).join('');
  $('#out').innerHTML = `<div class="muted">${res.trains.length} trains from ${hm(res.service_minute)},
      service day ${DAYS[res.service_dow]}. Click a train for its stops.</div>
    <table><tr><th>Dep</th><th>In</th><th>Train</th><th>Type</th><th>To</th><th>Arr</th><th>Stops after</th>
    <th>Cars</th><th>Tags</th><th>Runs</th></tr>${rows}</table>`;
  document.querySelectorAll('tr.t').forEach(tr => tr.onclick = () => toggle(tr));
}

async function toggle(tr){
  const next = tr.nextElementSibling;
  if (next && next.classList.contains('detail')) { next.remove(); return; }
  const stops = await api('/api/train', {id: tr.dataset.id});
  const here = $('#station').value;
  const d = document.createElement('tr'); d.className = 'detail';
  d.innerHTML = `<td colspan="10" class="stops">${stops.map(s =>
     (s.code===here?'<b>':'') + `${s.name} ${hm(s.time_min)}` + (s.code===here?'</b>':'')).join(' &rarr; ')}</td>`;
  tr.after(d);
}

(async () => {
  setNow();
  const meta = await api('/api/meta');
  $('#meta').textContent = `(schema ${meta.schema_version}, built ${meta.built_at})`;
  for (const s of await api('/api/stations')){
    const o = document.createElement('option'); o.value = s.code; o.textContent = `${s.name} (${s.code})`;
    $('#station').appendChild(o);
  }
  $('#station').onchange = loadDirs;
  $('#time').onchange = loadTrains; $('#dow').onchange = loadTrains;
  $('#now').onclick = () => { setNow(); loadTrains(); };
})();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        fn = ROUTES.get(url.path)
        if not fn:
            return self._send(404, b"not found", "text/plain")
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            body = json.dumps(fn(params)).encode()
        except (KeyError, ValueError) as e:
            return self._send(400, f"bad request: {e}".encode(), "text/plain")
        self._send(200, body, "application/json")

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def main():
    global DB_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("db", nargs="?", default=str(DB_PATH))
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    DB_PATH = Path(a.db).resolve()
    if not DB_PATH.exists():
        raise SystemExit(f"{DB_PATH} not found; build it with: mumbailocal wr <pdf-dir> --db {a.db}")
    print(f"serving {DB_PATH} on http://127.0.0.1:{a.port}")
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
