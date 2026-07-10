"use client";

import { use } from "react";
import { LogEditor } from "@/components/experiment/LogEditor";

export default function EditPage({
  params,
}: {
  params: Promise<{ path: string[] }>;
}) {
  const { path: pathSegments } = use(params);
  const filePath = pathSegments.map(decodeURIComponent).join("/");

  return <LogEditor filePath={filePath} />;
}
