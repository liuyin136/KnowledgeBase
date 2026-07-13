import type { SearchHit } from "@/lib/api/search";
import { SearchResultCard } from "./SearchResultCard";

export function SearchResults({
  hits,
  cached,
}: {
  hits: SearchHit[];
  cached: boolean;
}) {
  if (hits.length === 0) {
    return <p>No results — try a different query</p>;
  }
  return (
    <section aria-live="polite" aria-busy="false">
      {cached && <p className="rag-cached">CACHED</p>}
      {hits.map((hit, i) => (
        <SearchResultCard key={hit.chunk_id} hit={hit} rank={i + 1} />
      ))}
    </section>
  );
}
