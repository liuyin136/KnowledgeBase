"use client";

/**
 * Reusable markdown editor wrapper around @mdxeditor/editor.
 *
 * Plugins: headings, lists, link, quote, markdown-shortcut, link-dialog,
 * toolbar (Undo/Redo · Bold/Italic/Underline · Block-type/Headings ·
 * Lists toggle · Create Link).
 *
 * The component is controlled — pass `value` (markdown string) and `onChange`.
 * Pass `readOnly` to render the editor in a non-editable mode (still shows the
 * toolbar but input is disabled — useful for the "Rendered" preview variant
 * when you want consistent typography).
 *
 * NOTE: imports `@mdxeditor/editor/style.css` once at module load.
 */

import * as React from "react";
import {
  MDXEditor,
  type MDXEditorMethods,
  headingsPlugin,
  listsPlugin,
  linkPlugin,
  quotePlugin,
  markdownShortcutPlugin,
  linkDialogPlugin,
  toolbarPlugin,
  UndoRedo,
  BoldItalicUnderlineToggles,
  BlockTypeSelect,
  ListsToggle,
  CreateLink,
  Separator,
} from "@mdxeditor/editor";
import "@mdxeditor/editor/style.css";
import { cn } from "@/lib/utils";

export interface MarkdownEditorProps {
  value: string;
  onChange?: (markdown: string) => void;
  readOnly?: boolean;
  placeholder?: string;
  className?: string;
  /** Heading levels available in the BlockTypeSelect dropdown (defaults to 1–6). */
  headingLevels?: readonly (1 | 2 | 3 | 4 | 5 | 6)[];
  /** Hide the toolbar (useful for ultra-compact previews). */
  hideToolbar?: boolean;
  ariaLabel?: string;
}

export const MarkdownEditor = React.forwardRef<MDXEditorMethods, MarkdownEditorProps>(
  function MarkdownEditor(
    {
      value,
      onChange,
      readOnly = false,
      placeholder = "Edit markdown…",
      className,
      headingLevels = [1, 2, 3, 4, 5, 6],
      hideToolbar = false,
      ariaLabel = "Markdown editor",
    },
    ref,
  ) {
    return (
      <div
        className={cn(
          "rounded-md border border-input bg-background overflow-hidden focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-0",
          readOnly && "bg-muted/30",
          className,
        )}
      >
        <MDXEditor
          ref={ref}
          aria-label={ariaLabel}
          markdown={value ?? ""}
          onChange={(v) => onChange?.(v)}
          placeholder={placeholder}
          readOnly={readOnly}
          contentEditableClassName="md-prose max-w-none min-h-[180px] px-3 py-2.5 leading-relaxed focus:outline-none"
          plugins={[
            headingsPlugin({ allowedHeadingLevels: headingLevels }),
            listsPlugin(),
            quotePlugin(),
            linkPlugin(),
            linkDialogPlugin(),
            markdownShortcutPlugin(),
            ...(hideToolbar
              ? []
              : [
                  toolbarPlugin({
                    toolbarContents: () => (
                      <>
                        <UndoRedo />
                        <Separator />
                        <BoldItalicUnderlineToggles />
                        <Separator />
                        <BlockTypeSelect />
                        <ListsToggle />
                        <Separator />
                        <CreateLink />
                      </>
                    ),
                  }),
                ]),
          ]}
        />
      </div>
    );
  },
);

/**
 * Read-only rendered markdown view using react-markdown. Useful for the
 * "Rendered" toggle alongside the editable MarkdownEditor in "Raw" mode.
 *
 * Uses explicit per-element Tailwind classes (no @tailwindcss/typography
 * dependency) so the rendered preview matches the surrounding shadcn UI.
 */
export function MarkdownRender({
  value,
  className,
}: {
  value: string;
  className?: string;
}) {
  // Lazy-load react-markdown only on the client to keep SSR light.
  const ReactMarkdown = React.lazy(() => import("react-markdown"));
  return (
    <div
      className={cn(
        "max-w-none text-sm leading-relaxed text-foreground space-y-3",
        className,
      )}
    >
      <React.Suspense
        fallback={
          <div className="text-xs text-muted-foreground italic">
            Rendering preview…
          </div>
        }
      >
        <ReactMarkdown
          components={{
            h1: ({ children }) => (
              <h1 className="text-xl font-semibold tracking-tight mt-4 mb-2">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-lg font-semibold tracking-tight mt-4 mb-2">{children}</h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-base font-semibold mt-3 mb-1.5">{children}</h3>
            ),
            h4: ({ children }) => (
              <h4 className="text-sm font-semibold mt-3 mb-1.5">{children}</h4>
            ),
            h5: ({ children }) => (
              <h5 className="text-sm font-medium mt-2 mb-1">{children}</h5>
            ),
            h6: ({ children }) => (
              <h6 className="text-xs font-medium uppercase tracking-wide text-muted-foreground mt-2 mb-1">{children}</h6>
            ),
            p: ({ children }) => <p className="text-sm leading-relaxed">{children}</p>,
            ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 text-sm">{children}</ul>,
            ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 text-sm">{children}</ol>,
            li: ({ children }) => <li className="leading-relaxed">{children}</li>,
            blockquote: ({ children }) => (
              <blockquote className="border-l-2 border-primary/40 pl-3 italic text-muted-foreground">
                {children}
              </blockquote>
            ),
            a: ({ children, href }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline underline-offset-2 hover:opacity-80"
              >
                {children}
              </a>
            ),
            strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
            em: ({ children }) => <em className="italic">{children}</em>,
            code: ({ children }) => (
              <code className="rounded bg-muted px-1 py-0.5 text-xs font-mono">{children}</code>
            ),
            pre: ({ children }) => (
              <pre className="rounded-md border bg-muted/50 p-3 text-xs font-mono overflow-x-auto thin-scroll">
                {children}
              </pre>
            ),
            hr: () => <hr className="border-border my-4" />,
            table: ({ children }) => (
              <div className="overflow-x-auto thin-scroll">
                <table className="w-full text-xs border-collapse">{children}</table>
              </div>
            ),
            th: ({ children }) => (
              <th className="border border-border bg-muted/50 px-2 py-1 text-left font-medium">{children}</th>
            ),
            td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
          }}
        >
          {value || ""}
        </ReactMarkdown>
      </React.Suspense>
    </div>
  );
}
