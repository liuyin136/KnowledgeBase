import Link from "next/link";
import "./experiment.css";

export default function ExperimentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="experiment-root">
      <div className="experiment-shell">
        <header className="experiment-header">
          <h1 className="experiment-title">Lab Notebook</h1>
          <nav className="experiment-nav">
            <Link href="/experiment" className="cp-link">
              Browse
            </Link>
            <Link href="/experiment/create" className="cp-link">
              Create
            </Link>
            <Link href="/" className="cp-link">
              Home
            </Link>
          </nav>
        </header>
        {children}
      </div>
    </div>
  );
}
