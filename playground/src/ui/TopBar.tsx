import { repository } from "../chain/repository";
import { EDITOR_HASH, type Place, Route } from "../domain/route";
import { useDeployment } from "../state/deployment";
import { WalletButton } from "./WalletButton";

export function TopBar({ section }: { section: Place["page"] }) {
  const { chain } = useDeployment();
  const tab = (name: Place["page"], href: string, text: string) => (
    <a href={href} className="tab" aria-current={section === name ? "page" : undefined}>
      {text}</a>
  );
  return (
    <header className="topbar">
      <a href={EDITOR_HASH} className="brand">
        <span className="logo" aria-hidden="true">Fe0</span>
        <span className="brand-name">playground</span>
      </a>
      <nav aria-label="Sections">
        {tab("editor", EDITOR_HASH, "Editor")}
        {tab("registry", Route.registry().hash(), "Registry")}
      </nav>
      <div className="topbar-end">
        <a className="link-muted hide-tablet" href={repository.docUrl("SPEC.md")}>Spec</a>
        <a className="link-muted hide-tablet" href={repository.url}>GitHub</a>
        <span className="chain" title={`Chain ${chain.id}`}>
          <span className="dot" aria-hidden="true" />{chain.name}</span>
        <WalletButton />
      </div>
    </header>
  );
}
