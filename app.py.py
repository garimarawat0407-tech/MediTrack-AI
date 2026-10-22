from datetime import datetime, timedelta
import csv
import io
import sqlite3

from flask import Flask, Response, flash, g, redirect, render_template, request, url_for
from jinja2 import DictLoader

app = Flask(__name__)
app.secret_key = "meditrack-demo-key"   # only needed for flash messages (college demo project)
DB = "meditrack_data.db"
LOW_STOCK = 5

TEMPLATES = {
"base.html": """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MediTrack AI</title>
<style>
:root{--blue:#1e6fd9;--dark:#0f4aa1;--light:#eaf2ff;--text:#1b2a41;--muted:#6b7a90;--line:#dbe6f5}
*{box-sizing:border-box}
body{margin:0;font-family:Segoe UI,Arial,sans-serif;background:#f5f9ff;color:var(--text)}
header{background:linear-gradient(90deg,var(--dark),var(--blue));color:#fff;padding:14px 28px;display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px}
header h1{margin:0;font-size:22px}header small{opacity:.85}
nav a{color:#fff;text-decoration:none;margin-left:16px;font-size:14px;opacity:.9}
nav a:hover{opacity:1;text-decoration:underline}
main{max-width:1100px;margin:24px auto;padding:0 16px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:20px}
.stat{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px;border-top:4px solid var(--blue)}
.stat b{display:block;font-size:30px;color:var(--dark)}.stat span{color:var(--muted);font-size:14px}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:20px;overflow-x:auto}
.card h2{margin:0 0 12px;font-size:18px;color:var(--dark)}
form.add{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
input{padding:10px;border:1px solid var(--line);border-radius:8px;font-size:14px;width:100%}
button,.btn{padding:8px 14px;border:0;border-radius:8px;background:var(--blue);color:#fff;cursor:pointer;font-size:13px;text-decoration:none;display:inline-block}
button:hover,.btn:hover{background:var(--dark)}
button.ok{background:#1f9d62}button.no{background:#e0902b}button.del{background:#d64545}
table{width:100%;border-collapse:collapse;font-size:14px}
th{background:var(--light);color:var(--dark);text-align:left}
th,td{padding:10px;border-bottom:1px solid var(--line)}
td form{display:inline}
.badge{padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;white-space:nowrap}
.Low,.Taken,.good{background:#dff5ea;color:#177a4b}
.Medium,.warn{background:#fff1d6;color:#9a6200}
.High,.Missed,.bad{background:#fde2e2;color:#b02a2a}
.No{background:#eef1f6;color:var(--muted)}
.note{color:var(--muted);font-size:12px;margin-top:8px}
.empty{color:var(--muted);text-align:center;padding:16px}
.flash{background:#fff1d6;border:1px solid #f0d28a;color:#7a5200;padding:10px 14px;border-radius:8px;margin-bottom:14px}
.bar{display:flex;height:14px;border-radius:7px;overflow:hidden;background:#eef1f6;min-width:140px}
.bar i{display:block;height:100%}.bar .t{background:#1f9d62}.bar .m{background:#e0902b}
#toasts{position:fixed;top:14px;right:14px;z-index:99;display:flex;flex-direction:column;gap:10px}
.toast{background:#fff;border-left:6px solid var(--blue);box-shadow:0 6px 20px rgba(15,74,161,.25);padding:12px 16px;border-radius:10px;min-width:240px}
.toast button{margin-top:8px}
.due{background:#fff8e1}
@media print{header,.noprint,#toasts{display:none!important}body{background:#fff}.card{border:1px solid #ccc}}
</style>
</head>
<body>
<header>
  <div><h1>💙 MediTrack AI</h1><small>Smart medicine reminder &amp; adherence dashboard</small></div>
  <nav>
    <a href="{{ url_for('dashboard') }}">Dashboard</a>
    <a href="{{ url_for('report') }}">Weekly Report</a>
    <a href="{{ url_for('export_csv') }}">Export CSV</a>
  </nav>
</header>
<main>
  {% for m in get_flashed_messages() %}<div class="flash">{{ m }}</div>{% endfor %}
  {% block body %}{% endblock %}
</main>
<div id="toasts"></div>
{% block script %}{% endblock %}
</body>
</html>
""",

"index.html": """
{% extends 'base.html' %}
{% block body %}
  <div class="stats">
    <div class="stat"><b>{{ total }}</b><span>💊 Total Medicines</span></div>
    <div class="stat"><b>{{ taken }}</b><span>✅ Doses Taken</span></div>
    <div class="stat"><b>{{ missed }}</b><span>❌ Doses Missed</span></div>
    <div class="stat"><b>{{ adherence }}%</b><span>📊 Adherence</span></div>
  </div>

  <div class="card noprint" id="remBar" style="border-left:6px solid var(--blue)">
    <b>⏰ Next dose:</b> <span id="nextDose">No medicines scheduled</span>
    <div id="permRow" style="margin-top:8px;display:none">
      <span class="note">Turn on notifications to get a reminder at the scheduled time, even when this tab is in the background.</span>
      <button type="button" id="enableBtn" style="margin-left:8px">🔔 Enable Notifications</button>
    </div>
    <div id="okRow" class="note" style="display:none;margin-top:8px">✅ Reminders are ON. Keep this page open in your browser to receive them.</div>
  </div>

  {% if low_items %}
  <div class="flash">⚠️ Low stock: {% for m in low_items %}<b>{{ m.name }}</b> ({{ m.stock }} left){% if not loop.last %}, {% endif %}{% endfor %}</div>
  {% endif %}

  <div class="card">
    <h2>➕ Add Medicine</h2>
    <form class="add" method="post" action="/add">
      <input name="name" placeholder="Medicine name" required>
      <input name="dosage" placeholder="Dosage (e.g. 500mg)" required>
      <input type="time" name="time" required>
      <input type="number" name="stock" min="0" value="30" title="Tablets in stock" required>
      <button>Add</button>
    </form>
    <p class="note">The last box is the tablet stock. Each "Taken" click reduces the stock by 1.</p>
  </div>

  <div class="card">
    <h2>⏰ My Medicines &amp; 🤖 Missed-Dose Risk
</h2>
    <table>
      <tr><th>Medicine</th><th>Dosage</th><th>Time</th><th>Stock</th><th>Risk (AI demo)</th><th>Action</th></tr>
      {% for m in meds %}
      <tr>
        <td>{{ m.name }}</td><td>{{ m.dosage }}</td><td>{{ m.time }}</td>
        <td>{% if m.stock == 0 %}<span class="badge bad">Out of stock</span>
            {% elif m.stock <= low %}<span class="badge warn">{{ m.stock }} left</span>
            {% else %}<span class="badge good">{{ m.stock }}</span>{% endif %}</td>
        <td><span class="badge {{ m.risk.level.split()[0] }}">{{ m.risk.level }}{% if m.risk.level != 'No data' %} · {{ m.risk.score }}%{% endif %}</span></td>
        <td>
          <form method="post" action="/dose/{{ m.id }}/Taken"><button class="ok">Taken</button></form>
          <form method="post" action="/dose/{{ m.id }}/Missed"><button class="no">Missed</button></form>
          <form method="post" action="/delete/{{ m.id }}" onsubmit="return confirm('Delete this medicine?')"><button class="del">Delete</button></form>
        </td>
      </tr>
      {% else %}<tr><td colspan="6" class="empty">No medicines yet. Add one above.</td></tr>{% endfor %}
    </table>
    <p class="note">Risk = % of missed doses in last 7 logs + extra weight for consecutive misses (rule-based demo).</p>
  </div>

  <div class="card">
    <h2>📋 Dose History</h2>
    <table>
      <tr><th>Medicine</th><th>Status</th><th>Logged at</th></tr>
      {% for h in history %}
      <tr><td>{{ h.medicine_name }}</td><td><span class="badge {{ h.status }}">{{ h.status }}</span></td><td>{{ h.logged_at }}</td></tr>
      {% else %}<tr><td colspan="3" class="empty">No history yet.</td></tr>{% endfor %}
    </table>
  </div>
{% endblock %}

{% block script %}
<script>
const MEDS = {{ reminders|tojson }};
const BASE_TITLE = document.title;
let audioCtx = null;

function getAudio(){
  try{ if(!audioCtx) audioCtx = new (window.AudioContext||window.webkitAudioContext)();
       if(audioCtx.state==='suspended') audioCtx.resume(); }catch(e){}
  return audioCtx;
}
// Browsers only allow sound after a user gesture, so unlock it on the first click/tap.
['click','touchstart','keydown'].forEach(ev =>
  document.addEventListener(ev, getAudio, {once:true}));

function beep(){
  const c = getAudio(); if(!c) return;
  [0,0.35,0.7,1.05].forEach(d=>{
    const o=c.createOscillator(), g=c.createGain();
    o.connect(g); g.connect(c.destination); o.frequency.value=880;
    g.gain.setValueAtTime(0.25, c.currentTime+d);
    o.start(c.currentTime+d); o.stop(c.currentTime+d+0.25);
  });
}
function pad(n){ return String(n).padStart(2,'0'); }
function toMin(hm){ const p=hm.split(':'); return parseInt(p[0])*60+parseInt(p[1]); }

function showToast(m, snoozed){
  const box=document.getElementById('toasts');
  const t=document.createElement('div'); t.className='toast';
  t.innerHTML='<b>💊 Time to take your medicine!</b><br>'+m.name+' — '+m.dosage+
    '<br><small>Scheduled at '+m.time+(snoozed?' (snoozed reminder)':'')+'</small><br>'+
    '<button type="button" class="ok">✅ I took it</button> '+
    '<button type="button" class="no">⏰ Snooze 5 min</button> '+
    '<button type="button">Dismiss</button>';
  const b=t.querySelectorAll('button');
  b[0].onclick=()=>{ fetch('/dose/'+m.id+'/Taken',{method:'POST'}).then(()=>location.reload()); };
  b[1].onclick=()=>{ t.remove(); document.title=BASE_TITLE; setTimeout(()=>showToast(m,true), 5*60*1000); };
  b[2].onclick=()=>{ t.remove(); document.title=BASE_TITLE; };
  box.appendChild(t);
  document.title='⏰ Medicine time! – '+m.name;
  beep();
  try{
    if(window.Notification && Notification.permission==='granted'){
      new Notification('Time to take '+m.name, {body:m.dosage+' — scheduled at '+m.time, requireInteraction:true});
    }
  }catch(e){}
}

function firedKey(m, day){ return 'fired:'+day+':'+m.id+':'+m.time; }
function wasFired(k){ try{ return localStorage.getItem(k); }catch(e){ return null; } }
function markFired(k){ try{ localStorage.setItem(k,'1'); }catch(e){} }

function check(){
  const now=new Date();
  const nowMin=now.getHours()*60+now.getMinutes();
  const day=now.getFullYear()+'-'+pad(now.getMonth()+1)+'-'+pad(now.getDate());
  MEDS.forEach(m=>{
    const diff = nowMin - toMin(m.time);
    // fire at the scheduled minute, or up to 10 minutes late (e.g. page opened just after the time)
    if(diff>=0 && diff<=10){
      const k=firedKey(m,day);
      if(!wasFired(k)){ markFired(k); showToast(m,false); }
    }
  });
  updateNext(now, nowMin);
}

function updateNext(now, nowMin){
  const el=document.getElementById('nextDose');
  if(!MEDS.length){ el.textContent='No medicines scheduled'; return; }
  let best=null, bestWait=1e9;
  MEDS.forEach(m=>{
    let w=toMin(m.time)-nowMin; if(w<0) w+=1440;
    if(w<bestWait){ bestWait=w; best=m; }
  });
  const h=Math.floor(bestWait/60), mi=bestWait%60;
  el.innerHTML='<b>'+best.name+'</b> ('+best.dosage+') at <b>'+best.time+'</b> — in '+
    (h>0?h+' h ':'')+mi+' min';
}

function updatePerm(){
  const perm=document.getElementById('permRow'), ok=document.getElementById('okRow');
  const supported=!!window.Notification;
  const granted=supported && Notification.permission==='granted';
  perm.style.display = (supported && !granted && Notification.permission!=='denied') ? 'block':'none';
  ok.style.display = granted ? 'block':'none';
  if(supported && Notification.permission==='denied'){
    perm.style.display='block';
    perm.innerHTML='<span class="note">Notifications are blocked in your browser. Click the lock icon next to the address bar and allow notifications. On-page popups and sound will still work.</span>';
  }
}
document.getElementById('enableBtn').onclick=()=>{
  beep();
  try{ Notification.requestPermission().then(updatePerm); }catch(e){}
};
updatePerm(); check(); setInterval(check, 15000);
</script>
{% endblock %}
""",

"report.html": """
{% extends 'base.html' %}
{% block body %}
  <div class="card">
    <h2>📅 Weekly Report (last 7 days)
      <button class="noprint" style="float:right" onclick="window.print()">🖨️ Print / Save as PDF</button></h2>
    <div class="stats">
      <div class="stat"><b>{{ w_taken }}</b><span>✅ Taken</span></div>
      <div class="stat"><b>{{ w_missed }}</b><span>❌ Missed</span></div>
      <div class="stat"><b>{{ w_adh }}%</b><span>📊 Weekly Adherence</span></div>
    </div>
    <table>
      <tr><th>Date</th><th>Taken</th><th>Missed</th><th>Chart</th></tr>
      {% for d in days %}
      <tr><td>{{ d.label }}</td><td>{{ d.taken }}</td><td>{{ d.missed }}</td>
        <td><div class="bar">
          {% if d.taken + d.missed > 0 %}
          <i class="t" style="width:{{ d.taken * 100 // (d.taken + d.missed) }}%"></i>
          <i class="m" style="width:{{ d.missed * 100 // (d.taken + d.missed) }}%"></i>
          {% endif %}</div></td></tr>
      {% endfor %}
    </table>
    <p class="note">Green = Taken, Orange = Missed</p>
  </div>

  <div class="card">
    <h2>💊 Medicine-wise Summary</h2>
    <table>
      <tr><th>Medicine</th><th>Taken</th><th>Missed</th><th>Adherence</th></tr>
      {% for r in per_med %}
      <tr><td>{{ r.name }}</td><td>{{ r.taken }}</td><td>{{ r.missed }}</td>
          <td><span class="badge {{ 'good' if r.adh >= 80 else 'warn' if r.adh >= 50 else 'bad' }}">{{ r.adh }}%</span></td></tr>
      {% else %}<tr><td colspan="4" class="empty">No data for this week.</td></tr>{% endfor %}
    </table>
  </div>
  <p class="note">Report generated: {{ now }}</p>
{% endblock %}
"""
}
app.jinja_env.loader = DictLoader(TEMPLATES)


# ---------------- Database ----------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = sqlite3.connect(DB)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS medicines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        dosage TEXT NOT NULL,
        time TEXT NOT NULL,
        stock INTEGER NOT NULL DEFAULT 30,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS doses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicine_id INTEGER,
        medicine_name TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('Taken','Missed')),
        logged_at TEXT NOT NULL,
        logged_date TEXT NOT NULL);
    """)
    db.commit()
    db.close()


# ---------------- Risk (rule-based demo) ----------------
def risk_for(medicine_id):
    rows = get_db().execute(
        "SELECT status FROM doses WHERE medicine_id=? ORDER BY id DESC LIMIT 7",
        (medicine_id,)).fetchall()
    if not rows:
        return {"score": 0, "level": "No data"}
    missed = sum(1 for r in rows if r["status"] == "Missed")
    score = missed / len(rows) * 100
    streak = 0
    for r in rows:
        if r["status"] == "Missed":
            streak += 1
        else:
            break
    score = min(100, round(score + min(streak * 15, 30)))
    level = "Low" if score < 25 else "Medium" if score < 55 else "High"
    return {"score": score, "level": level}


# ---------------- Pages ----------------
@app.route("/")
def dashboard():
    db = get_db()
    meds = [dict(m) for m in db.execute("SELECT * FROM medicines ORDER BY time")]
    for m in meds:
        m["risk"] = risk_for(m["id"])
    total = len(meds)
    taken = db.execute("SELECT COUNT(*) FROM doses WHERE status='Taken'").fetchone()[0]
    missed = db.execute("SELECT COUNT(*) FROM doses WHERE status='Missed'").fetchone()[0]
    adherence = round(taken / (taken + missed) * 100) if (taken + missed) else 0
    history = db.execute("SELECT * FROM doses ORDER BY id DESC LIMIT 20").fetchall()
    low_items = [m for m in meds if m["stock"] <= LOW_STOCK]
    reminders = [{"id": m["id"], "name": m["name"], "dosage": m["dosage"], "time": m["time"]} for m in meds]
    return render_template("index.html", meds=meds, total=total, taken=taken, missed=missed,
                           adherence=adherence, history=history, low_items=low_items,
                           low=LOW_STOCK, reminders=reminders)


@app.post("/add")
def add():
    name = request.form["name"].strip()
    dosage = request.form["dosage"].strip()
    time = request.form["time"]
    try:
        stock = max(0, int(request.form.get("stock", 30)))
    except ValueError:
        stock = 30
    if name and dosage and time:
        db = get_db()
        db.execute("INSERT INTO medicines(name,dosage,time,stock) VALUES(?,?,?,?)",
                   (name, dosage, time, stock))
        db.commit()
    return redirect(url_for("dashboard"))


@app.post("/delete/<int:mid>")
def delete(mid):
    db = get_db()
    db.execute("DELETE FROM medicines WHERE id=?", (mid,))
    db.commit()
    return redirect(url_for("dashboard"))


@app.post("/dose/<int:mid>/<status>")
def dose(mid, status):
    if status in ("Taken", "Missed"):
        db = get_db()
        m = db.execute("SELECT * FROM medicines WHERE id=?", (mid,)).fetchone()
        if m:
            now = datetime.now()
            db.execute(
                "INSERT INTO doses(medicine_id,medicine_name,status,logged_at,logged_date) VALUES(?,?,?,?,?)",
                (mid, m["name"], status, now.strftime("%d %b %Y, %I:%M %p"), now.strftime("%Y-%m-%d")))
            if status == "Taken":
                if m["stock"] > 0:
                    db.execute("UPDATE medicines SET stock=stock-1 WHERE id=?", (mid,))
                else:
                    flash(f"{m['name']} is out of stock! Please refill.")
            db.commit()
            if status == "Taken" and 0 < m["stock"] - 1 <= LOW_STOCK:
                flash(f"{m['name']} is running low ({m['stock'] - 1} left).")
    return redirect(url_for("dashboard"))


@app.route("/report")
def report():
    db = get_db()
    today = datetime.now().date()
    days = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        rows = db.execute(
            "SELECT status, COUNT(*) c FROM doses WHERE logged_date=? GROUP BY status",
            (d.strftime("%Y-%m-%d"),)).fetchall()
        cnt = {r["status"]: r["c"] for r in rows}
        days.append({"label": d.strftime("%a, %d %b"), "taken": cnt.get("Taken", 0),
                     "missed": cnt.get("Missed", 0)})
    w_taken = sum(d["taken"] for d in days)
    w_missed = sum(d["missed"] for d in days)
    w_adh = round(w_taken / (w_taken + w_missed) * 100) if (w_taken + w_missed) else 0
    start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    per_med = []
    for r in db.execute(
        """SELECT medicine_name, SUM(status='Taken') t, SUM(status='Missed') m
           FROM doses WHERE logged_date>=? GROUP BY medicine_name""", (start,)):
        tot = r["t"] + r["m"]
        per_med.append({"name": r["medicine_name"], "taken": r["t"], "missed": r["m"],
                        "adh": round(r["t"] / tot * 100) if tot else 0})
    return render_template("report.html", days=days, w_taken=w_taken, w_missed=w_missed,
                           w_adh=w_adh, per_med=per_med,
                           now=datetime.now().strftime("%d %b %Y, %I:%M %p"))


@app.route("/export.csv")
def export_csv():
    rows = get_db().execute(
        "SELECT medicine_name, status, logged_at FROM doses ORDER BY id DESC").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Medicine", "Status", "Logged at"])
    for r in rows:
        w.writerow([r["medicine_name"], r["status"], r["logged_at"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=meditrack_history.csv"})


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
