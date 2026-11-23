import { BaseError } from "viem";
import { expect, test } from "vitest";
import { revertData } from "./revertData";

const carrying = (fields: object) => Object.assign(new BaseError("reverted"), fields);

test("revert data is found as raw, data or data.data, in the error or its causes", () => {
  expect(revertData(carrying({ raw: "0x01" }))).toBe("0x01");
  expect(revertData(carrying({ data: "0x02" }))).toBe("0x02");
  const cause = Object.assign(new Error("rpc"), { data: { data: "0x03" } });
  expect(revertData(new BaseError("call failed", { cause }))).toBe("0x03");
});

test("an error with no revert data carries none", () => {
  expect(revertData(carrying({ data: { message: "no" } }))).toBeNull();
  expect(revertData(new Error("plain"))).toBeNull();
  expect(revertData(null)).toBeNull();
});
