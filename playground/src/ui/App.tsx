// The page (playground/README.md).
import { useEffect } from "react";
import { defaultDeployment, routeDeployment } from "../chain/deployments";
import { repository } from "../chain/repository";
import { config } from "../config";
import type { Deployed } from "../domain/config";
import { Route } from "../domain/route";
import type { Source } from "../domain/source";
import { DeploymentContext } from "../state/deployment";
import { useCompile } from "../state/queries";
import { router, useRoute } from "../state/route";
import { store, useProgram } from "../state/store";
import { CompilePanel } from "./CompilePanel";
import { ContractPage, UnknownChainPage } from "./ContractPage";
import { CopyButton } from "./CopyButton";
import { DeployPanel } from "./DeployPanel";
import { Editor, compileMark } from "./Editor";
import { OpenContract } from "./OpenContract";
import { RegistryPage } from "./RegistryPage";
import { TopBar } from "./TopBar";

const EXAMPLES = Object.keys(config.examples).sort();

// Returns the name of the example whose text is `source`, or "" when it is none.
const exampleOf = (source: Source): string =>
  EXAMPLES.find((name) => config.examples[name] === source) ?? "";

// Puts the program that `route` carries in the editor. A route without one keeps the
// editor's program.
function useRouteSource(route: Route): void {
  useEffect(() => {
    if (route.source !== null) store.setSource(route.source);
  }, [route.source]);
}

function ShareButton({ source }: { source: Source }) {
  return <CopyButton label="Copy link" failed="Link in the address bar" text={() => {
    const shared = Route.editor(source);
    router.replace(shared);
    return router.url(shared);
  }} />;
}

function About() {
  return (
    <section className="card about" aria-label="About">
      <h2>About</h2>
      <p>Fe0 is a subset of <a href="https://github.com/argotorg/fe">Fe</a>, the smart contract
        language, with a compiler written in Fe that also runs on chain. This page compiles your
        program there: a compile is a free <code>eth_call</code>, and a deploy is a transaction
        from your wallet.</p>
      <p className="links">
        <a href={repository.docUrl("SPEC.md")}>Spec</a>
        <a href={repository.docUrl("DEMO.md")}>Demo from the command line</a>
        <a href={repository.url}>Repository</a>
      </p>
    </section>
  );
}

function EditorPage() {
  const program = useProgram();
  const { source } = program;
  const compile = useCompile(program);
  return (
    <main className="workspace">
      <section className="editor-pane" aria-label="Program">
        <div className="toolbar">
          <label className="select">
            <span>Example</span>
            <select value={exampleOf(source)} onChange={(e) => {
              const text = config.examples[e.target.value];
              if (text !== undefined) store.setSource(text);
            }}>
              <option value="" disabled>Your program</option>
              {EXAMPLES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <ShareButton source={source} />
        </div>
        <Editor mark={compileMark(compile)} />
        <CompilePanel view={compile} />
      </section>
      <aside className="side stack">
        <DeployPanel program={program}
          code={compile.kind === "compiled" ? compile.code : null} />
        <OpenContract />
        <About />
      </aside>
    </main>
  );
}

// The page of `route`. `known` is the deployment the route names, or undefined when config.ts
// lacks its chain.
function Page({ route, known }: { route: Route; known: Deployed | undefined }) {
  const { place } = route;
  switch (place.page) {
    case "editor":
      return <EditorPage />;
    case "registry":
      return <RegistryPage account={place.account} />;
    case "contract":
      return known
        ? <ContractPage address={place.address} routeSource={route.source} />
        : <UnknownChainPage chainId={place.chainId} address={place.address} />;
  }
}

export function App() {
  const route = useRoute();
  useRouteSource(route);
  const known = routeDeployment(route);
  return (
    <DeploymentContext value={known ?? defaultDeployment}>
      <TopBar section={route.place.page} />
      <Page route={route} known={known} />
    </DeploymentContext>
  );
}
