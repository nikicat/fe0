// The page's entry point (playground/README.md).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { WagmiProvider } from "wagmi";
import { wagmiConfig } from "./chain/chains";
import { parseRoute } from "./domain/route";
import { initialSource, setSource } from "./state/store";
import { App } from "./ui/App";
import "./ui/style.css";

setSource(initialSource(parseRoute(location.hash)));

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </WagmiProvider>
  </StrictMode>,
);
