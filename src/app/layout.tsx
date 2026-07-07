import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "RAG Lab Baseline",
  description: "Local-first RAG platform baseline",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
