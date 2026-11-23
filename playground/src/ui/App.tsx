// The page (playground/README.md).
import { useEffect, useMemo } from "react";
import { defaultDeployment, routeDeployment } from "../chain/deployments";
import { config } from "../config";
import { outline as outlineOf } from "../domain/outline";
import type { Route } from "../domain/route";
import type { Source } from "../domain/source";
import { DeploymentContext } from "../state/deployment";
import { useCompile } from "../state/queries";
import { replaceRoute, routeUrl, useRoute } from "../state/route";
import { setSource, useSource } from "../state/store";
import { CompilePanel } from "./CompilePanel";
import { ContractPage, UnknownChainPage } from "./ContractPage";
import { CopyButton } from "./CopyButton";
import { DeployPanel } from "./DeployPanel";
import { Editor, compileMark } from "./Editor";
import { OpenContract } from "./OpenContract";
import { Explorer } from "./Explorer";

const EXAMPLES = Object.keys(config.examples).sort();

// Puts the program that `route` carries in the editor. A route without one keeps the
// editor's program.
function useRouteSource(route: Route): void {
  useEffect(() => {
    if (route.source !== null) setSource(route.source);
  }, [route.source]);
}

function ShareButton({ route, source }: { route: Route; source: Source }) {
  return <CopyButton label="Copy link" failed="Link in the address bar" text={() => {
    const shared = { ...route, source };
    replaceRoute(shared);
    return routeUrl(shared);
  }} />;
}

export function App() {
  const route = useRoute();
  useRouteSource(route);
  const source = useSource();
  const outline = useMemo(() => outlineOf(source), [source]);
  const known = routeDeployment(route);
  // A link to a chain that config.ts lacks still compiles, on the default deployment.
  const deployment = known ?? defaultDeployment;
  const compile = useCompile(deployment, source);

  return (
    <DeploymentContext value={deployment}>
      <header>
        <h1><a href="#/" className="home">Fe0 playground</a></h1>
        <p>Fe0 is a subset of <a href="https://github.com/argotorg/fe">Fe</a>, the smart
          contract language, with a compiler written in Fe. The compiler also runs on chain, as
          five contracts. This page sends your program to it: a compile is a free{" "}
          <code>eth_call</code>, and a deploy is a transaction from your wallet.</p>
        <p className="meta">Compiler{" "}
          <Explorer target={{ address: deployment.compiler }}
            text={deployment.compiler} /> on {deployment.chain.name}.{" "}
          <a href={deployment.sourcify}>Sourcify</a> shows whether its source is verified.</p>
      </header>
      <main>
        <section className="editor-pane" aria-label="Program">
          <div className="toolbar">
            <label>Example{" "}
              <select defaultValue="" onChange={(e) => {
                const text = config.examples[e.target.value];
                if (text !== undefined) setSource(text);
              }}>
                <option value="" disabled>Choose…</option>
                {EXAMPLES.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <ShareButton route={route} source={source} />
          </div>
          <Editor mark={compileMark(compile)} />
        </section>
        <section className="side" aria-label="Results">
          <CompilePanel view={compile} />
          {route.page === "editor"
            ? <>
                <DeployPanel source={source} outline={outline} />
                <OpenContract />
              </>
            : known
              ? <ContractPage address={route.address} outline={outline} />
              : <UnknownChainPage chainId={route.chainId} address={route.address} />}
        </section>
      </main>
      <footer>
        <a href={config.repo}>Repository</a> ·{" "}
        <a href={`${config.repo}/blob/main/docs/SPEC.md`}>Fe0's spec</a> ·{" "}
        <a href={`${config.repo}/blob/main/docs/DEMO.md`}>The demo from the command line</a>
      </footer>
    </DeploymentContext>
  );
}
