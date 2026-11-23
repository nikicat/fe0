// A button that copies text to the clipboard and says for two seconds whether it did.
import { useState } from "react";

// Copies the text that `text` returns, which it calls once on each click. `failed` is the
// label shown when the clipboard refuses.
export function CopyButton({ label, text, failed = "Copy failed" }: {
  label: string; text: () => string; failed?: string;
}) {
  const [shown, setShown] = useState(label);
  return (
    <button type="button" onClick={async () => {
      try {
        await navigator.clipboard.writeText(text());
        setShown("Copied");
      } catch {
        setShown(failed);
      }
      setTimeout(() => setShown(label), 2000);
    }}>{shown}</button>
  );
}
