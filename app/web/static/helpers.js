function formatWeight(value) {
  const number = Number(value || 0);
  return Number.isInteger(number)
    ? String(number)
    : number.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

function estimateOneRepMax(weight, reps) {
  return Math.round((Number(weight) * (1 + Number(reps) / 30)) * 100) / 100;
}

function adjustNumericValue(
  value,
  delta,
  min = 0,
  max = Number.MAX_SAFE_INTEGER,
  precision = 0,
) {
  const factor = 10 ** precision;
  return Math.min(
    max,
    Math.max(min, Math.round((Number(value || 0) + Number(delta)) * factor) / factor),
  );
}

function chartScale(values, height = 160, padding = 12) {
  const numeric = values.map(Number);
  const max = Math.max(...numeric, 1);
  const min = Math.min(...numeric, 0);
  const range = Math.max(max - min, 1);
  return (value) =>
    height - padding - ((Number(value) - min) / range) * (height - padding * 2);
}

function chartPoints(values, width = 600, height = 160, padding = 12) {
  if (!values.length) return "";
  const y = chartScale(values, height, padding);
  const step = values.length === 1 ? 0 : (width - padding * 2) / (values.length - 1);
  return values
    .map((value, index) => `${padding + index * step},${y(value)}`)
    .join(" ");
}

function escapeHtml(value) {
  const entities = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  };
  return String(value ?? "").replace(/[&<>'"]/g, (character) => entities[character]);
}

async function parseApiError(response) {
  const body = await response.json().catch(() => ({}));
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    return body.detail.map((item) => item.msg || "Invalid value").join(", ");
  }
  return `Request failed (${response.status})`;
}

export {
  adjustNumericValue,
  chartPoints,
  chartScale,
  escapeHtml,
  estimateOneRepMax,
  formatWeight,
  parseApiError,
};
