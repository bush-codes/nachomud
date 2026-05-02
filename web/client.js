// NachoMUD terminal client.
//
// Landing page + sidebar + xterm. Sidebar lets you switch between your
// player and the 4 AI agents at any time. Anon viewers can spectate
// agents; sign in by email to play your own character.

(function () {
  // ── Terminal ──
  const term = new Terminal({
    fontFamily: 'ui-monospace, "SF Mono", Menlo, Consolas, monospace',
    fontSize: 14,
    cursorBlink: true,
    theme: {
      background: '#0a0a0a',
      foreground: '#d8d8d8',
      cursor: '#5dd',
      brightBlack: '#666',
    },
    convertEol: true,
    scrollback: 5000,
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(document.getElementById('term'));
  window.addEventListener('resize', () => {
    if (!document.getElementById('term').classList.contains('hidden')) fit.fit();
  });

  const status = document.getElementById('status');
  const sidebar = document.getElementById('sidebar-actors');
  const sidebarFooter = document.getElementById('sidebar-footer');
  const accountWho = document.getElementById('account-who');
  const logoutBtn = document.getElementById('logout-link');
  const termEl = document.getElementById('term');
  const landingEl = document.getElementById('landing');
  // Auth form was removed during the Coming-Soon period. The send-link /
  // email-input / auth-msg elements no longer exist; their handlers below
  // are gated on element presence so this still works once we add a form
  // back. Until then, /auth/request can be POSTed directly for the
  // operator to sign in.
  const emailInput = document.getElementById('email-input');
  const sendBtn = document.getElementById('send-link');
  const authMsg = document.getElementById('auth-msg');

  // ── Landing / xterm visibility ──
  let isLoggedIn = false;
  function showXterm() {
    landingEl.classList.add('hidden');
    termEl.classList.remove('hidden');
    fit.fit();
  }
  function showLanding() {
    termEl.classList.add('hidden');
    landingEl.classList.remove('hidden');
  }
  function applyView() {
    // Logged-in users always see the xterm (their character / welcome flow).
    // Anon visitors see the xterm only while spectating an agent; otherwise
    // the landing page is in front so they can sign in.
    const spectatingAgent = !!activeActorId;
    if (isLoggedIn || spectatingAgent) showXterm();
    else showLanding();
  }

  // ── Auth status check (run once on load) ──
  (async function checkAuth() {
    console.log('[nachomud] checkAuth start, url=', location.href);
    // Auth fetch FIRST — never let URL/history quirks block this.
    try {
      console.log('[nachomud] fetching /auth/me');
      const r = await fetch('/auth/me', {
        credentials: 'same-origin',
        cache: 'no-store',
      });
      const me = await r.json();
      console.log('[nachomud] /auth/me ->', me);
      isLoggedIn = !!me.logged_in;
      if (isLoggedIn) {
        accountWho.textContent = me.email || '';
        sidebarFooter.classList.remove('hidden');
      } else {
        sidebarFooter.classList.add('hidden');
      }
    } catch (e) {
      console.error('[nachomud] /auth/me failed', e);
      isLoggedIn = false;
    }
    // URL housekeeping — render auth=invalid notice; strip the auth= param.
    try {
      const params = new URLSearchParams(location.search);
      if (params.get('auth') === 'invalid' && authMsg) {
        authMsg.textContent = 'That sign-in link expired or was already used. Try again.';
        authMsg.className = 'err';
      }
      if (params.has('auth')) {
        history.replaceState({}, '', location.pathname);
      }
    } catch (e) {
      console.warn('[nachomud] URL cleanup failed', e);
    }
    console.log('[nachomud] applying view, isLoggedIn=', isLoggedIn);
    applyView();
  })();

  // ── Logout ──
  logoutBtn.addEventListener('click', async () => {
    try {
      await fetch('/auth/logout', { method: 'POST', credentials: 'same-origin' });
    } catch (_) {}
    location.reload();
  });

  // ── Sign-in form handler ──
  // Skip wiring entirely if the form isn't in the DOM (Coming-Soon mode).
  if (sendBtn && emailInput && authMsg) {
    async function submitEmail() {
      const email = (emailInput.value || '').trim();
      if (!email || !email.includes('@')) {
        authMsg.textContent = 'Enter a valid email address.';
        authMsg.className = 'err';
        return;
      }
      sendBtn.disabled = true;
      authMsg.textContent = 'Sending…';
      authMsg.className = '';
      try {
        const r = await fetch('/auth/request', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ email }),
        });
        const data = await r.json();
        if (data.ok) {
          authMsg.textContent = `Check ${email} for a sign-in link.`;
          authMsg.className = 'ok';
          emailInput.disabled = true;
        } else {
          authMsg.textContent = data.error || 'Could not send the link.';
          authMsg.className = 'err';
          sendBtn.disabled = false;
        }
      } catch (_) {
        authMsg.textContent = 'Network error — try again.';
        authMsg.className = 'err';
        sendBtn.disabled = false;
      }
    }
    sendBtn.addEventListener('click', submitEmail);
    emailInput.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') submitEmail();
    });
  }

  // ── Cookie consent banner ──
  const COOKIE_ACK_KEY = 'nachomud.cookie_acked';
  const cookieBanner = document.getElementById('cookie-banner');
  const cookieAck = document.getElementById('cookie-ack');
  let cookieAcked = false;
  try { cookieAcked = !!localStorage.getItem(COOKIE_ACK_KEY); } catch (_) {}
  if (!cookieAcked) cookieBanner.classList.remove('hidden');
  cookieAck.addEventListener('click', () => {
    cookieBanner.classList.add('hidden');
    try { localStorage.setItem(COOKIE_ACK_KEY, '1'); } catch (_) {}
  });

  // ── Per-line input buffer ──
  let buffer = '';
  let prompt = '';
  let mode = 'connecting';
  const history = [];
  const HISTORY_MAX = 200;
  let histIdx = -1;
  let liveBuffer = '';

  function pushHistory(text) {
    if (!text) return;
    if (history.length > 0 && history[history.length - 1] === text) return;
    history.push(text);
    if (history.length > HISTORY_MAX) history.shift();
  }

  function browseHistory(delta) {
    if (history.length === 0) return;
    if (histIdx === -1) {
      if (delta >= 0) return;
      liveBuffer = buffer;
      histIdx = history.length - 1;
      buffer = history[histIdx];
      rerenderLine();
      return;
    }
    const next = histIdx + delta;
    if (next < 0) return;
    if (next >= history.length) {
      histIdx = -1;
      buffer = liveBuffer;
      liveBuffer = '';
      rerenderLine();
      return;
    }
    histIdx = next;
    buffer = history[histIdx];
    rerenderLine();
  }

  let thinkingText = '';
  let thinkingFrame = 0;
  let thinkingTimer = null;
  let thinkingActive = false;
  const SPINNER = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

  function setStatus(text, cls) {
    status.textContent = text;
    status.className = cls || '';
  }

  function writePrompt() {
    term.write(prompt);
    term.write(buffer);
  }
  function rerenderLine() {
    term.write('\x1b[2K\r');
    writePrompt();
  }
  function backspace() {
    if (buffer.length === 0) return;
    buffer = buffer.slice(0, -1);
    term.write('\b \b');
  }

  function startThinking(text) {
    stopThinking();
    thinkingText = text;
    thinkingFrame = 0;
    thinkingActive = true;
    term.write('\r\x1b[2K');
    drawThinking();
    thinkingTimer = setInterval(() => {
      thinkingFrame = (thinkingFrame + 1) % SPINNER.length;
      term.write('\r\x1b[2K');
      drawThinking();
    }, 100);
  }
  function drawThinking() {
    term.write('\x1b[2;90m' + SPINNER[thinkingFrame] + ' ' + thinkingText + '\x1b[0m');
  }
  function stopThinking() {
    if (thinkingTimer !== null) { clearInterval(thinkingTimer); thinkingTimer = null; }
    if (thinkingActive) {
      term.write('\r\x1b[2K');
      thinkingActive = false;
      thinkingText = '';
    }
  }

  // ── Sidebar state ──
  let roster = {};
  let myActorId = '';
  let activeActorId = '';
  const actorStatus = {};

  const AGENT_ORDER = [
    'agent_scholar', 'agent_berserker', 'agent_wanderer', 'agent_zealot',
  ];

  function renderSidebar() {
    sidebar.innerHTML = '';

    // My Player row
    const meRow = document.createElement('button');
    meRow.className = 'actor my-player';
    if (!myActorId) meRow.classList.add('placeholder');
    if (myActorId && roster[myActorId]) {
      const a = roster[myActorId];
      meRow.dataset.actorId = myActorId;
      meRow.innerHTML = `
        <div class="display">My Player</div>
        <div class="name">${escapeHtml(a.name)}</div>
        <div class="meta">${escapeHtml(a.race + ' ' + a.class + ' L' + a.level)}</div>
        <div class="stats"></div>
      `;
    } else {
      meRow.dataset.actorId = '';
      meRow.innerHTML = `
        <div class="display">My Player</div>
        <div class="name">create / load…</div>
        <div class="meta">no character yet</div>
      `;
    }
    if (activeActorId === myActorId || (!myActorId && !activeActorId)) {
      meRow.classList.add('active');
    }
    meRow.addEventListener('click', () => {
      if (myActorId) subscribe(myActorId);
      else subscribe('');
    });
    sidebar.appendChild(meRow);

    // 4 agent rows in declared order
    for (const aid of AGENT_ORDER) {
      const a = roster[aid];
      const row = document.createElement('button');
      row.className = 'actor agent';
      row.dataset.actorId = aid;
      if (activeActorId === aid) row.classList.add('active');
      if (a && a.alive === false) row.classList.add('dead');
      const display = a ? a.display_name : aid;
      const name = a ? a.name : '—';
      const meta = a ? `${a.race} ${a.class} L${a.level}` : 'connecting…';
      row.innerHTML = `
        <div class="display">${escapeHtml(display)}</div>
        <div class="name">${escapeHtml(name)}</div>
        <div class="meta">${escapeHtml(meta)}</div>
        <div class="stats"></div>
      `;
      row.addEventListener('click', () => subscribe(aid));
      sidebar.appendChild(row);
    }

    // Map row — special pseudo-actor: shows the global ASCII map
    // (union of every actor's explored rooms) in the xterm pane.
    // Not a WS subscription; just a one-shot fetch of /map.
    const mapRow = document.createElement('button');
    mapRow.className = 'actor map';
    if (activeActorId === '_map') mapRow.classList.add('active');
    mapRow.innerHTML = `
      <div class="display">Map</div>
      <div class="name">World atlas</div>
      <div class="meta">where the agents have been</div>
    `;
    mapRow.addEventListener('click', showMap);
    sidebar.appendChild(mapRow);

    for (const aid of Object.keys(actorStatus)) paintStats(aid);
  }

  async function showMap() {
    activeActorId = '_map';
    renderSidebar();
    showXterm();
    term.clear();
    term.writeln('\x1b[36mFetching world map…\x1b[0m');
    try {
      const r = await fetch('/map', { credentials: 'same-origin' });
      const data = await r.json();
      term.clear();
      // Convert \n to xterm-friendly \r\n.
      term.write((data.map || '(empty)').replace(/\n/g, '\r\n'));
      term.writeln('');
      term.writeln('\x1b[2m(click an agent or your character to switch back)\x1b[0m');
    } catch (e) {
      term.writeln('\x1b[31mFailed to load map: ' + e + '\x1b[0m');
    }
  }

  function paintStats(actorId) {
    const s = actorStatus[actorId];
    if (!s) return;
    const row = sidebar.querySelector(`[data-actor-id="${cssEscape(actorId)}"]`);
    if (!row) return;
    const slot = row.querySelector('.stats');
    if (!slot) return;
    const hp = `HP ${s.hp ?? '?'}/${s.max_hp ?? '?'}`;
    const ac = s.ac !== undefined ? `AC ${s.ac}` : '';
    const lv = s.level !== undefined ? `L${s.level}` : '';
    const xp = s.xp !== undefined ? `XP ${s.xp}` : '';
    const mp = s.mp ? `MP ${s.mp}/${s.max_mp}` : '';
    slot.innerHTML = `
      <div class="bar"><span>${hp}</span><span>${ac}${ac && lv ? ' · ' : ''}${lv}</span></div>
      <div class="bar"><span>${mp}</span><span>${xp}</span></div>
    `;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }
  function cssEscape(s) {
    return String(s).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }
  function isSpectating() {
    return !!activeActorId && activeActorId !== myActorId;
  }
  function renderSpectatingNotice() {
    if (isSpectating()) {
      const a = roster[activeActorId];
      const who = a ? (a.display_name || a.name) : activeActorId;
      term.write(
        `\x1b[2;33m(Spectating ${who} — input is disabled. ` +
        `Click "My Player" to return to your character.)\x1b[0m\r\n\r\n`
      );
    }
  }

  // ── WebSocket ──
  const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://')
    + location.host + '/ws';
  const ws = new WebSocket(wsUrl);

  ws.addEventListener('open', () => setStatus('connected', 'ok'));
  ws.addEventListener('close', () => setStatus('disconnected', 'err'));
  ws.addEventListener('error', () => setStatus('error', 'err'));

  function subscribe(actorId) {
    if (ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'subscribe', actor_id: actorId }));
  }

  ws.addEventListener('message', (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.type !== 'thinking' && thinkingActive) stopThinking();

    switch (msg.type) {
      case 'actor_list': {
        roster = {};
        for (const a of (msg.actors || [])) roster[a.actor_id] = a;
        renderSidebar();
        break;
      }
      case 'you': {
        myActorId = msg.actor_id || '';
        renderSidebar();
        break;
      }
      case 'subscribed': {
        // Server arms the new view here BEFORE replaying transcript.
        activeActorId = msg.actor_id || '';
        prompt = '';
        buffer = '';
        term.clear();
        renderSidebar();
        applyView();
        renderSpectatingNotice();
        break;
      }
      case 'output':
        if (!msg.actor_id || msg.actor_id === activeActorId) term.write(msg.text || '');
        break;
      case 'prompt':
        if (!msg.actor_id || msg.actor_id === activeActorId) {
          prompt = msg.text || '> ';
          buffer = '';
          term.write('\r\x1b[2K');
          term.write(prompt);
        }
        break;
      case 'mode':
        mode = msg.mode;
        setStatus('connected · ' + mode, 'ok');
        break;
      case 'status': {
        const aid = msg.actor_id || activeActorId || '';
        actorStatus[aid] = msg;
        paintStats(aid);
        if (!msg.actor_id || msg.actor_id === activeActorId) {
          const parts = [];
          if (msg.hp !== undefined) parts.push(`HP ${msg.hp}/${msg.max_hp ?? '?'}`);
          if (msg.mp) parts.push(`MP ${msg.mp}/${msg.max_mp}`);
          if (msg.ap) parts.push(`AP ${msg.ap}/${msg.max_ap}`);
          setStatus(parts.join(' · ') || ('connected · ' + mode), 'ok');
        }
        break;
      }
      case 'thinking':
        if (msg.text) startThinking(msg.text);
        else stopThinking();
        break;
      default:
        break;
    }
  });

  // Initial sidebar render before the actor_list arrives so users see "My Player"
  renderSidebar();

  // ── Input handling ──
  function handleArrow(ev) {
    if (ev.type !== 'keydown') return false;
    if (ev.key === 'ArrowUp') { ev.preventDefault(); ev.stopPropagation(); browseHistory(-1); return true; }
    if (ev.key === 'ArrowDown') { ev.preventDefault(); ev.stopPropagation(); browseHistory(+1); return true; }
    return false;
  }
  document.addEventListener('keydown', (ev) => {
    const t = document.getElementById('term');
    if (!t) return;
    const target = ev.target;
    const insideTerm = t.contains(target) || target === document.body;
    if (!insideTerm) return;
    handleArrow(ev);
  }, true);
  term.attachCustomKeyEventHandler((ev) => {
    if (handleArrow(ev)) return false;
    if (ev.type === 'keydown' && (ev.ctrlKey || ev.metaKey) && (ev.key === 'c' || ev.key === 'C')) return false;
    return true;
  });

  term.onKey(({ key, domEvent }) => {
    const ev = domEvent;
    if (isSpectating()) {
      ev.preventDefault?.();
      return;
    }
    if (ev.key === 'Enter') {
      const text = buffer;
      term.write('\r\n');
      pushHistory(text);
      buffer = ''; histIdx = -1; liveBuffer = '';
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'command', text }));
      }
      return;
    }
    if (ev.key === 'Backspace') { backspace(); return; }
    if (ev.key === 'Tab') { ev.preventDefault(); return; }
    if (ev.ctrlKey && ev.key === 'l') { ev.preventDefault(); term.clear(); writePrompt(); return; }
    if (ev.ctrlKey && ev.key === 'u') {
      ev.preventDefault();
      buffer = ''; histIdx = -1; liveBuffer = '';
      rerenderLine();
      return;
    }
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return;
    if (key.length === 1 && key.charCodeAt(0) >= 32) {
      buffer += key;
      term.write(key);
    }
  });
})();
