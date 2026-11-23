import { expect, test } from "vitest";
import { explorerUrl } from "./chains";
import { defaultDeployment } from "./deployments";

const { chain } = defaultDeployment;
const hash = `0x${"ab".repeat(32)}` as const;
const address = `0x${"cd".repeat(20)}` as const;

test("explorer links join the explorer's tx/ and address/ paths", () => {
  expect(explorerUrl(defaultDeployment, { tx: hash })).toBe(`${chain.explorer}/tx/${hash}`);
  expect(explorerUrl(defaultDeployment, { address }))
    .toBe(`${chain.explorer}/address/${address}`);
});
