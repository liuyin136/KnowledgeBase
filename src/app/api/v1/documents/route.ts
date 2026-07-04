/**
 * POST /api/v1/documents — create a document (text-based; multipart not needed for v1).
 * GET  /api/v1/documents — paginated list.
 *
 * Body: { filename, contentType?, text } OR multipart/form-data with a "file" field.
 */
import { NextRequest, NextResponse } from "next/server";
import { withErrors, parsePagination, parseBody } from "@/lib/rag/api-helpers";
import { ValidationError } from "@/lib/rag/errors";
import * as store from "@/lib/rag/store";

export async function POST(req: NextRequest) {
  return withErrors(async () => {
    const contentType = req.headers.get("content-type") || "";
    let filename: string;
    let docContentType: string;
    let text: string;
    if (contentType.includes("multipart/form-data")) {
      const form = await req.formData();
      const file = form.get("file");
      if (!(file instanceof File)) throw new ValidationError("file field is required");
      filename = file.name;
      docContentType = file.type || "text/plain";
      text = await file.text();
    } else {
      const body = await parseBody<{ filename: string; contentType?: string; text: string }>(req);
      if (!body.filename?.trim()) throw new ValidationError("filename is required");
      if (typeof body.text !== "string") throw new ValidationError("text is required");
      filename = body.filename;
      docContentType = body.contentType || "text/plain";
      text = body.text;
    }
    const id = await store.createDocument({
      filename,
      contentType: docContentType,
      size: new Blob([text]).size,
      text,
    });
    return NextResponse.json({ id, filename, contentType: docContentType, size: text.length }, { status: 201 });
  });
}

export async function GET(req: NextRequest) {
  return withErrors(async () => {
    const { page, pageSize } = parsePagination(req);
    const { items, total } = await store.listDocuments({ page, pageSize });
    return NextResponse.json({ items, total, page, pageSize, hasMore: page * pageSize < total });
  });
}
