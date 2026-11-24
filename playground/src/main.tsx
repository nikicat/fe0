// The page's entry point (playground/README.md).
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { WagmiProvider } from "wagmi";
import { wagmiConfig } from "./chain/chains";
import { newQueryClient } from "./state/queries";
import { router } from "./state/route";
import { initialSource, store } from "./state/store";
import { App } from "./ui/App";
import "./ui/style.css";

store.setSource(initialSource(router.current()));

const queryClient = newQueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </WagmiProvider>
  </StrictMode>,
);
