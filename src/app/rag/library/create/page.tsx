"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Legacy create route — vault uploads live on the main library page. */
export default function RagLibraryCreatePage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/rag/library");
  }, [router]);
  return <p>Redirecting to vault library…</p>;
}
