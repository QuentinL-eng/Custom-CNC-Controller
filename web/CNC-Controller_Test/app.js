(() => {
  "use strict";

  const state = {
    screen: "home",
    history: ["home"],
    laserPage: "setup",
    file: null,
    material: "Unspecified",
    speed: 1200,
    power: 85,
    passes: 1,
    safetyReviewed: false,
    running: false,
    paused: false,
    progress: 0,
    elapsed: 0,
    timer: null,
    keyboardTarget: null,
    encoderAngle: 0,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function fitDisplay() {
    const windowElement = $("#displayWindow");
    const hmi = $("#hmi");
    const scale = windowElement.clientWidth / 1024;
    hmi.style.transform = `scale(${scale})`;
  }

  function updateClock() {
    $("#clock").textContent = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
  }

  function setMachineState(label, color = "var(--green)") {
    $("#machineState").textContent = label;
    $("#stateDot").style.background = color;
  }

  function navigate(screen, push = true) {
    if (screen === state.screen) return;
    $$("[data-screen]").forEach(item => item.classList.toggle("active", item.dataset.screen === screen));
    state.screen = screen;
    if (push) state.history.push(screen);
    $("#encoderAction").textContent = screen === "laser" ? "SELECT" : "NAVIGATE";
  }

  function navigateBack() {
    if (state.history.length > 1) state.history.pop();
    navigate(state.history[state.history.length - 1] || "home", false);
  }

  function showLaserPage(page) {
    state.laserPage = page;
    $$("[data-laser-page]").forEach(item => item.classList.toggle("active", item.dataset.laserPage === page));
    $$("[data-laser]").forEach(item => item.classList.toggle("active", item.dataset.laser === page));
    $("#encoderAction").textContent = page === "preview" ? "ZOOM" : page === "run" ? "NAVIGATE" : "SELECT";
  }

  function setFile(file) {
    if (!file) return;
    state.file = file;
    ["loadedJob", "laserFile", "setupFilename"].forEach(id => $("#" + id).textContent = file.name);
    $("#operationSummary").textContent = "2 operations · origin Front-left";
    state.safetyReviewed = false;
    updateSafety();
    showLaserPage("layers");
  }

  function applyPreset(button) {
    state.material = button.dataset.material;
    state.speed = Number(button.dataset.speed);
    state.power = Number(button.dataset.power);
    state.passes = Number(button.dataset.passes);
    $("#materialName").textContent = state.material;
    $("#layerSpeed").textContent = state.speed;
    $("#layerPower").textContent = state.power + "%";
    $("#layerPasses").textContent = state.passes;
    $("#previewMaterial").textContent = state.material;
    $("#previewSpeed").textContent = state.speed + " mm/min";
    $("#previewPower").textContent = state.power + "%";
    $("#previewPasses").textContent = state.passes;
    state.safetyReviewed = false;
    updateSafety();
  }

  function updateSafety() {
    const badge = $("#safetyBadge");
    badge.textContent = state.safetyReviewed ? "REVIEWED" : "NOT REVIEWED";
    badge.classList.toggle("reviewed", state.safetyReviewed);
  }

  function reviewSafety() {
    state.safetyReviewed = true;
    updateSafety();
    showLaserPage("run");
  }

  function renderProgress() {
    const total = 2980;
    const current = Math.round(total * state.progress / 100);
    $("#runProgress").style.width = state.progress + "%";
    $("#lineProgress").textContent = `Line ${current} / ${total}`;
    $("#elapsed").textContent = `Elapsed ${formatTime(state.elapsed)}`;
    const remaining = state.progress ? Math.round(state.elapsed * (100 - state.progress) / state.progress) : 0;
    $("#remaining").textContent = state.progress ? `Remaining ${formatTime(remaining)}` : "Remaining —";
  }

  function formatTime(seconds) {
    return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function startJob() {
    if (!state.safetyReviewed) {
      reviewSafety();
      return;
    }
    clearInterval(state.timer);
    state.running = true;
    state.paused = false;
    if (state.progress >= 100) { state.progress = 0; state.elapsed = 0; }
    $("#runState").textContent = "RUNNING";
    $("#runState").style.color = "var(--blue)";
    setMachineState("Run", "var(--blue)");
    state.timer = setInterval(() => {
      if (!state.running || state.paused) return;
      state.elapsed += 1;
      state.progress = Math.min(100, state.progress + 0.8);
      renderProgress();
      if (state.progress >= 100) completeJob();
    }, 500);
  }

  function pauseJob() {
    if (!state.running) return;
    state.paused = true;
    $("#runState").textContent = "PAUSED";
    $("#runState").style.color = "var(--amber)";
    setMachineState("Hold", "var(--amber)");
  }

  function resumeJob() {
    if (!state.running) return;
    state.paused = false;
    $("#runState").textContent = "RUNNING";
    $("#runState").style.color = "var(--blue)";
    setMachineState("Run", "var(--blue)");
  }

  function stopJob() {
    clearInterval(state.timer);
    state.running = false;
    state.paused = false;
    state.progress = 0;
    state.elapsed = 0;
    $("#runState").textContent = "IDLE";
    $("#runState").style.color = "var(--green)";
    setMachineState("Idle");
    renderProgress();
  }

  function completeJob() {
    clearInterval(state.timer);
    state.running = false;
    $("#runState").textContent = "COMPLETE";
    $("#runState").style.color = "var(--green)";
    setMachineState("Complete");
    renderProgress();
  }

  function showSetting(panel) {
    $$("[data-setting]").forEach(item => item.classList.toggle("active", item.dataset.setting === panel));
    $$("[data-panel]").forEach(item => item.classList.toggle("active", item.dataset.panel === panel));
  }

  const keyboardRows = [
    "1234567890".split(""),
    "qwertyuiop".split(""),
    "asdfghjkl".split(""),
    "zxcvbnm".split(""),
  ];

  function buildKeyboard() {
    const host = $("#keyboardKeys");
    keyboardRows.forEach((keys, rowIndex) => {
      const row = document.createElement("div");
      row.className = "key-row";
      keys.forEach(key => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = key;
        button.addEventListener("click", () => insertKey(key));
        row.append(button);
      });
      if (rowIndex === 3) {
        const backspace = document.createElement("button");
        backspace.textContent = "⌫";
        backspace.addEventListener("click", () => {
          if (state.keyboardTarget) state.keyboardTarget.value = state.keyboardTarget.value.slice(0, -1);
        });
        row.append(backspace);
      }
      host.append(row);
    });
    const actions = document.createElement("div");
    actions.className = "key-row";
    const symbols = document.createElement("button");
    symbols.textContent = "?123";
    const space = document.createElement("button");
    space.textContent = "Space";
    space.className = "space";
    space.addEventListener("click", () => insertKey(" "));
    const dot = document.createElement("button");
    dot.textContent = ".";
    dot.addEventListener("click", () => insertKey("."));
    const done = document.createElement("button");
    done.textContent = "Done";
    done.addEventListener("click", hideKeyboard);
    actions.append(symbols, space, dot, done);
    host.append(actions);
  }

  function insertKey(key) {
    if (state.keyboardTarget) state.keyboardTarget.value += key;
  }

  function showKeyboard(input) {
    state.keyboardTarget = input;
    $("#keyboardTitle").textContent = input.placeholder || "Keyboard";
    $("#touchKeyboard").classList.add("open");
    $("#touchKeyboard").setAttribute("aria-hidden", "false");
  }

  function hideKeyboard() {
    $("#touchKeyboard").classList.remove("open");
    $("#touchKeyboard").setAttribute("aria-hidden", "true");
    state.keyboardTarget = null;
  }

  function sendConsole() {
    const input = $("#consoleCommand");
    const command = input.value.trim();
    if (!command) return;
    $("#consoleOutput").textContent += `\n> ${command}\nok`;
    input.value = "";
    $("#consoleOutput").scrollTop = $("#consoleOutput").scrollHeight;
  }

  function bindEvents() {
    $$("[data-nav]").forEach(button => button.addEventListener("click", () => navigate(button.dataset.nav)));
    $("[data-rail='home']").addEventListener("click", () => navigate("home"));
    $("[data-rail='back']").addEventListener("click", navigateBack);
    $$("[data-laser-page]").forEach(button => button.addEventListener("click", () => showLaserPage(button.dataset.laserPage)));
    $("#fileInput").addEventListener("change", event => setFile(event.target.files[0]));
    $$(".preset").forEach(button => button.addEventListener("click", () => applyPreset(button)));
    $$(".origin").forEach(button => button.addEventListener("click", () => {
      $$(".origin").forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      $("#originName").textContent = button.textContent;
    }));
    $("#generateButton").addEventListener("click", event => {
      event.currentTarget.textContent = "Generating…";
      setTimeout(() => event.currentTarget.textContent = "G-code Ready", 850);
    });
    $("#reviewButton").addEventListener("click", reviewSafety);
    $("#startJob").addEventListener("click", startJob);
    $("#pauseJob").addEventListener("click", pauseJob);
    $("#resumeJob").addEventListener("click", resumeJob);
    $("#stopJob").addEventListener("click", stopJob);
    $("#clearConsole").addEventListener("click", () => $("#consoleOutput").textContent = "");
    $("#sendConsole").addEventListener("click", sendConsole);
    $("#consoleCommand").addEventListener("keydown", event => { if (event.key === "Enter") sendConsole(); });
    $$("[data-setting]").forEach(button => button.addEventListener("click", () => showSetting(button.dataset.setting)));
    $$(".segmented button").forEach(button => button.addEventListener("click", () => {
      $$(".segmented button").forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      document.body.classList.toggle("motion-off", button.textContent === "Off");
    }));
    $$(".keyboard-input").forEach(input => input.addEventListener("focus", () => showKeyboard(input)));
    $("#hideKeyboard").addEventListener("click", hideKeyboard);
    $$(".hardware-button").forEach(button => {
      button.addEventListener("pointerdown", () => button.classList.add("pressed"));
      ["pointerup", "pointercancel", "pointerleave"].forEach(name => button.addEventListener(name, () => button.classList.remove("pressed")));
    });
    const knob = $("#encoderKnob");
    knob.addEventListener("wheel", event => {
      event.preventDefault();
      state.encoderAngle += event.deltaY > 0 ? 15 : -15;
      knob.style.rotate = state.encoderAngle + "deg";
    }, {passive:false});
    knob.addEventListener("click", () => {
      state.encoderAngle += 30;
      knob.style.rotate = state.encoderAngle + "deg";
    });
    window.addEventListener("resize", fitDisplay);
  }

  buildKeyboard();
  bindEvents();
  fitDisplay();
  updateClock();
  renderProgress();
  setInterval(updateClock, 10000);
  $("#buildLabel").textContent = "web emulator";
})();
