import type { ParamText } from "../domain/abi";
import { placeholder } from "../domain/values";
import type { Form } from "../state/store";

export function Fields({ form, texts }: { form: Form; texts: readonly ParamText[] }) {
  if (texts.length === 0) return null;
  return (
    <div className="fields">
      {texts.map(({ param: p, text }) => (
        <label className="field" key={p.name}>
          <span>{p.name}: {p.type}</span>
          <input value={text} spellCheck={false}
            placeholder={p.abi ? placeholder(p.abi) : ""}
            onChange={(e) => form.set(p.name, e.target.value)} />
        </label>
      ))}
    </div>
  );
}
