"use client";

import { use } from "react";
import { VaultFileEditor } from "@/components/rag/VaultFileEditor";

export default function RagEditPage({ params }: { params: Promise<{ path: string[] }> }) {
  const { path: pathSegments } = use(params);
  const filePath = pathSegments.map(decodeURIComponent).join("/");
  return <VaultFileEditor relativePath={filePath} />;
}
