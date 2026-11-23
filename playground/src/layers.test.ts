// Checks the layer rule of docs/adr/0032 ("Layers"), with its exception for config.ts.
import { readFileSync, readdirSync } from "node:fs";
import { expect, test } from "vitest";

const LAYERS = ["domain", "chain", "state", "ui"];
const src = new URL("./", import.meta.url);

test("each layer imports only from the layers above it", () => {
  for (const [rank, layer] of LAYERS.entries()) {
    const dir = new URL(`${layer}/`, src);
    for (const file of readdirSync(dir).filter((f) => /\.tsx?$/.test(f))) {
      const text = readFileSync(new URL(file, dir), "utf8");
      for (const [, path] of text.matchAll(/from "\.\.\/(\w+)/g)) {
        const at = LAYERS.indexOf(path!);
        const allowed = path === "config" ? layer !== "domain" : at >= 0 && at < rank;
        expect(allowed, `${layer}/${file} imports ../${path}`).toBe(true);
      }
    }
  }
});
