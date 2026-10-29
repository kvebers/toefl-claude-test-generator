'use strict';
// TOEFL iBT practice runner. Flow: home -> checks -> for each section: intro, module 1, (adaptive) module 2 -> submit.
// Answer keys never reach the browser; adaptive routing and scoring happen on the server.

const params = new URLSearchParams(location.search);
const SPEED = Number(params.get('fast')) || 1;          // ?fast=10 compresses every timer (for development)
const $ = (sel, el = document) => el.querySelector(sel);

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
  return el;
}

const api = {
  async get(url) { const r = await fetch(url); const j = await r.json(); if (!r.ok) throw new Error(j.error || r.status); return j; },
  async post(url, body, raw = false) {
    const r = await fetch(url, raw ? { method: 'POST', body, headers: { 'Content-Type': body.type || 'application/octet-stream' } }
                                   : { method: 'POST', body: JSON.stringify(body ?? {}), headers: { 'Content-Type': 'application/json' } });
    const j = await r.json(); if (!r.ok) throw Object.assign(new Error(j.error || r.status), { details: j.details }); return j;
  },
};

let CFG, TEST, AUDIO, AID, MIC = null, HOME_EDITION = false;
let R = { tasks: {}, meta: { routes: {}, fullscreen_exits: 0, task_seconds: {} } };

// ------------------------------------------------------------------ top bar + timer
const bar = {
  section(t) { $('#bar-section').textContent = t || ''; },
  progress(t) { $('#bar-progress').textContent = t || ''; },
  next(label, onClick, enabled = true) {
    const b = $('#bar-next'); b.hidden = !label; b.textContent = label || ''; b.disabled = !enabled; b.onclick = onClick;
  },
  enableNext(on) { $('#bar-next').disabled = !on; },
  steps(active) {   // section stepper; active = section id or null to hide
    const order = TEST && active ? TEST.sections.map(s => s.id) : [];
    const at = order.indexOf(active);
    $('#stepper').replaceChildren(...order.map((id, i) =>
      h('span', { class: i < at ? 'done' : i === at ? 'active' : '' }, CFG.spec.sections[id].title)));
  },
  fill(frac) { $('#progress-fill').style.width = `${Math.round(Math.min(1, Math.max(0, frac)) * 100)}%`; },
};

class Timer {
  constructor(seconds, onExpire) { this.left = seconds; this.onExpire = onExpire; this.paused = false; }
  start() { this.render(); this.iv = setInterval(() => this.tick(), 1000 / SPEED); return this; }
  tick() { if (this.paused) return; this.left -= 1; this.render(); if (this.left <= 0) { this.stop(); this.onExpire(); } }
  pause() { this.paused = true; this.render(); }
  resume() { this.paused = false; this.render(); }
  stop() { clearInterval(this.iv); $('#bar-timer').hidden = true; }
  render() {
    const t = $('#bar-timer'), s = Math.max(0, this.left);
    t.hidden = false; t.textContent = `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    t.classList.toggle('low', s <= 60); t.classList.toggle('paused', this.paused);
  }
}

// ------------------------------------------------------------------ screens
let current = null;
function show(build) {
  return new Promise(resolve => {
    const screen = h('div', { class: 'screen' });
    $('#app').replaceChildren(screen); window.scrollTo({ top: 0 });
    const finish = v => { if (current && current.resolve === resolve) { current = null; bar.next(null); resolve(v); } };
    current = { resolve, finish };
    build(screen, finish);
  });
}
const expireCurrent = () => current && current.finish({ expired: true });

let saveTimer;
function save() { clearTimeout(saveTimer); saveTimer = setTimeout(() => AID && api.post(`/api/attempts/${AID}/responses`, R).catch(console.error), 300); }
const taskResp = (id, init) => (R.tasks[id] ??= init);

// ------------------------------------------------------------------ audio
let ctx;
function beep(freq = 880, ms = 250) {
  ctx ??= new AudioContext();
  const o = ctx.createOscillator(), g = ctx.createGain();
  o.frequency.value = freq; g.gain.value = 0.15; o.connect(g).connect(ctx.destination); o.start(); o.stop(ctx.currentTime + ms / 1000);
  return new Promise(r => setTimeout(r, ms + 150));
}

const sleep = ms => new Promise(r => setTimeout(r, ms / SPEED));

function speak(text, voiceName) {
  return new Promise(resolve => {
    const u = new SpeechSynthesisUtterance(text);
    const voices = speechSynthesis.getVoices().filter(v => v.lang.startsWith('en'));
    if (voices.length) u.voice = voices[Math.abs([...(voiceName || '')].reduce((a, c) => a + c.charCodeAt(0), 0)) % voices.length];
    u.rate = 0.95; u.onend = u.onerror = () => resolve();
    speechSynthesis.speak(u);
  });
}

async function playClip(key, onLine) {
  const lines = AUDIO?.[key] || [];
  for (const [i, line] of lines.entries()) {
    onLine?.(line, i, lines.length);
    if (line.file && SPEED === 1) {
      await new Promise(resolve => {
        const a = new Audio(`/media/${TEST.id}/${line.file}`);
        a.onended = a.onerror = () => resolve(); a.play().catch(() => resolve());
      });
    } else if (SPEED === 1) await speak(line.text, line.voice);
    else await sleep(800);
    await sleep(350);
  }
}

async function ensureMic() {
  if (!MIC) MIC = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  return MIC;
}

function record(key, seconds, onTick) {
  return new Promise(async resolve => {
    const rec = new MediaRecorder(await ensureMic()), chunks = [];
    rec.ondataavailable = e => e.data.size && chunks.push(e.data);
    rec.onstop = async () => {
      const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
      if (AID) await api.post(`/api/attempts/${AID}/recording?key=${encodeURIComponent(key)}`, blob, true).catch(console.error);
      resolve(blob);
    };
    rec.start();
    let left = seconds; onTick?.(left, seconds);
    const iv = setInterval(() => { left -= 1; onTick?.(left, seconds); if (left <= 0) { clearInterval(iv); rec.stop(); } }, 1000 / SPEED);
  });
}

// ------------------------------------------------------------------ directions
const DIRECTIONS = {
  complete_the_words: 'Fill in the missing letters in the paragraph.',
  daily_life: 'Read a text from everyday life and answer the questions.',
  academic_passage: 'Read an academic passage and answer the questions.',
  choose_response: 'You will hear a person speak. Choose the best response. You will hear the speaker only once.',
  conversation: 'Listen to a conversation. Then answer the questions. You will hear the conversation only once.',
  announcement: 'Listen to an announcement. Then answer the questions. You will hear it only once.',
  academic_talk: 'Listen to part of an academic talk. Then answer the questions. You will hear it only once.',
  build_sentence: 'Make an appropriate sentence by putting the words and phrases in the correct order.',
  email: 'Read the situation and write an email. Address every point.',
  academic_discussion: 'Your professor is teaching a class. Write a post responding to the professor\'s question. Express and support your opinion and contribute to the discussion. An effective response contains at least 100 words.',
  listen_and_repeat: 'Listen to the speaker and repeat exactly what you hear. You will hear each sentence only once. Recording starts automatically after the beep.',
  interview: 'An interviewer will ask you questions. Answer each one as fully as you can. Recording starts automatically after the beep; you have no preparation time.',
};
const SECTION_INFO = {
  reading: 'This section measures your ability to understand written English. The section has two parts; the second part depends on how you do in the first.',
  listening: 'This section measures your ability to understand spoken English. Each recording plays only once. The clock stops while audio plays.',
  writing: 'This section measures your ability to write in English. Each task has its own time limit. Spell-check is turned off.',
  speaking: 'This section measures your ability to speak English. Speak clearly into your microphone. Responses are recorded automatically.',
};

function directionsScreen(title, text) {
  return show((app, done) => {
    app.append(h('div', { class: 'panel stack narrow' }, h('h1', {}, title), h('p', {}, text),
      h('p', { class: 'muted' }, 'Select Continue when you are ready.')));
    bar.next('Continue', () => done());
  });
}

// ------------------------------------------------------------------ task renderers
function mcqBlock(q, resp, onChange) {
  const opts = h('div', { class: 'options', role: 'radiogroup' });
  q.options.forEach((o, i) => {
    const input = h('input', { type: 'radio', name: q.id, checked: resp.answers[q.id] === i });
    const lab = h('label', { class: 'option' + (resp.answers[q.id] === i ? ' selected' : '') }, input, h('span', {}, o));
    input.onchange = () => { resp.answers[q.id] = i; opts.querySelectorAll('.option').forEach(x => x.classList.remove('selected')); lab.classList.add('selected'); save(); onChange?.(); };
    opts.append(lab);
  });
  return h('div', {}, h('p', { class: 'question' }, q.prompt), opts);
}

const counter = { n: 0, total: 0 };
const progress = (span = 1) => bar.progress(!counter.total ? '' : span > 1
  ? `Questions ${counter.n - span + 1}–${counter.n} of ${counter.total}` : `Question ${Math.min(counter.n, counter.total)} of ${counter.total}`);

async function readingTask(task, expired) {
  const resp = taskResp(task.id, task.type === 'complete_the_words' ? { gaps: [] } : { answers: {} });
  if (task.type === 'complete_the_words') {
    const nGaps = task.segments.filter(s => 'gap' in s).length;
    counter.n += nGaps; progress(nGaps);
    return show((app, done) => {
      const p = h('p', { class: 'ctw' }), inputs = [];
      // A full gap jumps to the next one; Backspace in an empty gap and Space/Enter move between gaps.
      const go = (i, atEnd) => { const el = inputs[i]; if (!el) return; el.focus(); const n = atEnd ? el.value.length : 0; el.setSelectionRange(n, n); };
      for (const s of task.segments) {
        if ('t' in s) { p.append(s.t); continue; }
        const i = inputs.length;
        const input = h('input', {
          maxlength: s.len, value: resp.gaps[s.gap] || '', spellcheck: 'false', autocomplete: 'off', autocapitalize: 'off',
          style: `--len: ${s.len}`, 'aria-label': `missing letters after ${s.prefix}`,
          oninput: e => {
            const v = e.target.value.replace(/\s+/g, '');
            if (v !== e.target.value) e.target.value = v;
            resp.gaps[s.gap] = v; save();
            if (v.length >= s.len && e.inputType !== 'deleteContentBackward') go(i + 1);
          },
          onkeydown: e => {
            if (e.key === 'Backspace' && !e.target.value) { e.preventDefault(); go(i - 1, true); }
            else if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); go(i + 1); }
          },
        });
        inputs.push(input);
        p.append(h('span', { class: 'ctw-word' }, s.prefix, input));
      }
      app.append(h('div', { class: 'panel narrow' }, h('p', { class: 'instructions' }, task.title || DIRECTIONS.complete_the_words), p));
      bar.next('Next', () => done());
    });
  }
  for (const q of task.questions) {
    if (expired()) return;
    counter.n += 1; progress();
    await show((app, done) => {
      const body = passageBody(task.text.body, q.prompt);
      app.append(h('div', { class: 'split' },
        h('div', { class: 'panel passage' }, task.text.genre && h('div', { class: 'genre' }, task.text.genre), h('h3', {}, task.text.title), body),
        h('div', { class: 'panel' }, mcqBlock(q, resp))));
      bar.next('Next', () => done());
      const mark = body.querySelector('mark'), pane = body.parentElement;   // scroll the passage panel only, not the page
      if (mark) pane.scrollTop += mark.getBoundingClientRect().top - pane.getBoundingClientRect().top - pane.clientHeight / 2;
    });
  }
}

// "The word "scarce" in paragraph 2 is closest in meaning to": highlight that word in the passage, as on the real test.
function passageBody(text, prompt) {
  const out = h('span');
  const m = /\b(?:word|phrase)\s+["“'‘](.+?)["”'’]\s+in\s+paragraph\s+(\d+)/i.exec(prompt || '');
  if (!m) { out.append(text); return out; }
  const word = new RegExp(`(?<![A-Za-z])${m[1].replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Za-z])`, 'i');
  const parts = text.split(/(\n\s*\n)/);   // odd entries are the separators, kept so pre-line spacing is unchanged
  const nth = 2 * (Number(m[2]) - 1);
  const pick = word.test(parts[nth] ?? '') ? nth : parts.findIndex((p, i) => i % 2 === 0 && word.test(p));
  for (const [i, part] of parts.entries()) {
    const hit = i === pick && word.exec(part);
    if (!hit) { out.append(part); continue; }
    out.append(part.slice(0, hit.index), h('mark', { class: 'vocab' }, hit[0]), part.slice(hit.index + hit[0].length));
  }
  return out;
}

async function listeningTask(task, timer, expired) {
  const resp = taskResp(task.id, { answers: {} });
  timer?.pause();
  await show(async (app, done) => {
    const who = h('p', { class: 'muted status' }), meter = h('div', { class: 'meter' }, h('div'));
    const orb = h('div', { class: 'orb live', 'aria-hidden': 'true' }, '🎧');
    app.append(h('div', { class: 'panel player narrow' }, orb, h('h2', {}, task.context || DIRECTIONS[task.type]), who, meter));
    await playClip(task.id, (line, i, n) => { who.textContent = `${line.speaker} is speaking…`; meter.firstChild.style.width = `${(100 * (i + 1)) / n}%`; });
    orb.classList.remove('live'); who.textContent = 'Now answer the questions.';
    await sleep(500);
    done();
  });
  timer?.resume();
  for (const q of task.questions) {
    if (expired()) return;
    counter.n += 1; progress();
    await show((app, done) => {
      app.append(h('div', { class: 'panel narrow' }, task.context && h('p', { class: 'instructions' }, task.context),
        mcqBlock(q, resp, () => bar.enableNext(true))));
      bar.next('Next', () => done(), resp.answers[q.id] != null);
    });
  }
}

async function buildSentenceTask(task, expired) {
  const resp = taskResp(task.id, { items: {} });
  for (const [idx, it] of task.items.entries()) {
    if (expired()) return;
    bar.progress(`Sentence ${idx + 1} of ${task.items.length}`);
    await show((app, done) => {
      const placed = resp.items[it.id] ?? (resp.items[it.id] = []);
      const line = h('div', { class: 'answer-line' }), pool = h('div', { class: 'row' });
      const render = () => {
        line.classList.toggle('filled', placed.length === it.chunks.length);
        line.replaceChildren(...[it.start && h('span', { class: 'fixed' }, it.start),
          ...placed.map((c, i) => h('button', { class: 'chunk', onclick: () => { placed.splice(i, 1); save(); render(); } }, c)),
          it.end && h('span', { class: 'fixed' }, it.end)].filter(Boolean));
        const used = [...placed];
        pool.replaceChildren(...it.chunks.map(c => {
          const k = used.indexOf(c); const isUsed = k >= 0; if (isUsed) used.splice(k, 1);
          return h('button', { class: 'chunk' + (isUsed ? ' used' : ''), disabled: isUsed, onclick: () => { placed.push(c); save(); render(); } }, c);
        }));
      };
      render();
      app.append(h('div', { class: 'panel stack narrow' }, h('p', { class: 'instructions' }, DIRECTIONS.build_sentence),
        h('div', {}, h('div', { class: 'bubble' }, it.prompt)), line, pool,
        h('p', { class: 'muted' }, 'Click a word to place it; click a placed word to remove it.')));
      bar.next('Next', () => done());
    });
  }
}

function writingTask(task) {
  const resp = taskResp(task.id, { text: '' });
  bar.progress(task.type === 'email' ? 'Write an Email' : 'Academic Discussion');
  return show((app, done) => {
    // Live word counter (the real test also shows a word count you can hide)
    const [lo, hi] = CFG.spec.sections.writing.tasks[task.type]?.target_words || [100, 150];
    const num = h('b', { class: 'wc-num' }, '0'), fill = h('div');
    const counter = h('div', { class: 'wc', role: 'status', 'aria-live': 'polite' },
      h('div', { class: 'wc-text' }, h('span', {}, 'Words: ', num), h('span', { class: 'muted' }, ` · target ${lo}–${hi}`)),
      h('div', { class: 'wc-bar' }, fill));
    const toggle = h('button', { class: 'btn wc-toggle', onclick: () => {
      counter.hidden = !counter.hidden; toggle.textContent = counter.hidden ? 'Show word count' : 'Hide word count'; } }, 'Hide word count');
    const ta = h('textarea', { class: 'writing', spellcheck: 'false', autocorrect: 'off', autocapitalize: 'off', autocomplete: 'off',
      'aria-label': 'Your response',
      oninput: e => { resp.text = e.target.value; count(); save(); } });
    ta.value = resp.text;
    const count = () => {
      const n = (resp.text.match(/\S+/g) || []).length;
      num.textContent = n;
      counter.dataset.state = n < lo ? 'under' : n <= hi ? 'in' : 'over';
      fill.style.width = `${Math.min(100, (100 * n) / hi)}%`;
    };
    count();
    let prompt;
    if (task.type === 'email') {
      prompt = h('div', { class: 'panel stack' }, h('p', {}, task.scenario), h('p', {}, h('b', {}, 'In your email, do the following:')),
        h('ul', {}, task.bullets.map(b => h('li', {}, b))), h('p', { class: 'muted' }, 'Write as much as you can and in complete sentences.'));
    } else {
      prompt = h('div', { class: 'panel stack' }, h('p', { class: 'instructions' }, DIRECTIONS.academic_discussion),
        h('div', { class: 'post prof' }, h('b', {}, `${task.professor.name} (${task.course})`), task.professor.post),
        ...task.students.map(s => h('div', { class: 'post' }, h('b', {}, s.name), s.post)));
    }
    const editor = h('div', { class: 'panel editor' },
      task.type === 'email' && h('div', { class: 'email-head' }, h('b', {}, 'To:'), h('span', {}, task.to), h('b', {}, 'Subject:'), h('span', {}, task.subject)),
      h('div', { class: 'wc-row' }, counter, toggle),
      ta, h('div', { class: 'wordcount' }, h('span', {}, 'Spell-check is off, as in the real test')));
    app.append(h('div', { class: 'split' }, prompt, editor));
    bar.next('Next', () => done());
    ta.focus();
  });
}

function recordScreen({ title, sub, key, clipKey, seconds }) {
  return show(async (app, done) => {
    const status = h('p', { class: 'status' }, 'Listen…'), meter = h('div', { class: 'meter' }, h('div'));
    const orb = h('div', { class: 'orb live', 'aria-hidden': 'true' }, '🔊');
    app.append(h('div', { class: 'panel player narrow' }, orb, h('h2', {}, title), sub && h('p', { class: 'muted' }, sub), status, meter));
    await playClip(clipKey);
    orb.className = 'orb rec'; orb.textContent = '🎙️'; meter.classList.add('rec');
    await beep();
    await record(key, seconds, (left, total) => {
      status.replaceChildren(h('span', { class: 'rec-dot' }), `Recording… ${left}s`);
      meter.firstChild.style.width = `${(100 * (total - left + 1)) / total}%`;
    });
    orb.className = 'orb'; orb.textContent = '✓';
    status.textContent = 'Response saved.';
    await sleep(600);
    done();
  });
}

async function speakingTask(task) {
  await ensureMic();
  if (task.type === 'listen_and_repeat') {
    for (const [i, it] of task.items.entries()) {
      bar.progress(`Sentence ${i + 1} of ${task.items.length}`);
      await recordScreen({ title: 'Listen and Repeat', sub: task.setting, key: `${task.id}__${it.id}`, clipKey: `${task.id}__${it.id}`, seconds: it.response_sec });
    }
  } else {
    bar.progress(task.topic);
    await show(async (app, done) => {
      app.append(h('div', { class: 'panel player narrow' }, h('div', { class: 'orb live', 'aria-hidden': 'true' }, '🧑‍💼'),
        h('h2', {}, 'Take an Interview'), h('p', { class: 'muted' }, task.topic), h('p', { class: 'status' }, 'The interviewer is speaking…')));
      await playClip(`${task.id}__intro`);
      done();
    });
    for (const [i, q] of task.questions.entries()) {
      bar.progress(`Question ${i + 1} of ${task.questions.length}`);
      await recordScreen({ title: `Interview: question ${i + 1}`, key: `${task.id}__${q.id}`, clipKey: `${task.id}__${q.id}`, seconds: task.answer_sec });
    }
  }
}

// ------------------------------------------------------------------ module / section / test flow
async function runModule(sec, mkey) {
  const mod = sec.modules[mkey];
  let expired = false;
  const isExpired = () => expired;
  const modTimer = mod.time_sec ? new Timer(Math.round(mod.time_sec), () => { expired = true; expireCurrent(); }).start() : null;
  counter.n = 0;
  counter.total = mod.tasks.reduce((n, t) => n + (t.questions?.length || t.segments?.filter(s => 'gap' in s).length || 0), 0);
  let lastType = null;
  for (const task of mod.tasks) {
    if (expired) break;
    if (task.type !== lastType && ['listening', 'writing', 'speaking'].includes(sec.id)) {
      modTimer?.pause();
      await directionsScreen(task.type.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()), DIRECTIONS[task.type]);
      modTimer?.resume();
    }
    lastType = task.type;
    const t0 = Date.now();
    let taskExpired = false;
    const taskTimer = !modTimer && task.time_sec ? new Timer(task.time_sec, () => { taskExpired = true; expireCurrent(); }).start() : null;
    const exp = () => expired || taskExpired;
    if (sec.id === 'reading') await readingTask(task, exp);
    else if (sec.id === 'listening') await listeningTask(task, modTimer, exp);
    else if (task.type === 'build_sentence') await buildSentenceTask(task, exp);
    else if (sec.id === 'writing') await writingTask(task);
    else await speakingTask(task);
    taskTimer?.stop();
    R.meta.task_seconds[task.id] = Math.round((Date.now() - t0) / 1000);
    tasksDone.n += 1; bar.fill(tasksDone.n / tasksDone.total);
    save();
  }
  modTimer?.stop();
}

const tasksDone = { n: 0, total: 1 };

async function runTest() {
  R.meta.started = new Date().toISOString();
  tasksDone.n = 0;
  tasksDone.total = TEST.sections.reduce((n, s) => n + s.modules.m1.tasks.length + (s.modules.m2_hard?.tasks.length || 0), 0);
  bar.fill(0);
  for (const sec of TEST.sections) {
    const title = CFG.spec.sections[sec.id].title;
    bar.section(''); bar.steps(sec.id); bar.progress('');
    await directionsScreen(title, SECTION_INFO[sec.id]);
    bar.section(sec.modules.m2_easy ? 'Part 1' : '');
    await runModule(sec, 'm1');
    if (sec.modules.m2_easy) {
      await api.post(`/api/attempts/${AID}/responses`, R);
      const { module } = await api.post(`/api/attempts/${AID}/route`, { section: sec.id, responses: R.tasks });
      R.meta.routes[sec.id] = module;
      tasksDone.total += sec.modules[module].tasks.length - sec.modules.m2_hard.tasks.length;
      bar.section('Part 2');
      await runModule(sec, module);
    }
  }
  R.meta.finished = new Date().toISOString();
  bar.section(''); bar.progress(''); bar.steps(null); bar.fill(1);
  clearTimeout(saveTimer);     // the submit carries everything; a late autosave would overwrite the file while grading reads it
  await api.post(`/api/attempts/${AID}/submit`, R);
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  gradingScreen(AID);
}

// ------------------------------------------------------------------ pre-test checks
function checksScreen() {
  const he = CFG.spec.home_edition;
  return show((app, done) => {
    const boxes = HOME_EDITION ? he.checklist.map(c => h('label', {}, h('input', { type: 'checkbox', onchange: upd }), c)) : [];
    const micStatus = h('span', { class: 'muted' }, 'not tested');
    let micOk = false;
    function upd() { bar.enableNext(micOk && boxes.every(b => b.firstChild.checked)); }
    const testMic = async () => {
      try {
        micStatus.textContent = 'Say a sentence… (4s)';
        const blob = await record('mic-check', 4);
        micStatus.textContent = 'Playing back…';
        const a = new Audio(URL.createObjectURL(blob)); a.onended = () => { micStatus.textContent = 'OK, you should have heard yourself.'; };
        await a.play(); micOk = true; upd();
      } catch (e) { micStatus.replaceChildren(h('span', { class: 'error' }, `Microphone unavailable: ${e.message}`)); }
    };
    const firstClip = AUDIO && Object.keys(AUDIO)[0];
    app.append(h('div', { class: 'panel narrow' },
      h('h1', {}, HOME_EDITION ? 'Home Edition check-in' : 'Equipment check'),
      h('p', { class: 'muted' }, TEST.title),
      HOME_EDITION && h('div', { class: 'checklist' }, h('h2', {}, 'Your environment'), boxes, h('p', { class: 'muted' }, he.notes)),
      h('div', { class: 'check-row' },
        h('div', {}, h('b', {}, 'Speakers'), h('div', { class: 'muted' }, AUDIO ? 'Pre-rendered voices' : 'Browser speech (run make audio for real voices)')),
        h('button', { class: 'btn', onclick: () => firstClip ? playClip(firstClip) : speak('This is an audio check.') }, '▶ Play sample')),
      h('div', { class: 'check-row' },
        h('div', {}, h('b', {}, 'Microphone'), h('div', {}, micStatus)),
        h('button', { class: 'btn', onclick: testMic }, '🎙 Test microphone')),
      h('p', { class: 'muted' }, HOME_EDITION
        ? 'The test runs in full screen with no breaks. Leaving full screen is logged. Once you start, the test cannot be paused.'
        : 'Once you start, the test cannot be paused.')));
    bar.next('Start test', async () => {
      if (HOME_EDITION) await document.documentElement.requestFullscreen?.().catch(() => {});
      done();
    }, false);
  });
}

document.addEventListener('fullscreenchange', () => {
  const ov = $('#overlay');
  if (!HOME_EDITION || !AID || R.meta.finished) return;
  if (!document.fullscreenElement) {
    R.meta.fullscreen_exits += 1; save();
    ov.replaceChildren(h('div', { class: 'stack' }, h('h2', {}, 'You left full screen'),
      h('p', {}, 'In the real Home Edition the proctor may end your test. This has been logged.'),
      h('button', { class: 'btn primary', onclick: () => document.documentElement.requestFullscreen() }, 'Return to full screen')));
    ov.hidden = false;
  } else ov.hidden = true;
});

async function startTest(testId, section = null) {
  const data = await api.get(`/api/tests/${testId}`);
  TEST = data.test; AUDIO = data.audio; AID = null;
  if (section) { TEST.sections = TEST.sections.filter(s => s.id === section); TEST.title += ` (${CFG.spec.sections[section].title} only)`; }
  R = { tasks: {}, meta: { routes: {}, fullscreen_exits: 0, task_seconds: {}, home_edition: HOME_EDITION } };
  await checksScreen();
  AID = (await api.post('/api/attempts', { test_id: testId, home_edition: HOME_EDITION, sections: section ? [section] : null })).attempt_id;
  window.onbeforeunload = e => { if (!R.meta.finished) { e.preventDefault(); return ''; } };
  await runTest();
}

// ------------------------------------------------------------------ grading + home
async function gradingScreen(aid) {
  window.onbeforeunload = null;
  const STAGES = [['transcribing', 'Transcribing your speaking'], ['objective', 'Scoring reading, listening & sentences'],
                  ['claude', 'Claude grades writing & speaking (1–3 min)'], ['scoring', 'Calculating bands'], ['report', 'Building your PDF report']]
    .filter(([k]) => {
      const has = id => TEST?.sections.some(s => s.id === id);
      return k === 'transcribing' ? has('speaking') : k === 'claude' ? has('writing') || has('speaking') : true;
    });
  await show(async (app, done) => {
    const status = h('p', { class: 'muted' }, 'Your answers are saved. Grading runs on your computer.'), out = h('div', { class: 'stack' });
    const list = h('ul', { class: 'stages' }, STAGES.map(([k, label]) => h('li', { 'data-k': k }, label)));
    app.append(h('div', { class: 'panel stack narrow' }, h('h1', {}, 'Test complete'), status, list, out,
      h('div', { class: 'btn-row' }, h('button', { class: 'btn', onclick: () => done() }, 'Back to start'))));
    for (;;) {
      if (!current) return;
      const s = await api.get(`/api/attempts/${aid}`).catch(() => ({}));
      const at = s.stage === 'done' ? STAGES.length : STAGES.findIndex(([k]) => k === s.stage);
      list.querySelectorAll('li').forEach((li, i) => { li.className = i < at ? 'done' : i === at ? 'active' : ''; });
      if (s.stage === 'error') { status.replaceChildren(h('span', { class: 'error' }, `Grading failed: ${s.error}. See results/${aid}/pipeline.log, then run: make grade ID=${aid}`)); return; }
      if (s.stage === 'done') {
        list.remove();
        status.textContent = `Saved to results/${aid}/`;
        out.replaceChildren(scoreTiles(s.score), h('div', { class: 'btn-row' },
          s.report_pdf && h('a', { class: 'btn primary', href: `/results/${aid}/report.pdf`, target: '_blank' }, 'Open PDF report'),
          s.report_html && h('a', { class: 'btn', href: `/results/${aid}/report.html`, target: '_blank' }, 'Open HTML report')));
        return;
      }
      await new Promise(r => setTimeout(r, 1500));
    }
  });
  home();
}

function scoreTiles(sum) {
  if (!sum) return h('p', {}, 'No score yet.');
  const tile = (label, band, sub, main) => h('div', { class: 'score-tile' + (main ? ' main' : '') }, h('div', { class: 'muted' }, label),
    h('div', { class: 'big' }, band == null ? '-' : Number(band).toFixed(1)), sub && h('div', { class: 'muted' }, sub));
  return h('div', { class: 'score-grid' },
    tile('Overall band', sum.overall_band, sum.overall_cefr ? `CEFR ${sum.overall_cefr} · ~${sum.est_total_120}/120` : null, true),
    ...Object.entries(sum.sections).map(([k, v]) => tile(k[0].toUpperCase() + k.slice(1), v.band, `~${v.est_30}/30`)));
}

async function home() {
  bar.section(''); bar.progress(''); bar.next(null); bar.steps(null); bar.fill(0); $('#bar-timer').hidden = true;
  const [tests, attempts] = await Promise.all([api.get('/api/tests'), api.get('/api/attempts')]);
  HOME_EDITION = CFG.home_edition;
  await show((app) => {
    const msg = h('p');
    const fileInput = h('input', { type: 'file', accept: '.json,application/json', hidden: true, onchange: async e => {
      const f = e.target.files[0]; if (!f) return;
      try {
        const res = await api.post('/api/tests', JSON.parse(await f.text()));
        msg.replaceChildren(`Imported as "${res.id}". Audio is being generated in the background.`);
        setTimeout(home, 800);
      } catch (err) { msg.replaceChildren(h('span', { class: 'error' }, `Import failed: ${err.message}`), h('pre', {}, (err.details || []).join('\n'))); }
    } });
    const titles = Object.fromEntries(tests.map(t => [t.id, t.title]));
    app.append(h('div', { class: 'home' },
      h('div', { class: 'hero' }, h('div', {}, h('h1', {}, 'Choose a test'),
        h('p', { class: 'muted' }, 'Take a full test or a single section, generate new ones with Claude, or load a test someone shared.'))),
      h('div', { class: 'panel toolbar' },
        h('label', { class: 'switch' }, h('input', { type: 'checkbox', checked: HOME_EDITION, onchange: e => { HOME_EDITION = e.target.checked; } }),
          h('span', {}, h('b', {}, 'Home Edition rules'), h('span', { class: 'muted' }, ' · check-in, full screen, no breaks'))),
        h('button', { class: 'btn', onclick: () => fileInput.click() }, '⤒ Load test from file…'), fileInput),
      generatePanel(),
      msg,
      tests.length ? testBrowser(tests) : h('div', { class: 'panel empty' }, 'No tests yet. Run make test to generate one.'),
      h('h2', {}, 'Past attempts'),
      attempts.length ? h('div', { class: 'panel table-wrap', style: 'padding: 8px 12px' }, h('table', {},
        h('thead', {}, h('tr', {}, h('th', {}, 'Date'), h('th', {}, 'Test'), h('th', {}, 'Overall'), h('th', {}, 'R / L / W / S'), h('th', {}, '~/120'), h('th', {}, 'Report'))),
        h('tbody', {}, attempts.slice(0, 15).map(a => h('tr', {}, h('td', {}, a.date), h('td', {}, titles[a.test_id] || a.test_id), h('td', {}, h('b', {}, a.overall_band ?? '-')),
          h('td', {}, ['reading', 'listening', 'writing', 'speaking'].map(s => a.bands?.[s] ?? '–').join(' / ')),
          h('td', {}, a.est_total_120 ?? '-'),
          h('td', {}, h('a', { href: `/results/${a.attempt_id}/report.pdf`, target: '_blank' }, 'PDF'), ' · ',
            h('a', { href: `/results/${a.attempt_id}/report.html`, target: '_blank' }, 'HTML')))))))
        : h('div', { class: 'panel empty' }, 'No graded attempts yet. Your results will appear here.'),
      attempts.length ? studyPanel() : null));
  });
}

// ------------------------------------------------------------------ study guide (/toefl-study)
let studyPoll;

function studyPanel() {
  const section = h('select', { 'aria-label': 'Sections to analyse' },
    h('option', { value: '' }, 'Writing and speaking'), h('option', { value: 'writing' }, 'Writing only'),
    h('option', { value: 'speaking' }, 'Speaking only'));
  const status = h('div', { class: 'jobs' });
  const links = h('div', { class: 'study-links' });
  const go = h('button', { class: 'btn primary', onclick: async () => {
    go.disabled = true;
    try { await api.post('/api/study', { section: section.value }); }
    catch (e) { alertBox(e); }
    refreshStudy(go, links, status);
  } }, 'Create guide');
  refreshStudy(go, links, status);
  return h('div', { class: 'panel generate' },
    h('div', { class: 'generate-head' }, h('b', {}, 'Study guide'),
      h('span', { class: 'muted' }, 'Claude reads all your past writing and speaking: how your structure changed, a blueprint per task, linking words, key phrases, core errors and a spelling list · ~5–10 min')),
    h('div', { class: 'study-form' }, section, go, links), status);
}

async function refreshStudy(go, links, status) {
  clearTimeout(studyPoll);
  const s = await api.get('/api/study').catch(() => null);
  if (!s) return;
  const fmt = n => `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`;
  const j = s.job, active = j && (j.state === 'queued' || j.state === 'running');
  go.disabled = active;
  go.textContent = s.pdf || s.html ? 'Update guide' : 'Create guide';
  links.replaceChildren(...(s.pdf || s.html ? [
    s.pdf && h('a', { class: 'btn', href: `/results/study/study.pdf?t=${Date.now()}`, target: '_blank' }, 'Open PDF'),
    s.html && h('a', { class: 'btn', href: `/results/study/study.html?t=${Date.now()}`, target: '_blank' }, 'HTML'),
    h('span', { class: 'muted' }, `updated ${s.updated}`)] : [h('span', { class: 'muted' }, 'No study guide yet')]).filter(Boolean));
  status.replaceChildren(...(j ? [h('div', { class: `job ${j.state}` }, h('span', { class: 'job-dot' }),
    h('span', {}, `Study guide · ${j.section === 'all' ? 'writing and speaking' : j.section}`),
    h('span', { class: 'muted' }, j.state === 'queued' ? 'waiting for other Claude jobs' : j.state === 'running' ? `writing… ${fmt(j.elapsed)}`
      : j.state === 'done' ? `ready in ${fmt(j.elapsed)}` : (j.error || 'failed')))] : []));
  if (active && go.isConnected) studyPoll = setTimeout(() => refreshStudy(go, links, status), 3000);
}

// ------------------------------------------------------------------ test list with filters
const FILTER_KEY = 'toefl.testFilters';
const FILTER_DEFAULTS = { q: '', mode: 'all', section: 'all', status: 'any', level: 'any', sort: 'new' };

function loadFilters() {
  try { return { ...FILTER_DEFAULTS, ...JSON.parse(localStorage.getItem(FILTER_KEY) || '{}') }; } catch { return { ...FILTER_DEFAULTS }; }
}
function saveFilters(f) { try { localStorage.setItem(FILTER_KEY, JSON.stringify(f)); } catch { /* private mode: filters just reset */ } }

const shortDate = d => d ? new Date(`${d}T00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : '';
const lastBand = t => t.last && (t.last.overall_band ?? Object.values(t.last.bands || {}).find(b => b != null));

document.addEventListener('click', e => {      // close an open row menu when clicking anywhere else
  document.querySelectorAll('details.more[open]').forEach(d => d.contains(e.target) || d.removeAttribute('open'));
});

function testBrowser(rawTests) {
  // a server started before task_types/last existed still sends the older shape
  const tests = rawTests.map(t => ({ task_types: [], sections: [], ...t }));
  const F = loadFilters();
  const pre = params.get('test');
  const list = h('div', { class: 'test-groups' });
  const count = h('span', { class: 'muted' });
  const clear = h('button', { class: 'btn link', onclick: () => { Object.assign(F, FILTER_DEFAULTS); sync(); } }, 'Clear filters');

  const chips = (key, options) => {
    const el = h('div', { class: 'chips', role: 'group' });
    el.paint = () => el.replaceChildren(...options.map(([v, label]) => h('button', {
      class: 'chip' + (F[key] === v ? ' on' : ''), 'aria-pressed': String(F[key] === v), onclick: () => { F[key] = v; sync(); } }, label)));
    return el;
  };
  const select = (key, label, options) => {
    const el = h('select', { 'aria-label': label, onchange: e => { F[key] = e.target.value; sync(); } },
      options.map(([v, text]) => h('option', { value: v }, text)));
    el.paint = () => { el.value = F[key]; };
    return el;
  };
  const search = h('input', { type: 'search', class: 'search', placeholder: 'Search title, topic or task…', 'aria-label': 'Search tests',
    oninput: e => { F.q = e.target.value; sync(false); } });
  search.paint = () => { if (search.value !== F.q) search.value = F.q; };
  const controls = [
    search,
    chips('mode', [['all', 'All'], ['full', 'Full tests'], ['practice', 'Practice sets']]),
    chips('section', [['all', 'Any section'], ...CFG.spec.order.map(s => [s, CFG.spec.sections[s].title])]),
    select('status', 'Status', [['any', 'Taken or not'], ['new', 'Not taken yet'], ['taken', 'Already taken']]),
    select('level', 'Difficulty', [['any', 'Any difficulty'], ...['easy', 'medium', 'hard', 'mixed'].map(l => [l, l[0].toUpperCase() + l.slice(1)])]),
    select('sort', 'Sort', [['new', 'Newest first'], ['old', 'Oldest first'], ['untaken', 'Not taken first']]),
  ];

  const matches = t => {
    if (t.id === pre) return true;                   // a test opened by link is always shown
    const q = F.q.trim().toLowerCase();
    const hay = [t.title, t.description, t.id, ...t.task_types.map(x => TASK_LABELS[x] || x)].join(' ').toLowerCase();
    return (!q || q.split(/\s+/).every(w => hay.includes(w)))
      && (F.mode === 'all' || t.mode === F.mode)
      && (F.section === 'all' || t.sections.includes(F.section))
      && (F.status === 'any' || (F.status === 'new') === !t.attempts)
      && (F.level === 'any' || t.difficulty === F.level);
  };
  const order = (a, b) => (b.id === pre) - (a.id === pre)
    || (F.sort === 'untaken' && (!!a.attempts - !!b.attempts))
    || (F.sort === 'old' ? 1 : -1) * ((a.created || '') + a.id).localeCompare((b.created || '') + b.id);

  const row = t => {
    const band = lastBand(t);
    const multi = t.sections.length > 1;
    const what = t.mode === 'full' ? t.sections.map(s => CFG.spec.sections[s].title[0]).join(' · ')
      : t.task_types.map(x => TASK_LABELS[x] || x).join(' + ');
    const menu = h('details', { class: 'more' }, h('summary', { class: 'btn', 'aria-label': 'More options' }, '⋯'),
      h('div', { class: 'menu' },
        multi && h('div', { class: 'menu-label' }, 'Take one section'),
        multi && t.sections.map(sid => h('button', { onclick: () => startTest(t.id, sid).catch(alertBox) }, CFG.spec.sections[sid].title)),
        h('a', { href: `/api/tests/${t.id}/download` }, 'Download test file')));
    return h('div', { class: 'trow' + (t.id === pre ? ' highlight' : '') },
      h('div', { class: 'tdate' }, shortDate(t.created)),
      h('div', { class: 'tmain' },
        h('div', { class: 'ttitle' }, t.title.replace(/^(Full test|[A-Za-z ]+ practice( \(\w+\))?):\s*/, '')),
        h('div', { class: 'tmeta' }, what, t.difficulty && ` · ${t.difficulty}`, t.source === 'library' && h('span', { class: 'badge library' }, 'library'),
          !t.audio_ready && h('span', { class: 'badge warn', title: `Run: make audio ID=${t.id}` }, 'no audio'))),
      h('div', { class: 'tstatus' }, t.attempts
        ? h('span', { class: 'pill' }, h('b', {}, band != null ? Number(band).toFixed(1) : '–'), ` · taken ${t.attempts}×`)
        : h('span', { class: 'pill new' }, 'New'),
        t.section_attempts ? h('span', { class: 'muted small' }, `${t.section_attempts} section run${t.section_attempts > 1 ? 's' : ''}`) : null),
      h('div', { class: 'tactions' },
        h('button', { class: 'btn primary', onclick: () => startTest(t.id).catch(alertBox) }, multi ? 'Start full' : 'Start'), menu));
  };

  function sync(paintSearch = true) {
    saveFilters(F);
    controls.forEach(c => (c !== search || paintSearch) && c.paint());
    const shown = tests.filter(matches).sort(order);
    const groups = F.mode !== 'all' ? [[null, shown]]
      : [['Full tests', shown.filter(t => t.mode === 'full')], ['Practice sets', shown.filter(t => t.mode !== 'full')]];
    count.replaceChildren(`${shown.length} of ${tests.length} tests`);
    clear.hidden = JSON.stringify({ ...F }) === JSON.stringify(FILTER_DEFAULTS);
    list.replaceChildren(...(shown.length
      ? groups.filter(([, ts]) => ts.length).map(([name, ts]) => h('section', { class: 'test-group' },
        name && h('h2', {}, name, h('span', { class: 'muted' }, ` ${ts.length}`)),
        h('div', { class: 'panel tlist' }, ts.map(row))))
      : [h('div', { class: 'panel empty' }, 'No tests match these filters. ', h('button', { class: 'btn link', onclick: () => clear.click() }, 'Clear filters'))]));
  }

  const panel = h('div', { class: 'test-browser' },
    h('div', { class: 'panel filters' }, controls[0], h('div', { class: 'filter-row' }, ...controls.slice(1, -1)),
      h('div', { class: 'filter-foot' }, h('div', { class: 'row' }, count, clear), controls.at(-1))),
    list);
  sync();
  return panel;
}

// ------------------------------------------------------------------ generate from the browser
const TASK_LABELS = {
  complete_the_words: 'Complete the Words', daily_life: 'Read in Daily Life', academic_passage: 'Academic Passage',
  choose_response: 'Choose a Response', conversation: 'Conversation', announcement: 'Announcement', academic_talk: 'Academic Talk',
  build_sentence: 'Build a Sentence', email: 'Write an Email', academic_discussion: 'Academic Discussion',
  listen_and_repeat: 'Listen and Repeat', interview: 'Take an Interview',
};
let jobsPoll;

function generatePanel() {
  const what = h('select', { 'aria-label': 'What to generate' },
    h('option', { value: 'full' }, 'Full test (all 4 sections)'),
    CFG.spec.order.map(sid => h('optgroup', { label: CFG.spec.sections[sid].title },
      h('option', { value: sid }, `${CFG.spec.sections[sid].title} (whole section)`),
      Object.keys(CFG.spec.sections[sid].tasks).map(t => h('option', { value: t }, TASK_LABELS[t] || t)))),
    h('option', { value: 'weakest' }, 'My weakest area (from past results)'));
  const level = h('select', { 'aria-label': 'Difficulty' }, ['', 'easy', 'medium', 'hard', 'mixed'].map(l => h('option', { value: l }, l ? l[0].toUpperCase() + l.slice(1) : 'Default difficulty')));
  const count = h('select', { 'aria-label': 'How many' }, [1, 2, 3, 5].map(n => h('option', { value: n }, `${n} test${n > 1 ? 's' : ''}`)));
  const jobs = h('div', { class: 'jobs' });
  const go = h('button', { class: 'btn primary', onclick: async () => {
    go.disabled = true;
    try { await api.post('/api/jobs', { target: what.value, level: level.value, count: Number(count.value) }); await refreshJobs(jobs); }
    catch (e) { alertBox(e); }
    go.disabled = false;
  } }, 'Generate');
  refreshJobs(jobs);
  return h('div', { class: 'panel generate' },
    h('div', { class: 'generate-head' }, h('b', {}, 'Generate new tests with Claude'),
      h('span', { class: 'muted' }, 'Runs Claude Code on your computer · a full test takes ~5–15 min · you can keep practising meanwhile')),
    h('div', { class: 'generate-form' }, what, level, count, go), jobs);
}

async function refreshJobs(el) {
  clearTimeout(jobsPoll);
  const jobs = await api.get('/api/jobs').catch(() => []);
  const fmt = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  const label = j => j.target === 'full' ? 'Full test' : (TASK_LABELS[j.target] || CFG.spec.sections[j.target]?.title || 'Weakest area');
  el.replaceChildren(...jobs.slice(0, 6).map(j => h('div', { class: `job ${j.state}` },
    h('span', { class: 'job-dot' }),
    h('span', {}, `${label(j)} · ${j.level}`),
    h('span', { class: 'muted' }, j.state === 'queued' ? 'waiting in queue' : j.state === 'running' ? `generating… ${fmt(j.elapsed)}`
      : j.state === 'done' ? `ready in ${fmt(j.elapsed)}` : (j.error || 'failed')))));
  const active = jobs.some(j => j.state === 'queued' || j.state === 'running');
  const justDone = jobs.some(j => j.state === 'done' && !seenJobs.has(j.id));
  jobs.filter(j => j.state === 'done').forEach(j => seenJobs.add(j.id));
  if (justDone && el.isConnected && !firstJobsLoad) return home();
  firstJobsLoad = false;
  if (active && el.isConnected) jobsPoll = setTimeout(() => refreshJobs(el), 3000);
}
const seenJobs = new Set();
let firstJobsLoad = true;

function alertBox(err) {
  const ov = $('#overlay');
  ov.replaceChildren(h('div', { class: 'stack' }, h('h2', {}, 'Something went wrong'), h('p', {}, err.message),
    h('button', { class: 'btn primary', onclick: () => { ov.hidden = true; } }, 'Close')));
  ov.hidden = false;
}

(async () => {
  try { CFG = await api.get('/api/config'); speechSynthesis?.getVoices(); await home(); }
  catch (e) { alertBox(e); }
})();
