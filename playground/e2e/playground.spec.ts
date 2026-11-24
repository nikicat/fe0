import { readFileSync } from "node:fs";
import type { Page } from "@playwright/test";
import { type Address, getAbiItem, toFunctionSelector } from "viem";
import { registryAbi } from "../src/config";
import { Route } from "../src/domain/route";
import type { Source } from "../src/domain/source";
import { expect, test } from "./fixtures";
import { chain } from "./fork";

// A salt that no earlier deploy used, on the fork or on the chain it forks, so that each test
// deploys a new contract.
const freshSalt = () => `e2e ${Date.now()} ${Math.random()}`;

const corpus = (name: string) =>
  readFileSync(new URL(`../../corpus/${name}`, import.meta.url), "utf8") as Source;

const infoSelector = toFunctionSelector(getAbiItem({ abi: registryAbi, name: "info" }));

// Opens the editor on the counter example, and fills its deploy form with `from` and a fresh
// salt.
async function fillCounter(page: Page, from: number) {
  await page.goto("./");
  await expect(page.getByText(/^Compiled:/)).toBeVisible();
  await page.getByLabel("from: u256").fill(String(from));
  await page.getByLabel("salt (optional)").fill(freshSalt());
}

// Clicks Deploy, waits for the contract's page that it opens, and returns its address.
async function submitDeploy(page: Page): Promise<Address> {
  await page.getByRole("button", { name: "Deploy" }).click();
  await expect(page).toHaveURL((url) => Route.parse(url.hash).place.page === "contract");
  const { place } = Route.parse(new URL(page.url()).hash);
  if (place.page !== "contract" || place.chainId !== chain.id) {
    throw new Error(`Deploy opened ${page.url()}`);
  }
  return place.address;
}

async function deployCounter(page: Page, from: number): Promise<Address> {
  await fillCounter(page, from);
  return submitDeploy(page);
}

test("compiles the example that the page opens with on chain", async ({ page }) => {
  await page.goto("./");
  await expect(page.getByLabel("Example")).toHaveValue("counter");
  await expect(page.getByText(/^Compiled: [\d,]+ bytes of deploy code\./)).toBeVisible();
  await expect(page.getByText(/[\d,]+ gas as a transaction, free as an eth_call\./))
    .toBeVisible();
});

test("shows a compile error with the CLI's code, and marks it in place", async ({ page }) => {
  await page.goto(`./${Route.editor(corpus("reject/assign_let.fe")).hash()}`);
  const status = page.getByRole("region", { name: "Compile", exact: true }).getByRole("status");
  await expect(status).toHaveText("5:5 N014 cannot assign to this name");
  await expect(page.locator(".cm-lintRange-error")).toHaveCount(1);
});

test("deploys counter, calls Get, and sends Increment", async ({ page }) => {
  await deployCounter(page, 2);
  await expect(page.getByText(/^[\d,]+ bytes of code$/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Counter", level: 1 })).toBeVisible();
  const record = page.getByRole("region", { name: "Record" });
  await expect(record.getByText("from = 2")).toBeVisible();
  await expect(record.getByText(/^Fe0 \d+\.\d+\.\d+$/)).toBeVisible();

  const form = (name: string) => page.getByRole("region", { name, exact: true });
  await form("Get").getByRole("button", { name: "Call" }).click();
  await expect(form("Get").getByRole("status")).toHaveText("Returned 2");
  await form("Increment").getByRole("button", { name: "Send" }).click();
  await expect(form("Increment").getByRole("status"))
    .toHaveText(/^Mined 0x[0-9a-f]{64}, [\d,]+ gas\.$/);
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
  await expect(page.getByLabel("Example")).toHaveValue("");
});

test("the registry lists a deployed contract first, and opens it", async ({ page }) => {
  const address = await deployCounter(page, 7);

  await page.goto(`./${Route.registry().hash()}`);
  const first = page.getByRole("row").nth(1);
  await expect(first).toContainText("Counter(7)");
  await expect(first).toContainText(/Fe0 \d+\.\d+\.\d+/);
  await expect(first.getByRole("cell").nth(2)).toHaveText(/^0x[0-9a-f]{64}$/);

  // The list has read each record. The contract's page, the list opened again and a reload
  // then read none from the chain.
  const reads: string[] = [];
  page.on("request", (r) => {
    const body = r.postData() ?? "";
    if (body.includes(infoSelector) || body.includes("eth_getLogs")) reads.push(body);
  });
  await first.getByRole("cell").nth(1).locator(`a[href$="/${address}"]`).click();
  await expect(page.getByText("from = 7")).toBeVisible();
  await page.getByRole("link", { name: "Registry", exact: true }).first().click();
  await expect(first).toContainText("Counter(7)");
  // The browser keeps the records.
  await page.reload();
  await expect(first).toContainText("Counter(7)");
  expect(reads).toEqual([]);
});

test("a contract's page shows the registry's record of a contract it did not deploy",
  async ({ page }) => {
    // The demo's counter, which tools/deploy_registry.py deployed through the registry on
    // Arbitrum One, where Registry records Ethereum's block number (ADR 0031, "Reading").
    const counter = "0xC9757E2Bf29ABb6697E360131008A74F1B247eC0";
    await page.goto(`./${Route.contract(chain.id, counter).hash()}`);
    await expect(page.getByText("from = 2")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".cm-content")).toContainText("contract Counter");
  });

test("the same program, arguments and salt reach the address the form showed, once",
  async ({ page }) => {
    await fillCounter(page, 5);
    const deploy = page.getByRole("region", { name: "Deploy" });
    const target = deploy.getByText("Deploys to");
    await expect(target).toBeVisible();
    const shown = /0x[0-9a-fA-F]{40}/.exec(await target.textContent() ?? "")?.[0];
    const address = await submitDeploy(page);
    expect(address).toBe(shown);

    await page.getByRole("link", { name: "Editor" }).click();
    await expect(deploy.getByText("Already deployed at")).toContainText(address);
    await deploy.getByRole("button", { name: "Open" }).click();
    await expect(page).toHaveURL(
      (url) => url.hash === Route.contract(chain.id, address).hash());
  });
