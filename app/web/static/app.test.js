import test from "node:test";
import assert from "node:assert/strict";
import {adjustNumericValue, chartPoints, chartScale, dayLabel, escapeHtml, estimateOneRepMax, formatWeight, parseApiError} from "./helpers.js";

test("formats gym weights without noisy zeros", () => {
  assert.equal(formatWeight(80), "80");
  assert.equal(formatWeight("82.50"), "82.5");
  assert.equal(formatWeight(82.25), "82.25");
  assert.equal(formatWeight(), "0");
});

test("estimates one-rep max with the Epley formula", () => {
  assert.equal(estimateOneRepMax(100, 6), 120);
  assert.equal(estimateOneRepMax(0, 10), 0);
});

test("adjusts and clamps numeric inputs", () => {
  assert.equal(adjustNumericValue("20", 2.5, 0, 100, 2), 22.5);
  assert.equal(adjustNumericValue(1, -5, 1, 20), 1);
  assert.equal(adjustNumericValue(19, 5, 1, 20), 20);
  assert.equal(adjustNumericValue(undefined, 2), 2);
});

test("builds chart scales and points", () => {
  const y = chartScale([0, 10], 100, 10);
  assert.equal(y(0), 90);
  assert.equal(y(10), 10);
  assert.equal(chartPoints([], 100, 100), "");
  assert.equal(chartPoints([5], 100, 100, 10), "50,10");
  assert.equal(chartPoints([0, 10], 100, 100, 10), "10,90 90,10");
  assert.match(chartPoints([0, 10]), /^12,/);
});

test("pluralizes streak days", () => {
  assert.equal(dayLabel(1), "1 day");
  assert.equal(dayLabel(2), "2 days");
});

test("escapes untrusted exercise names", () => {
  assert.equal(escapeHtml('<Bench & "Press">'), "&lt;Bench &amp; &quot;Press&quot;&gt;");
  assert.equal(escapeHtml(null), "");
});

test("parses FastAPI error shapes", async () => {
  assert.equal(await parseApiError(new Response(JSON.stringify({detail: "Nope"}), {status: 400})), "Nope");
  assert.equal(await parseApiError(new Response(JSON.stringify({detail: [{msg: "Too heavy"}]}), {status: 422})), "Too heavy");
  assert.equal(await parseApiError(new Response(JSON.stringify({detail: [{}]}), {status: 422})), "Invalid value");
  assert.equal(await parseApiError(new Response("not json", {status: 500})), "Request failed (500)");
});
