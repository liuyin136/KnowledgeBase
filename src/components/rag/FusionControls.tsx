"use client";

export function FusionControls({
  w1,
  coarseDim,
  onW1Change,
  onCoarseDimChange,
}: {
  w1: number;
  coarseDim: 256 | 512;
  onW1Change: (v: number) => void;
  onCoarseDimChange: (v: 256 | 512) => void;
}) {
  const w2 = 1 - w1;
  return (
    <div className="rag-panel">
      <label htmlFor="w1-slider">
        Vector weight (w1): {w1.toFixed(2)} · BM25 weight (w2): {w2.toFixed(2)}
      </label>
      <input
        id="w1-slider"
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={w1}
        onChange={(e) => onW1Change(Number(e.target.value))}
        style={{ width: "100%", marginTop: "0.5rem" }}
      />
      <div style={{ marginTop: "1rem" }}>
        <label htmlFor="coarse-dim">Coarse dimension: </label>
        <select
          id="coarse-dim"
          className="rag-select"
          value={coarseDim}
          onChange={(e) => onCoarseDimChange(Number(e.target.value) as 256 | 512)}
        >
          <option value={256}>256</option>
          <option value={512}>512</option>
        </select>
      </div>
    </div>
  );
}
