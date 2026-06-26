import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, uploadPdfs } from "@/lib/api";
import type { Job } from "@/lib/types";

function job(id: string): Job {
  return {
    job_id: id,
    status: "pending",
    pdf_path: `/app/pdfs/${id}.pdf`,
    records: [],
    flagged: [],
    created_at: "2026-06-25T00:00:00Z",
    completed_at: null,
    token_usage: null,
    cost_usd: null,
    processing_duration_seconds: null,
    error: null,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("uploadPdfs", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("creates one upload request per selected PDF", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(job("job-a"), 201))
      .mockResolvedValueOnce(jsonResponse(job("job-b"), 201));
    vi.stubGlobal("fetch", fetchMock);

    const files = [
      new File(["%PDF-1.4"], "a.pdf", { type: "application/pdf" }),
      new File(["%PDF-1.4"], "b.pdf", { type: "application/pdf" }),
    ];

    const result = await uploadPdfs(files, true);

    expect(result.accepted.map((j) => j.job_id)).toEqual(["job-a", "job-b"]);
    expect(result.failed).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/backend/jobs?bypass_cache=true",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/backend/jobs?bypass_cache=true",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    );
  });

  it("returns accepted jobs and failed files when only part of the batch fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(job("job-a"), 201))
      .mockResolvedValueOnce(jsonResponse({ message: "Uploaded file is not a PDF" }, 400));
    vi.stubGlobal("fetch", fetchMock);

    const files = [
      new File(["%PDF-1.4"], "a.pdf", { type: "application/pdf" }),
      new File(["plain text"], "notes.pdf", { type: "application/pdf" }),
    ];

    const result = await uploadPdfs(files);

    expect(result.accepted.map((j) => j.job_id)).toEqual(["job-a"]);
    expect(result.failed).toHaveLength(1);
    expect(result.failed[0]?.file.name).toBe("notes.pdf");
    expect(result.failed[0]?.error).toBeInstanceOf(ApiError);
    expect((result.failed[0]?.error as ApiError).status).toBe(400);
  });
});
