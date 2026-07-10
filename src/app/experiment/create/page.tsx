"use client";

import { LogCreateForm } from "@/components/experiment/LogCreateForm";

export default function CreatePage() {
  return (
    <>
      <h2 className="experiment-title" style={{ fontSize: "1.1rem", marginBottom: "1.5rem" }}>
        Create Log
      </h2>
      <LogCreateForm />
    </>
  );
}
