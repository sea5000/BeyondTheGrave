(() => {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);
  const DEFAULT_MODELS = ["qwen/qwen3.5-9b", "google/gemma-4-12b"];

  let SESSION_ID = null;
  let state = null;
  let USER_NAME = "";
  let recorder = null; // active MediaRecorder
  let refBlob = null;
  let selectedModel = DEFAULT_MODELS[0];

  const PASSAGE = "Welcome to Beyond the Grave. This is my voice. I'm recording these words so the people I love can hear me again someday. I'll tell you a little about who I am, and how I speak.";

  async function api(path, opts = {}) {
    const res = await fetch(path, opts);
    let data = {};
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  function show(id) {
    $$(".screen").forEach((s) => s.classList.remove("active"));
    $("#" + id).classList.add("active");
    window.scrollTo(0, 0);
  }

  function esc(s) {
    return (s == null ? "" : String(s)).replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
  }

  /* ---------- audio playback ---------- */
  let currentAudio = null;
  function play(url) {
    if (currentAudio) { currentAudio.pause(); }
    const a = new Audio(url);
    currentAudio = a;
    a.play().catch(() => {});
    return a;
  }

  /* ---------- recording ---------- */
  async function startRecording(ondata) {
    if (recorder) return;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    const chunks = [];
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      stream.getTracks().forEach((t) => t.stop());
      recorder = null;
      ondata(blob);
    };
    recorder.start();
  }

  function stopRecording() { if (recorder) recorder.stop(); }

  function attachRecorder({ recBtn, stopBtn, statusEl, onDone }) {
    recBtn.onclick = async () => {
      try {
        recBtn.style.display = "none";
        stopBtn.style.display = "";
        statusEl.textContent = "Recording…";
        await startRecording(async (blob) => {
          statusEl.textContent = "Processing…";
          await onDone(blob);
        });
      } catch (e) {
        recBtn.style.display = "";
        stopBtn.style.display = "none";
        statusEl.textContent = "Microphone unavailable: " + e.message;
      }
    };
    stopBtn.onclick = () => {
      stopBtn.style.display = "none";
      stopRecording();
    };
  }

  /* ---------- chat rendering ---------- */
  function addMsg(log, cls, text) {
    const d = document.createElement("div");
    d.className = "msg " + cls;
    d.textContent = text;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }

  function addAiMsg(log, text) {
    const d = document.createElement("div");
    d.className = "msg ai";
    d.textContent = text;
    const btn = document.createElement("button");
    btn.className = "speak-btn";
    btn.textContent = "🔊 hear it";
    btn.onclick = () => speak(text);
    d.appendChild(btn);
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }

  async function speak(text) {
    const r = await api(`/api/session/${SESSION_ID}/tts`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    play(r.url);
  }

  /* ---------- coverage chips ---------- */
  const TITLES = {
    identity: "Identity", family: "Family", friends: "Friends", romance: "Love",
    career: "Career", life_events: "Life events", values: "Values",
    favorites: "Favorites", personality: "Character", speech_style: "Speech",
    wisdom: "Wisdom", phrases: "Phrases",
  };
  function renderCoverage(cov) {
    const wrap = $("#coverage-wrap");
    wrap.innerHTML = "";
    for (const [k, v] of Object.entries(cov || {})) {
      const c = document.createElement("div");
      c.className = "chip";
      const pct = Math.round((v || 0) * 100);
      c.title = `${TITLES[k] || k}: ${pct}%`;
      c.innerHTML = `${TITLES[k] || k}<div class="bar"><i style="width:${pct}%"></i></div>`;
      wrap.appendChild(c);
    }
  }

  /* ================= TOPBAR MODEL ================= */
  async function loadModels() {
    let models = [];
    let note = "";
    try {
      const r = await api("/api/models");
      models = r.models || [];
    } catch (e) { note = e.message; }
    if (!models.length) {
      models = DEFAULT_MODELS;
      note = note || "couldn't reach LM Studio — using defaults";
    }
    const sel = $("#topbar-model");
    sel.innerHTML = "";
    for (const m of models) {
      const o = document.createElement("option");
      o.value = m; o.textContent = m;
      sel.appendChild(o);
    }
    sel.value = selectedModel;
    $("#model-note").textContent = note;
  }

  $("#topbar-model").onchange = async () => {
    selectedModel = $("#topbar-model").value;
    if (!SESSION_ID) return;
    try {
      await api(`/api/session/${SESSION_ID}/model`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: selectedModel }),
      });
      if (state) state.model = selectedModel;
    } catch (e) { console.warn("model switch", e); }
  };

  /* ================= HOME ================= */
  function updateNewBtn() {
    $("#btn-new").disabled = !$("#consent").checked;
  }
  $("#consent").onchange = () => {
    localStorage.setItem("btg_consent", $("#consent").checked ? "1" : "");
    updateNewBtn();
  };
  $("#btn-home").onclick = () => showHome();

  async function showHome() {
    $("#consent").checked = !!localStorage.getItem("btg_consent");
    updateNewBtn();
    renderProfileList();
    show("screen-home");
  }

  async function renderProfileList() {
    const wrap = $("#profile-list");
    wrap.innerHTML = "<p class='hint'>Loading…</p>";
    let items = [];
    try {
      const r = await api("/api/profiles");
      items = r.profiles || [];
    } catch (e) {
      wrap.innerHTML = "<p class='hint'>Couldn't load clones: " + esc(e.message) + "</p>";
      return;
    }
    if (!items.length) {
      wrap.innerHTML = "<p class='hint'>No saved clones yet — create your first one.</p>";
      return;
    }
    wrap.innerHTML = "";
    for (const p of items) {
      const el = document.createElement("div");
      el.className = "profile-item";
      el.innerHTML = `
        <div class="profile-main">
          <div class="profile-name">${esc(p.name)} <span class="pill phase-${esc(p.phase)}">${esc(p.phase)}</span></div>
          <div class="profile-meta">${esc(p.model)} · voice ${p.has_voice_ref ? "✓" : "—"} · ${p.phrases_recorded} phrases · ${p.facts} facts</div>
        </div>
        <div class="profile-actions">
          <button class="ghost small act-continue">${p.phase === "ready" ? "Talk to echo" : "Continue"}</button>
          ${p.phase === "ready" ? `<button class="ghost small act-train">Train mode</button>` : ""}
          <button class="ghost small act-delete">Delete</button>
        </div>`;
      el.querySelector(".act-continue").onclick = () => openProfile(p.id);
      const trainBtn = el.querySelector(".act-train");
      if (trainBtn) trainBtn.onclick = () => openProfile(p.id, "train");
      el.querySelector(".act-delete").onclick = async () => {
        if (!confirm(`Delete ${p.name}'s profile? This removes their voice and memory permanently.`)) return;
        try { await api(`/api/session/${p.id}`, { method: "DELETE" }); } catch (e) { alert(e.message); }
        renderProfileList();
      };
      wrap.appendChild(el);
    }
  }

  $("#btn-new").onclick = () => {
    SESSION_ID = null; state = null; USER_NAME = ""; refBlob = null;
    $("#name").value = "";
    $("#ref-status").textContent = ""; $("#ref-status").classList.remove("ok");
    $("#rec-ref").style.display = ""; $("#rec-ref-stop").style.display = "none";
    $("#rec-ref-play").style.display = "none";
    $("#voice-done").style.display = "none";
    $("#btn-start-interview").disabled = true;
    show("screen-setup");
    $("#name").focus();
  };

  /* ================= OPEN / RESUME PROFILE ================= */
  async function openProfile(sid, mode) {
    try {
      const s = await api(`/api/session/${sid}/state`);
      SESSION_ID = sid; state = s; USER_NAME = s.name;
      selectedModel = s.model || selectedModel;
      $("#topbar-model").value = selectedModel;
      if (mode === "train") { enterClone(true); return; }
      switch (s.phase) {
        case "setup":
          $("#name").value = s.name;
          $("#voice-done").style.display = s.has_voice_ref ? "" : "none";
          $("#btn-start-interview").disabled = !s.has_voice_ref;
          show("screen-setup");
          break;
        case "interview":
          renderInterview(s);
          break;
        case "phrases":
          renderPhrases(s.phrase_prompts || [], s.phrases || []);
          show("screen-phrases");
          break;
        case "ready":
          enterClone(false);
          break;
        default:
          show("screen-setup");
      }
    } catch (e) { alert("Could not open profile: " + e.message); }
  }

  /* ================= SETUP ================= */
  attachRecorder({
    recBtn: $("#rec-ref"), stopBtn: $("#rec-ref-stop"),
    statusEl: $("#ref-status"),
    onDone: async (blob) => {
      refBlob = blob;
      $("#rec-ref-play").style.display = "";
      $("#ref-status").textContent = "✓ recorded — you can begin";
      $("#ref-status").classList.add("ok");
      $("#btn-start-interview").disabled = !$("#name").value.trim();
    },
  });
  $("#rec-ref-play").onclick = () => {
    $("#ref-audio").src = URL.createObjectURL(refBlob);
    $("#ref-audio").play();
  };
  $("#name").oninput = () => {
    $("#btn-start-interview").disabled = !($("#name").value.trim() && refBlob);
  };

  $("#btn-start-interview").onclick = async () => {
    const name = $("#name").value.trim();
    const btn = $("#btn-start-interview");
    btn.disabled = true; btn.textContent = "Creating session…";
    try {
      const s = await api("/api/session", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, model: selectedModel }),
      });
      SESSION_ID = s.session_id;
      if (refBlob) {
        const fd = new FormData();
        fd.append("file", refBlob, "ref.webm");
        fd.append("text", PASSAGE);
        await api(`/api/session/${SESSION_ID}/voice/reference`, { method: "POST", body: fd });
      }
      await startInterview();
    } catch (e) {
      btn.disabled = false; btn.textContent = "Start the interview";
      alert("Setup failed: " + e.message);
    }
  };

  async function startInterview() {
    $("#interview-hint").textContent = "Opening the interview…";
    const r = await api(`/api/session/${SESSION_ID}/interview/start`, { method: "POST" });
    state = { phase: r.phase, coverage: r.coverage };
    const log = $("#chat-log");
    log.innerHTML = "";
    addAiMsg(log, r.reply);
    renderCoverage(r.coverage);
    $("#btn-finish").style.display = "";
    show("screen-interview");
    $("#interview-hint").textContent = "Take your time. The more specific you are, the more real your echo will be.";
    $("#answer").focus();
  }

  function renderInterview(s) {
    const log = $("#chat-log");
    log.innerHTML = "";
    for (const t of (s.transcript || [])) {
      if (t.role === "assistant") addAiMsg(log, t.content);
      else addMsg(log, "me", t.content);
    }
    renderCoverage(s.coverage);
    $("#btn-finish").style.display = "";
    show("screen-interview");
    $("#answer").focus();
  }

  /* ================= INTERVIEW ================= */
  async function sendAnswer() {
    const inp = $("#answer");
    const text = inp.value.trim();
    if (!text) return;
    const log = $("#chat-log");
    inp.value = "";
    addMsg(log, "me", text);
    const thinking = addMsg(log, "ai thinking", "");
    const btn = $("#btn-send"); btn.disabled = true;
    try {
      const r = await api(`/api/session/${SESSION_ID}/interview`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      thinking.remove();
      addAiMsg(log, r.reply);
      renderCoverage(r.coverage);
      if (r.phase !== "interview") {
        $("#btn-finish").click();
      }
    } catch (e) {
      thinking.remove();
      addMsg(log, "ai", "⚠ " + e.message);
    }
    btn.disabled = false;
    inp.focus();
  }
  $("#btn-send").onclick = sendAnswer;
  $("#answer").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAnswer(); }
  });

  $("#btn-finish").onclick = async () => {
    const r = await api(`/api/session/${SESSION_ID}/finish`, { method: "POST" });
    renderPhrases(r.phrase_prompts, state && state.phrases ? state.phrases : []);
    show("screen-phrases");
  };

  /* ================= PHRASES ================= */
  function renderPhrases(prompts, recorded) {
    const list = $("#phrase-list");
    list.innerHTML = "";
    const byId = {};
    (recorded || []).forEach((ph) => { if (ph.recorded && ph.id) byId[ph.id] = ph; });
    prompts.forEach((p, i) => {
      const item = document.createElement("div");
      item.className = "phrase-item";
      item.id = "phrase-" + p.id;
      item.innerHTML = `
        <span class="num">${i + 1}.</span>
        ${p.text ? `<span class="text">“${esc(p.text)}”</span>` : `<span class="text" style="font-style:italic">Your own message</span>`}
        <span class="hint">${esc(p.hint)}</span>
        <div class="recorder">
          <button class="rec ph-rec">● Record</button>
          <button class="danger ph-stop" style="display:none">■ Stop</button>
          <audio style="display:none"></audio>
          <span class="status ph-status"></span>
        </div>`;
      const recBtn = item.querySelector(".ph-rec");
      const stopBtn = item.querySelector(".ph-stop");
      const statusEl = item.querySelector(".ph-status");
      const audioEl = item.querySelector("audio");
      const saved = byId[p.id];
      if (saved) {
        item.classList.add("done");
        recBtn.style.display = "none";
        statusEl.textContent = "✓ saved";
        statusEl.classList.add("ok");
        audioEl.src = saved.url;
        const playBtn = document.createElement("button");
        playBtn.className = "ghost small";
        playBtn.textContent = "Play";
        playBtn.onclick = () => play(saved.url);
        item.querySelector(".recorder").appendChild(playBtn);
      } else {
        attachRecorder({
          recBtn, stopBtn, statusEl,
          onDone: async (blob) => {
            const fd = new FormData();
            fd.append("file", blob, "phrase.webm");
            fd.append("prompt_id", p.id);
            fd.append("text", p.text || "");
            fd.append("hint", p.hint);
            fd.append("source", p.kind);
            try {
              const r = await api(`/api/session/${SESSION_ID}/voice/phrase`, { method: "POST", body: fd });
              statusEl.textContent = "✓ saved";
              statusEl.classList.add("ok");
              audioEl.src = r.url;
              item.classList.add("done");
              const playBtn = document.createElement("button");
              playBtn.className = "ghost small";
              playBtn.textContent = "Play";
              playBtn.onclick = () => play(r.url);
              item.querySelector(".recorder").appendChild(playBtn);
              recBtn.style.display = "none";
            } catch (e) { statusEl.textContent = "✗ " + e.message; }
          },
        });
      }
      list.appendChild(item);
    });
  }

  // custom phrase
  attachRecorder({
    recBtn: $("#rec-custom"), stopBtn: $("#rec-custom-stop"),
    statusEl: $("#custom-status"),
    onDone: async (blob) => {
      const text = $("#custom-phrase-text").value.trim();
      const fd = new FormData();
      fd.append("file", blob, "phrase.webm");
      fd.append("text", text);
      fd.append("hint", "A message of your own");
      fd.append("source", "custom");
      try {
        const r = await api(`/api/session/${SESSION_ID}/voice/phrase`, { method: "POST", body: fd });
        $("#custom-status").textContent = "✓ saved — “" + (text || "your own words") + "”";
        $("#custom-status").classList.add("ok");
        play(r.url);
      } catch (e) { $("#custom-status").textContent = "✗ " + e.message; }
    },
  });

  $("#btn-build").onclick = async () => {
    $("#dossier-status").textContent = "Synthesizing your dossier from everything you shared…";
    show("screen-dossier");
    $("#dossier-title").textContent = "Building your echo…";
    $("#dossier-body").style.display = "none";
    $("#btn-meet").style.display = "none";
    try {
      const r = await api(`/api/session/${SESSION_ID}/dossier`, { method: "POST" });
      renderDossier(r.dossier);
    } catch (e) {
      $("#dossier-status").textContent = "✗ " + e.message;
    }
  };

  function renderDossier(md) {
    $("#dossier-title").textContent = "Your echo is ready";
    $("#dossier-status").textContent = "Everything below is what your echo remembers and speaks from.";
    $("#dossier-body").style.display = "";
    $("#dossier-body").innerHTML = "";
    md.split(/\n{2,}/).forEach((blk) => {
      const p = document.createElement("p");
      if (blk.trim().startsWith("# ")) { const h = document.createElement("h1"); h.textContent = blk.replace(/^#\s*/, ""); $("#dossier-body").appendChild(h); return; }
      if (blk.trim().startsWith("## ")) { const h = document.createElement("h2"); h.textContent = blk.replace(/^##\s*/, ""); $("#dossier-body").appendChild(h); return; }
      if (blk.trim().startsWith("### ")) { const h = document.createElement("h3"); h.textContent = blk.replace(/^###\s*/, ""); $("#dossier-body").appendChild(h); return; }
      const lines = blk.split("\n").filter((l) => l.trim());
      if (lines.every((l) => l.trim().startsWith("- "))) {
        const ul = document.createElement("ul");
        lines.forEach((l) => { const li = document.createElement("li"); li.textContent = l.trim().replace(/^-\s*/, ""); ul.appendChild(li); });
        $("#dossier-body").appendChild(ul);
      } else {
        p.textContent = blk.trim();
        $("#dossier-body").appendChild(p);
      }
    });
    $("#btn-meet").style.display = "";
  }

  $("#btn-meet").onclick = () => enterClone(false);

  /* ================= CLONE ================= */
  function enterClone(train) {
    const log = $("#clone-log");
    log.innerHTML = "";
    $("#clone-name").textContent = "“" + (USER_NAME || "you") + "” — your echo";
    $("#train-mode").checked = !!train;
    $("#train-note").textContent = train
      ? "Training mode: tell me things to remember about you — it updates the memory file."
      : "";
    if (!train) {
      addAiMsg(log, "Hi. It's me — or as close to me as this little echo can manage. Ask me anything, or just say hi. I'll answer in my own words, and my own voice.");
    }
    show("screen-clone");
    $("#clone-msg").focus();
  }

  $("#train-mode").onchange = () => {
    const on = $("#train-mode").checked;
    $("#train-note").textContent = on
      ? "Training mode: tell me things to remember about you — it updates the memory file."
      : "";
  };

  async function cloneSend() {
    const inp = $("#clone-msg");
    const text = inp.value.trim();
    if (!text) return;
    inp.value = "";
    const log = $("#clone-log");
    addMsg(log, "me", text);
    const thinking = addMsg(log, "ai thinking", "");
    const btn = $("#btn-clone-send"); btn.disabled = true;
    const trainMode = $("#train-mode").checked;
    try {
      if (trainMode) {
        const r = await api(`/api/session/${SESSION_ID}/train`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        });
        thinking.remove();
        addAiMsg(log, r.reply);
        if (state) { state.coverage = r.coverage; }
      } else {
        const r = await api(`/api/session/${SESSION_ID}/clone/chat`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        });
        thinking.remove();
        addAiMsg(log, r.reply);
        if ($("#autospeak").checked) {
          try { await speak(r.reply); } catch (e) { console.warn("tts", e); }
        }
      }
    } catch (e) {
      thinking.remove();
      addMsg(log, "ai", "⚠ " + e.message);
    }
    btn.disabled = false;
    inp.focus();
  }
  $("#btn-clone-send").onclick = cloneSend;
  $("#clone-msg").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); cloneSend(); }
  });

  /* ================= BOOT ================= */
  loadModels();
  showHome();
})();
