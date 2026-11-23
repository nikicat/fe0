import { readFileSync } from "node:fs";
import { routeHash } from "../src/domain/route";
import type { Source } from "../src/domain/source";
import { expect, test } from "./fixtures";
import { chain } from "./fork";

const corpus = (name: string) =>
  readFileSync(new URL(`../../corpus/${name}`, import.meta.url), "utf8") as Source;

test("compiles the example that the page opens with on chain", async ({ page }) => {
  await page.goto("./");
  await expect(page.getByText(/^Compiled: [\d,]+ bytes of deploy code\./)).toBeVisible();
  await expect(page.getByText(/the compile would cost [\d,]+ gas; as an eth_call it is free\./))
    .toBeVisible();
});

test("shows a compile error with the CLI's code, and marks it in place", async ({ page }) => {
  await page.goto(`./${routeHash({ page: "editor", source: corpus("reject/assign_let.fe") })}`);
  const status = page.getByRole("region", { name: "Compile", exact: true }).getByRole("status");
  await expect(status).toHaveText("5:5 N014 cannot assign to this name");
  await expect(page.locator(".cm-lintRange-error")).toHaveCount(1);
});

test("deploys counter, calls Get, and sends Increment", async ({ page }) => {
  await page.goto("./");
  await expect(page.getByText(/^Compiled:/)).toBeVisible();
  await page.getByLabel("from: u256").fill("2");
  await page.getByRole("button", { name: "Deploy" }).click();
  await expect(page).toHaveURL(new RegExp(`#/${chain.id}/0x[0-9a-fA-F]{40}$`));
  await expect(page.getByText(/bytes of code\./)).toBeVisible();

  const form = (name: string) => page.getByRole("region", { name, exact: true });
  await form("Get").getByRole("button", { name: "Call" }).click();
  await expect(form("Get").getByRole("status")).toHaveText("Returned 2");
  await form("Increment").getByRole("button", { name: "Send" }).click();
  await expect(form("Increment").getByRole("status"))
    .toHaveText(/^Mined 0x[0-9a-f]{4}…[0-9a-f]{4}, [\d,]+ gas\.$/);
  await form("Get").getByRole("button", { name: "Call" }).click();
  await expect(form("Get").getByRole("status")).toHaveText("Returned 3");
});

test("a shared link opens its program", async ({ page }) => {
  await page.goto("./");
  await page.getByLabel("Example").selectOption("fib");
  await page.getByRole("button", { name: "Copy link" }).click();
  await expect(page).toHaveURL(/#\/src\//);
  await page.reload();
  await expect(page.locator(".cm-content")).toContainText(corpus("fib.fe").split("\n")[0]!);
});

test("typing after Copy link keeps the editor's text", async ({ page }) => {
  await page.goto("./");
  await page.getByRole("button", { name: "Copy link" }).click();
  await expect(page).toHaveURL(/#\/src\//);
  await page.locator(".cm-content").click();
  await page.keyboard.press("ControlOrMeta+End");
  await page.keyboard.type("// kept");
  await expect(page.locator(".cm-content")).toContainText("// kept");
});
