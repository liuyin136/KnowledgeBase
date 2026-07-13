import Link from "next/link";

const NAV_ITEMS = [
  { href: "/rag/search", label: "Search" },
  { href: "/rag/library", label: "Library" },
  { href: "/rag/memory", label: "Memory" },
] as const;

export function RagNav() {
  return (
    <nav className="rag-nav" aria-label="RAG navigation">
      {NAV_ITEMS.map((item) => (
        <Link key={item.href} href={item.href} className="cp-link">
          {item.label}
        </Link>
      ))}
      <Link href="/" className="cp-link rag-nav-home">
        Home
      </Link>
    </nav>
  );
}
