// The playground page (playground/README.md).
import { $, escape } from "./dom.js";
import { clientOf, explorerLink } from "./chain.js";
import { Compiler } from "./compiler.js";
import { Editor, shareButton } from "./editor.js";
import { failures } from "./failure.js";
import { Forms } from "./forms.js";
import { linkedSource } from "./lib.js";
import { Wallet } from "./wallet.js";

const data = await (await fetch("data.json")).json();
const client = clientOf(data);
const wallet = new Wallet(client, (account) => {
  $("connect").textContent = `${account.slice(0, 6)}…${account.slice(-4)}`;
  $("deploy").disabled = false;
});
const editor = new Editor($("source"), $("gutter"), () => {
  compiler.compileSoon();
  forms.draw(editor.text);
});
const showFailure = failures(data, editor);
const compiler = new Compiler(data, client, editor, showFailure);
const forms = new Forms({ client, wallet, showFailure });

shareButton($("share"), editor);
$("copy-code").addEventListener("click",
  () => navigator.clipboard.writeText($("code").textContent));
$("connect").addEventListener("click",
  () => wallet.account().catch((e) => showFailure($("deploy-status"), e)));
$("deploy").addEventListener("click",
  () => compiler.deploy(wallet, forms, $("deploy-status")));

const example = $("example");
for (const name of Object.keys(data.examples)) example.add(new Option(name, name));
example.addEventListener("change", () => editor.open(data.examples[example.value]));

const compilerLink = explorerLink(client.chain, `address/${data.compiler}`, data.compiler);
$("release").innerHTML = `Compiler ${compilerLink}, built from the release` +
  ` <a href="${data.repo}/tree/${escape(data.tag)}">${escape(data.tag)}</a>.`;
for (const a of document.querySelectorAll("a[data-repo]")) {
  a.href = data.repo + a.dataset.repo;
}
editor.open(linkedSource(location.hash) ?? data.examples[example.value]);
