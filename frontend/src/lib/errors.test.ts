import { AxiosError } from "axios";
import { describe, expect, it } from "vitest";
import { mapApiError } from "./errors";

function axiosError(status: number, data: unknown = {}, headers: Record<string, string> = {}) {
  const err = new AxiosError("request failed", "ERR_BAD_RESPONSE");
  // @ts-expect-error - partial response is enough for the mapper
  err.response = { status, data, headers, statusText: "", config: {} };
  return err;
}

describe("mapApiError", () => {
  it("maps each HTTP status to its kind", () => {
    expect(mapApiError(axiosError(400)).kind).toBe("bad_input");
    expect(mapApiError(axiosError(401)).kind).toBe("unauthenticated");
    expect(mapApiError(axiosError(403)).kind).toBe("forbidden");
    expect(mapApiError(axiosError(404)).kind).toBe("not_found");
    expect(mapApiError(axiosError(409)).kind).toBe("conflict");
    expect(mapApiError(axiosError(422)).kind).toBe("domain");
    expect(mapApiError(axiosError(429)).kind).toBe("rate_limited");
    expect(mapApiError(axiosError(503)).kind).toBe("ai_unavailable");
    expect(mapApiError(axiosError(418)).kind).toBe("unknown");
  });

  it("surfaces the domain code + detail message on a 422", () => {
    const e = mapApiError(axiosError(422, { detail: "Cannot reassign mid-cycle", code: "REPORTING_CYCLE" }));
    expect(e.kind).toBe("domain");
    expect(e.code).toBe("REPORTING_CYCLE");
    expect(e.message).toBe("Cannot reassign mid-cycle");
  });

  it("extracts Retry-After + upgrade hint on a 429", () => {
    const e = mapApiError(axiosError(429, { upgrade_hint: { pack: "FULL_AI" } }, { "retry-after": "30" }));
    expect(e.kind).toBe("rate_limited");
    expect(e.retryAfter).toBe(30);
    expect(e.upgradeHint).toBe(true);
  });

  it("pulls field errors out of a 400 body", () => {
    const e = mapApiError(axiosError(400, { weight: ["Must sum to 100."], email: "invalid" }));
    expect(e.kind).toBe("bad_input");
    expect(e.fields).toEqual({ weight: ["Must sum to 100."], email: ["invalid"] });
  });

  it("treats a response-less axios error as a network error", () => {
    expect(mapApiError(new AxiosError("Network Error", "ERR_NETWORK")).kind).toBe("network");
  });

  it("passes an already-mapped ApiError straight through", () => {
    const already = { kind: "forbidden" as const, message: "nope" };
    expect(mapApiError(already)).toBe(already);
  });

  it("falls back to unknown for a plain Error / non-error value", () => {
    expect(mapApiError(new Error("boom")).kind).toBe("unknown");
    expect(mapApiError("weird").kind).toBe("unknown");
  });
});
