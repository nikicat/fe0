import { expect, test } from "vitest";
import { txUrl } from "./chains";
import { defaultDeployment } from "./deployments";

const { chain } = defaultDeployment;
const hash = `0x${"ab".repeat(32)}` as const;

test("a transaction's link joins the explorer's tx/ path", () => {
  expect(txUrl(defaultDeployment, hash)).toBe(`${chain.explorer}/tx/${hash}`);
});
