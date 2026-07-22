import {
  adjustNumericValue,
  chartPoints,
  escapeHtml,
  estimateOneRepMax,
  formatWeight,
  parseApiError,
} from "./helpers.js";


const state = {
  activeWorkout: null,
  workouts: [],
  exercises: [],
  stats: null,
  selectedStationId: null,
  edit: null,
  timer: null,
};

async function api(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: options.body ? {"Content-Type": "application/json", ...(options.headers || {})} : options.headers,
  });
  if (response.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    throw new Error("Authentication required");
  }
  if (!response.ok) throw new Error(await parseApiError(response));
  return response.status === 204 ? null : response.json();
}

function toast(message) {
  const node = document.querySelector("[data-toast]");
  if (!node) return;
  node.textContent = message;
  node.hidden = false;
  window.clearTimeout(toast.timeout);
  toast.timeout = window.setTimeout(() => { node.hidden = true; }, 2400);
}

function prettyDate(value) {
  return new Intl.DateTimeFormat(undefined, {weekday: "short", month: "short", day: "numeric"}).format(new Date(value));
}

function elapsed(value) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function showView(name) {
  document.querySelectorAll("[data-view]").forEach((view) => { view.hidden = view.dataset.view !== name; });
  document.querySelectorAll("[data-nav]").forEach((button) => button.classList.toggle("is-active", button.dataset.nav === name));
  if (name === "workout") renderWorkout();
  if (name === "stats") loadStats().catch(handleError);
}

function workoutSummary(workout) {
  const status = workout.completed_at ? prettyDate(workout.completed_at) : "In progress";
  return `<article class="recent-row"><div><strong>${escapeHtml(workout.name)}</strong><span>${status} · ${workout.exercise_count} exercises · ${workout.total_sets} sets</span></div><div class="metric">${formatWeight(workout.total_volume_kg)} kg</div></article>`;
}

function renderDashboard() {
  const root = document.querySelector("[data-dashboard-content]");
  if (!root) return;
  const active = state.activeWorkout;
  const recent = state.workouts.filter((workout) => workout.completed_at).slice(0, 5);
  root.innerHTML = `<div class="dashboard-grid">
    <section class="card action-card">
      <div><p class="eyebrow">${active ? "Still cooking" : "Next up"}</p><h2>${active ? escapeHtml(active.name) : "Start today's workout"}</h2><p class="muted">${active ? `${active.total_sets} sets logged · ${formatWeight(active.total_volume_kg)} kg moved` : "Your last numbers will be waiting at every station."}</p>
      <button class="primary-button" type="button" data-${active ? "resume" : "start"}-workout data-testid="start-workout">${active ? "Resume workout" : "Start workout"}</button></div>
      <img src="/static/img/repperoni-mascot.png" alt="" />
    </section>
    <section class="card"><p class="eyebrow">Recent workouts</p><h2>Your hot streak</h2>
      <div class="recent-list">${recent.length ? recent.map(workoutSummary).join("") : '<div class="empty-state"><p>Your first workout will show up here. Everybody starts with one slice.</p></div>'}</div>
    </section></div>`;
}

function selectedStation() {
  if (!state.activeWorkout?.stations.length) return null;
  return state.activeWorkout.stations.find((station) => station.id === state.selectedStationId) || state.activeWorkout.stations.at(-1);
}

function setRows(station) {
  if (!station.sets.length) return '<div class="empty-state"><p>No sets yet. Make the first one spicy.</p></div>';
  return station.sets.map((entry) => `<article class="set-row" data-testid="set-row" data-set-id="${entry.id}">
    <span class="set-badge">✓</span><div class="set-copy"><strong>${formatWeight(entry.weight_kg)} kg × ${entry.reps}</strong><small>Set ${entry.set_number} · e1RM ${formatWeight(estimateOneRepMax(entry.weight_kg, entry.reps))} kg</small></div>
    <div class="set-actions"><button type="button" data-edit-set="${entry.id}" data-testid="edit-set" aria-label="Edit set">✎</button><button type="button" data-delete-set="${entry.id}" data-testid="delete-set" aria-label="Delete set">×</button></div>
  </article>`).join("");
}

function renderWorkout() {
  const root = document.querySelector("[data-workout-content]");
  if (!root) return;
  const workout = state.activeWorkout;
  window.clearInterval(state.timer);
  if (!workout) {
    root.innerHTML = `<div class="empty-state card"><img src="/static/img/repperoni-mascot.png" alt="Repperoni lifting a barbell" /><p class="eyebrow">Rack is empty</p><h1>No active workout</h1><p>Start one and we'll remember every plate.</p><button class="primary-button" type="button" data-start-workout data-testid="start-workout">Start workout</button></div>`;
    return;
  }
  const station = selectedStation();
  if (station) state.selectedStationId = station.id;
  const previous = station?.previous_performance;
  root.innerHTML = `<header class="workout-heading"><div><p class="eyebrow">Currently cooking</p><h1>${escapeHtml(workout.name)}</h1><span class="workout-timer" data-workout-timer>${elapsed(workout.started_at)}</span></div><button class="danger-button" type="button" data-finish-workout data-testid="finish-workout">Finish</button></header>
    <div class="station-tabs">${workout.stations.map((item) => `<button type="button" class="station-tab ${item.id === station?.id ? "is-active" : ""}" data-station="${item.id}">${escapeHtml(item.exercise.name)}</button>`).join("")}<button type="button" class="station-tab add" data-add-station>＋ Station</button></div>
    ${station ? `<section class="card station-card"><p class="eyebrow">Station ${station.position}</p><h2>${escapeHtml(station.exercise.name)}</h2>
      <div class="last-performance" data-testid="last-performance"><span>Last time</span><strong>${previous ? `${formatWeight(previous.weight_kg)} kg × ${previous.reps}` : "Fresh station"}</strong></div>
      <form data-log-set><div class="set-entry-grid">
        <div class="number-control"><label for="weight-input">Weight · kg</label><div class="number-row"><button type="button" data-adjust="weight" data-delta="-2.5" aria-label="Decrease weight">−</button><input id="weight-input" name="weight_kg" type="number" min="0" max="2000" step="0.25" value="${previous ? formatWeight(previous.weight_kg) : "20"}" required data-testid="weight-input" /><button type="button" data-adjust="weight" data-delta="2.5" aria-label="Increase weight" data-testid="weight-step">＋</button></div></div>
        <div class="number-control"><label for="reps-input">Reps</label><div class="number-row"><button type="button" data-adjust="reps" data-delta="-1" aria-label="Decrease reps">−</button><input id="reps-input" name="reps" type="number" min="1" max="1000" step="1" value="${previous?.reps || 8}" required data-testid="reps-input" /><button type="button" data-adjust="reps" data-delta="1" aria-label="Increase reps">＋</button></div></div>
      </div><div class="entry-actions"><button class="secondary-button" type="button" data-repeat-last data-testid="repeat-last" ${previous ? "" : "disabled"}>Repeat last</button><button class="primary-button" type="submit" data-testid="log-set">Log set ✓</button></div></form>
      <div class="sets-list"><p class="eyebrow">Today's sets</p>${setRows(station)}</div></section>` : `<div class="empty-state card"><img src="/static/img/repperoni-mascot.png" alt="" /><h2>Choose your first station</h2><p>Your previous weight appears as soon as you pick an exercise.</p><button class="primary-button" type="button" data-add-station>Pick a station</button></div>`}`;
  state.timer = window.setInterval(() => { const timer = document.querySelector("[data-workout-timer]"); if (timer) timer.textContent = elapsed(workout.started_at); }, 1000);
}

function renderExerciseResults(query = "") {
  const root = document.querySelector("[data-exercise-results]");
  if (!root) return;
  const existing = new Set(state.activeWorkout?.stations.map((station) => station.exercise.id) || []);
  const needle = query.trim().toLowerCase();
  const options = state.exercises.filter((exercise) => !existing.has(exercise.id) && exercise.name.toLowerCase().includes(needle));
  root.innerHTML = options.length ? options.map((exercise) => `<button class="exercise-option" type="button" data-add-exercise="${exercise.id}" data-testid="exercise-result-${exercise.id}"><span><strong>${escapeHtml(exercise.name)}</strong><small>${escapeHtml(exercise.muscle_group)} · ${escapeHtml(exercise.equipment)}</small></span><span>＋</span></button>`).join("") : '<p class="muted">No matching station. Try another slice.</p>';
}

function renderStats(progress = null) {
  const root = document.querySelector("[data-stats-content]");
  if (!root || !state.stats) return;
  const values = progress?.points.map((point) => Number(point.best_estimated_one_rep_max)) || state.stats.volume_by_day.map((point) => Number(point.volume_kg));
  const points = chartPoints(values);
  const circles = points.split(" ").filter(Boolean).map((point) => { const [cx, cy] = point.split(","); return `<circle cx="${cx}" cy="${cy}" r="5" />`; }).join("");
  root.innerHTML = `<div class="stats-grid">
    <article class="stat-card"><span>Workouts</span><strong data-testid="stats-workout-count">${state.stats.workout_count}</strong></article>
    <article class="stat-card"><span>Sets</span><strong>${state.stats.total_sets}</strong></article>
    <article class="stat-card"><span>Volume</span><strong>${formatWeight(state.stats.total_volume_kg)} kg</strong></article>
    <article class="stat-card"><span>Streak</span><strong>${state.stats.current_streak} days</strong></article></div>
    <section class="card chart-card"><p class="eyebrow">${progress ? `${escapeHtml(progress.exercise.name)} · estimated 1RM` : "Training volume"}</p><h2>${values.length ? "Up and to the right" : "Your curve starts here"}</h2>
      ${values.length ? `<svg class="progress-chart" viewBox="0 0 600 180" role="img" aria-label="${progress ? "Estimated one rep max progress" : "Training volume over time"}" data-testid="progress-chart"><defs><linearGradient id="chart-fill" x1="0" x2="0" y1="0" y2="1"><stop stop-color="#e1261c" stop-opacity=".32"/><stop offset="1" stop-color="#e1261c" stop-opacity="0"/></linearGradient></defs><path class="grid" d="M12 48H588M12 96H588M12 144H588"/><polygon class="area" points="12,168 ${points} 588,168"/><polyline class="line" points="${points}"/>${circles}</svg>` : '<div class="empty-state"><p>Log a few sets and Repperoni will draw the gains.</p></div>'}</section>
    <section class="card chart-card"><p class="eyebrow">Personal records</p><div class="pr-list">${state.stats.personal_records.length ? state.stats.personal_records.map((record) => `<div class="pr-row"><span><strong>${escapeHtml(record.exercise_name)}</strong><small class="muted">${formatWeight(record.weight_kg)} kg × ${record.reps}</small></span><strong>${formatWeight(record.estimated_one_rep_max)} kg e1RM</strong></div>`).join("") : '<p class="muted">PR pizza is still in the oven.</p>'}</div></section>`;
}

async function reloadWorkout() {
  state.activeWorkout = await api("/workouts/active");
  if (state.selectedStationId && !state.activeWorkout?.stations.some((station) => station.id === state.selectedStationId)) state.selectedStationId = null;
  renderWorkout();
  renderDashboard();
}

async function loadStats() {
  state.stats = await api("/stats/overview?days=90");
  const selector = document.querySelector("[data-progress-exercise]");
  if (selector && !selector.options.length) {
    selector.innerHTML = '<option value="">All volume</option>' + state.exercises.map((exercise) => `<option value="${exercise.id}">${escapeHtml(exercise.name)}</option>`).join("");
  }
  const progress = selector?.value ? await api(`/stats/exercises/${selector.value}/progress?days=365`) : null;
  renderStats(progress);
}

function handleError(error) {
  console.error(error);
  toast(error instanceof Error ? error.message : "Something slipped off the bar.");
}

async function startWorkout(name) {
  state.activeWorkout = await api("/workouts", {method: "POST", body: JSON.stringify({name})});
  state.workouts = await api("/workouts");
  document.querySelector("[data-start-dialog]")?.close();
  showView("workout");
}

function bindEvents() {
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    try {
      if (button.dataset.nav) return showView(button.dataset.nav);
      if (button.hasAttribute("data-start-workout")) return document.querySelector("[data-start-dialog]")?.showModal();
      if (button.hasAttribute("data-resume-workout")) return showView("workout");
      if (button.hasAttribute("data-add-station")) { renderExerciseResults(); return document.querySelector("[data-exercise-dialog]")?.showModal(); }
      if (button.hasAttribute("data-close-exercises")) return document.querySelector("[data-exercise-dialog]")?.close();
      if (button.dataset.station) { state.selectedStationId = button.dataset.station; return renderWorkout(); }
      if (button.dataset.addExercise) {
        state.activeWorkout = await api(`/workouts/${state.activeWorkout.id}/stations`, {method: "POST", body: JSON.stringify({exercise_id: button.dataset.addExercise})});
        state.selectedStationId = state.activeWorkout.stations.at(-1)?.id;
        document.querySelector("[data-exercise-dialog]")?.close();
        return renderWorkout();
      }
      if (button.dataset.adjust) {
        const input = document.querySelector(button.dataset.adjust === "weight" ? "[name=weight_kg]" : "[name=reps]");
        input.value = adjustNumericValue(input.value, button.dataset.delta, Number(input.min), Number(input.max), button.dataset.adjust === "weight" ? 2 : 0);
      }
      if (button.hasAttribute("data-repeat-last")) {
        const previous = selectedStation()?.previous_performance;
        if (previous) { document.querySelector("[name=weight_kg]").value = formatWeight(previous.weight_kg); document.querySelector("[name=reps]").value = previous.reps; }
      }
      if (button.hasAttribute("data-finish-workout") && window.confirm("Finish this workout and bake the stats?")) {
        await api(`/workouts/${state.activeWorkout.id}/finish`, {method: "POST"});
        state.activeWorkout = null;
        state.workouts = await api("/workouts");
        renderDashboard();
        showView("dashboard");
        toast("Workout finished. Absolute unit.");
      }
      if (button.dataset.editSet) {
        const entry = selectedStation().sets.find((item) => item.id === button.dataset.editSet);
        state.edit = entry;
        const form = document.querySelector("[data-edit-form]");
        form.elements.weight_kg.value = formatWeight(entry.weight_kg);
        form.elements.reps.value = entry.reps;
        document.querySelector("[data-edit-dialog]")?.showModal();
      }
      if (button.dataset.deleteSet && window.confirm("Remove this set?")) {
        const station = selectedStation();
        await api(`/workouts/${state.activeWorkout.id}/stations/${station.id}/sets/${button.dataset.deleteSet}`, {method: "DELETE"});
        await reloadWorkout();
      }
    } catch (error) { handleError(error); }
  });

  document.querySelector("[data-start-form]")?.addEventListener("submit", (event) => {
    event.preventDefault();
    startWorkout(new FormData(event.currentTarget).get("name")).catch(handleError);
  });
  document.querySelector("[data-exercise-search]")?.addEventListener("input", (event) => renderExerciseResults(event.target.value));
  document.addEventListener("submit", async (event) => {
    if (!event.target.matches("[data-log-set]")) return;
    event.preventDefault();
    const station = selectedStation();
    const form = new FormData(event.target);
    try {
      await api(`/workouts/${state.activeWorkout.id}/stations/${station.id}/sets`, {method: "POST", body: JSON.stringify({weight_kg: form.get("weight_kg"), reps: Number(form.get("reps")), client_mutation_id: crypto.randomUUID()})});
      await reloadWorkout();
      toast("Set logged. Spicy.");
    } catch (error) { handleError(error); }
  });
  document.querySelector("[data-edit-form]")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const station = selectedStation();
    const form = new FormData(event.currentTarget);
    try {
      await api(`/workouts/${state.activeWorkout.id}/stations/${station.id}/sets/${state.edit.id}`, {method: "PATCH", body: JSON.stringify({weight_kg: form.get("weight_kg"), reps: Number(form.get("reps"))})});
      document.querySelector("[data-edit-dialog]")?.close();
      await reloadWorkout();
    } catch (error) { handleError(error); }
  });
  document.querySelector("[data-progress-exercise]")?.addEventListener("change", () => loadStats().catch(handleError));
}

async function initialize() {
  [state.activeWorkout, state.workouts, state.exercises] = await Promise.all([api("/workouts/active"), api("/workouts"), api("/exercises")]);
  bindEvents();
  renderDashboard();
  if (state.activeWorkout) state.selectedStationId = state.activeWorkout.stations.at(-1)?.id || null;
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js").catch(() => {});
}

if (typeof document !== "undefined" && document.querySelector("[data-app]")) initialize().catch(handleError);

export {adjustNumericValue, chartPoints, escapeHtml, estimateOneRepMax, formatWeight, parseApiError};
