import {execFileSync} from "node:child_process";
import {mkdir, writeFile} from "node:fs/promises";
import {pathToFileURL} from "node:url";
import path from "node:path";
import process from "node:process";
import {chromium} from "playwright";


function argument(name, fallback) {
  const prefix = `--${name}=`;
  return process.argv.find((value) => value.startsWith(prefix))?.slice(prefix.length) || fallback;
}

const baseUrl = argument("base-url", "http://localhost:8000").replace(/\/$/, "");
const requestedDevice = argument("device", "all");
const devices = requestedDevice === "all" ? ["desktop", "mobile"] : [requestedDevice];
const resultsDirectory = path.resolve("test-results");


function fastPasskeyHelper() {
  const python = path.resolve(".venv/bin/python");
  return execFileSync(
    python,
    ["-c", "from importlib.resources import files; print(files('fastpasskey').joinpath('testing/playwright.mjs'))"],
    {encoding: "utf8"},
  ).trim();
}


async function expectText(page, selector, text) {
  const locator = page.locator(selector);
  await locator.waitFor({state: "visible"});
  const content = await locator.textContent();
  if (!String(content).includes(text)) throw new Error(`Expected ${selector} to contain ${text}; got ${content}`);
}


async function finishWorkout(page) {
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByTestId("finish-workout").click();
  await page.locator('[data-view="dashboard"]:not([hidden])').waitFor({state: "visible"});
}


async function runJourney(browser, createVirtualAuthenticator, device) {
  const mobile = device === "mobile";
  const context = await browser.newContext({
    viewport: mobile ? {width: 390, height: 844} : {width: 1365, height: 900},
    isMobile: mobile,
    hasTouch: mobile,
    deviceScaleFactor: mobile ? 2 : 1,
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  const authenticator = await createVirtualAuthenticator(context, page);
  const suffix = `${device}-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  try {
    await page.goto(`${baseUrl}/login`, {waitUntil: "networkidle"});
    await page.getByTestId("signup-tab").click();
    await page.getByTestId("signup-name").fill(mobile ? "Mobile Mozzarella" : "Desktop Dough");
    await page.getByTestId("signup-email").fill(`e2e-${suffix}@example.com`);
    await page.getByTestId("signup-submit").click();
    await page.waitForURL(`${baseUrl}/`);
    await expectText(page, "h1", "shredded");

    await page.getByRole("button", {name: "Sign out"}).click();
    await page.waitForURL(/\/login/);
    await page.getByTestId("passkey-login").click();
    await page.waitForURL(`${baseUrl}/`);

    await page.getByTestId("start-workout").click();
    await page.getByTestId("workout-name").fill("Pepper Push");
    await page.getByTestId("create-workout").click();
    await expectText(page, "h1", "Pepper Push");
    await page.getByRole("button", {name: /Station/}).click();
    await page.getByTestId("exercise-search").fill("Bench Press");
    await page.locator("[data-add-exercise]").first().click();
    await expectText(page, '[data-testid="last-performance"]', "Fresh station");
    await page.getByTestId("weight-input").fill("60");
    await page.getByTestId("reps-input").fill("8");
    await page.getByTestId("log-set").click();
    await expectText(page, '[data-testid="set-row"]', "60 kg × 8");

    await page.getByTestId("edit-set").click();
    await page.locator("[data-edit-form] [name=weight_kg]").fill("62.5");
    await page.locator("[data-edit-form] [name=reps]").fill("9");
    await page.getByRole("button", {name: "Save correction"}).click();
    await expectText(page, '[data-testid="set-row"]', "62.5 kg × 9");
    await page.screenshot({path: path.join(resultsDirectory, `${device}-workout.png`), fullPage: true});
    await finishWorkout(page);
    await expectText(page, "[data-dashboard-content]", "Pepper Push");

    await page.getByTestId("start-workout").click();
    await page.getByTestId("workout-name").fill("Dough Reloaded");
    await page.getByTestId("create-workout").click();
    await page.getByRole("button", {name: /Station/}).click();
    await page.getByTestId("exercise-search").fill("Bench Press");
    await page.locator("[data-add-exercise]").first().click();
    await expectText(page, '[data-testid="last-performance"]', "62.5 kg × 9");
    await page.getByTestId("repeat-last").click();
    if (await page.getByTestId("weight-input").inputValue() !== "62.5") {
      throw new Error("Repeat last did not restore the previous weight");
    }
    if (await page.getByTestId("reps-input").inputValue() !== "9") {
      throw new Error("Repeat last did not restore the previous reps");
    }
    await page.getByTestId("log-set").click();
    await expectText(page, '[data-testid="set-row"]', "62.5 kg × 9");

    await page.getByTestId("weight-input").fill("65");
    await page.getByTestId("reps-input").fill("8");
    await page.getByTestId("log-set").click();
    await expectText(page, ".sets-list", "65 kg × 8");
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByTestId("delete-set").last().click();
    await page.locator('[data-testid="set-row"]').filter({hasText: "65 kg × 8"}).waitFor({state: "detached"});
    await finishWorkout(page);

    await page.getByTestId("nav-stats").click();
    await expectText(page, '[data-testid="stats-workout-count"]', "2");
    await page.locator("[data-progress-exercise]").selectOption({label: "Bench Press"});
    await page.getByTestId("progress-chart").waitFor({state: "visible"});
    await expectText(page, "[data-stats-content]", "Bench Press");
    await expectText(page, "[data-stats-content]", "62.5 kg × 9");
    await page.screenshot({path: path.join(resultsDirectory, `${device}-progress.png`), fullPage: true});
  } catch (error) {
    await page.screenshot({path: path.join(resultsDirectory, `${device}-failure.png`), fullPage: true}).catch(() => {});
    throw error;
  } finally {
    await authenticator.dispose();
    await context.close();
  }

  if (errors.length) throw new Error(`Browser errors: ${errors.join(" | ")}`);
}


async function main() {
  await mkdir(resultsDirectory, {recursive: true});
  const helper = await import(pathToFileURL(fastPassKeyHelper()).href);
  const browser = await chromium.launch({headless: true});
  const completed = [];
  try {
    for (const device of devices) {
      await runJourney(browser, helper.createVirtualAuthenticator, device);
      completed.push(device);
    }
  } finally {
    await browser.close();
  }
  const summary = `# Repperoni browser E2E\n\n- Base URL: ${baseUrl}\n- Devices: ${completed.join(", ")}\n- Result: passed\n`;
  await writeFile(path.join(resultsDirectory, "summary.md"), summary);
  console.log(summary);
}


main().catch(async (error) => {
  await mkdir(resultsDirectory, {recursive: true});
  await writeFile(path.join(resultsDirectory, "summary.md"), `# Repperoni browser E2E\n\nResult: failed\n\n${error.stack || error}\n`);
  console.error(error);
  process.exitCode = 1;
});
