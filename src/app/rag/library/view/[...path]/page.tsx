"use client";

import { use } from "react";
import { VaultFileViewer } from "@/components/rag/VaultFileViewer";

export default function RagViewPage({ params }: { params: Promise<{ path: string[] }> }) {
  const { path: pathSegments } = use(params);
  const filePath = pathSegments.map(decodeURIComponent).join("/");
  return <VaultFileViewer relativePath={filePath} />;
}
