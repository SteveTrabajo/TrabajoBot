"use client";
import { useState } from "react";

/** Number input whose Save button appears only when the value was changed. */
export default function SizeField({ defaultValue }: { defaultValue: number }) {
  const [dirty, setDirty] = useState(false);
  return (
    <>
      <input
        type="number"
        name="size"
        defaultValue={defaultValue}
        min={0}
        max={999}
        onChange={(e) => setDirty(Number(e.target.value) !== defaultValue)}
        className="w-20 rounded-md border border-white/15 bg-transparent px-2 py-1 text-sm [color-scheme:dark]"
      />
      {dirty && (
        <button className="rounded-md bg-accent px-3 py-1 text-sm font-medium text-white transition hover:opacity-85">
          Save
        </button>
      )}
    </>
  );
}
