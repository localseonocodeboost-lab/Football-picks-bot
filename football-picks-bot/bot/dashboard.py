"""Generate docs/index.html — a personal version of the site's performance page."""
import html
import os
from datetime import date, datetime

OUT = os.path.join("docs", "index.html")
STAKE = 10.0


def build(db):
    picks = db["picks"]
    settled = [p for p in picks if p["status"] in ("won", "lost")]
    won = [p for p in settled if p["status"] == "won"]
    lost = [p for p in settled if p["status"] == "lost"]
    pending = [p for p in picks if p["status"] == "pending"]
    win_rate = 100 * len(won) / len(settled) if settled else 0
    profit = sum(p["profit"] or 0 for p in settled)
    staked = STAKE * len(settled)
    roi = 100 * profit / staked if staked else 0

    month = date.today().strftime("%Y-%m")
    m_settled = [p for p in settled if p["date"].startswith(month)]
    m_won = sum(1 for p in m_settled if p["status"] == "won")

    today = date.today().isoformat()
    todays = [p for p in picks if p["date"] == today]

    rows = []
    for p in sorted(picks, key=lambda x: x["date"], reverse=True):
        if p["status"] == "won":
            badge = '<span class="badge win">✓ Won</span>'
        elif p["status"] == "lost":
            badge = '<span class="badge loss">✗ Lost</span>'
        elif p["status"] == "void":
            badge = '<span class="badge void">— Void</span>'
        else:
            badge = '<span class="badge pend">⏳ Pending</span>'
        score = f' · {p["score"]}' if p.get("score") else ""
        rows.append(f"""
        <div class="row">
          <div>
            <div class="match">{html.escape(p['home'])} v {html.escape(p['away'])}</div>
            <div class="detail">{html.escape(p['market_label'])} @ {p['odds']}
              · {html.escape(p['league'])} · {p['date']}{score}</div>
          </div>
          {badge}
        </div>""")

    today_cards = []
    for p in todays:
        today_cards.append(f"""
        <div class="pick-card">
          <div class="match">{html.escape(p['home'])} v {html.escape(p['away'])}</div>
          <div class="market">{html.escape(p['market_label'])} @ {p['odds']}
            <span class="edge">model {p['model_prob']:.0%} · edge +{p['edge']:.1%}</span></div>
          <p class="reason">{html.escape(p['reasoning'])}</p>
        </div>""")
    if not today_cards:
        today_cards = ['<p class="muted">No picks passed the value filter today.</p>']

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, must-revalidate">
<title>My Betting Bot — Track Record</title>
<script>
  // Re-load the page every 10 min (cache-busted) so an open tab stays current.
  setTimeout(() => location.replace(location.pathname + "?t=" + Date.now()), 600000);
  // Also refresh when the phone returns to the tab after 5+ min away.
  let hiddenAt = null;
  document.addEventListener("visibilitychange", () => {{
    if (document.hidden) hiddenAt = Date.now();
    else if (hiddenAt && Date.now() - hiddenAt > 300000)
      location.replace(location.pathname + "?t=" + Date.now());
  }});
</script>
<style>
  :root {{ --bg:#0b0f14; --card:#141b24; --line:#233040; --text:#e8eef5;
           --muted:#8fa1b3; --green:#2ecc71; --red:#e74c3c; --accent:#4da3ff; }}
  * {{ box-sizing:border-box; margin:0; }}
  body {{ background:var(--bg); color:var(--text);
         font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif; padding:32px 16px; }}
  .wrap {{ max-width:860px; margin:0 auto; }}
  h1 {{ font-size:2rem; margin-bottom:4px; }}
  .sub {{ color:var(--muted); margin-bottom:28px; }}
  .stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
            gap:12px; margin-bottom:32px; }}
  .stat {{ background:var(--card); border:1px solid var(--line);
           border-radius:12px; padding:18px; }}
  .stat .label {{ color:var(--muted); font-size:.8rem; text-transform:uppercase;
                  letter-spacing:.05em; }}
  .stat .value {{ font-size:1.7rem; font-weight:700; margin-top:4px; }}
  .stat .note {{ color:var(--muted); font-size:.8rem; }}
  h2 {{ font-size:1.2rem; margin:28px 0 12px; }}
  .pick-card {{ background:var(--card); border:1px solid var(--line);
                border-radius:12px; padding:16px; margin-bottom:10px; }}
  .pick-card .market {{ color:var(--accent); margin:4px 0; }}
  .edge {{ color:var(--muted); font-size:.85rem; margin-left:8px; }}
  .reason {{ color:var(--muted); font-size:.9rem; margin-top:6px; }}
  .row {{ display:flex; justify-content:space-between; align-items:center;
          gap:12px; background:var(--card); border:1px solid var(--line);
          border-radius:10px; padding:12px 16px; margin-bottom:8px; }}
  .match {{ font-weight:600; }}
  .detail {{ color:var(--muted); font-size:.85rem; }}
  .badge {{ padding:4px 10px; border-radius:999px; font-size:.8rem;
            font-weight:600; white-space:nowrap; }}
  .win {{ background:rgba(46,204,113,.12); color:var(--green); }}
  .loss {{ background:rgba(231,76,60,.12); color:var(--red); }}
  .pend {{ background:rgba(77,163,255,.12); color:var(--accent); }}
  .void {{ background:rgba(143,161,179,.15); color:var(--muted); }}
  .muted {{ color:var(--muted); }}
  .pos {{ color:var(--green); }} .neg {{ color:var(--red); }}
  footer {{ margin-top:40px; padding-top:16px; border-top:1px solid var(--line);
            color:var(--muted); font-size:.8rem; }}
</style></head><body><div class="wrap">
  <h1>My Betting Bot</h1>
  <p class="sub">Personal football model · every pick tracked, wins and losses ·
    updated {datetime.now().strftime('%d %b %Y %H:%M')}</p>

  <div class="stats">
    <div class="stat"><div class="label">Win rate</div>
      <div class="value">{win_rate:.1f}%</div>
      <div class="note">{len(settled)} settled · {len(pending)} pending</div></div>
    <div class="stat"><div class="label">Record</div>
      <div class="value">{len(won)}W — {len(lost)}L</div>
      <div class="note">from {len(settled)} picks</div></div>
    <div class="stat"><div class="label">This month</div>
      <div class="value">{m_won}W — {len(m_settled) - m_won}L</div>
      <div class="note">{len(m_settled)} settled · {date.today().strftime('%B')}</div></div>
    <div class="stat"><div class="label">P/L @ £{STAKE:.0f} stakes</div>
      <div class="value {'pos' if profit >= 0 else 'neg'}">{profit:+.0f}</div>
      <div class="note">ROI {roi:+.1f}%</div></div>
  </div>

  <h2>Today's picks</h2>
  {''.join(today_cards)}

  <h2>All results</h2>
  {''.join(rows) if rows else '<p class="muted">No picks yet — run the bot.</p>'}

  <footer>⚠️ Personal statistical model for entertainment. Past performance does
  not guarantee future results. Only bet what you can afford to lose.
  18+ · BeGambleAware.org · GamCare 0808 8020 133</footer>
</div></body></html>"""

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Dashboard written to {OUT}")
