/**
 * graphql.test.ts — Tests for graphql.ts (operation constants + executeGraphQL).
 *
 * The executeGraphQL function is tested with a mock fetch to avoid real
 * network calls.  The operation constants are validated for structural
 * correctness (presence of expected query/mutation fields).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  GRAPHQL_QUERY,
  GRAPHQL_MUTATION,
  GRAPHQL_DEFAULT_VARIABLES,
  executeGraphQL,
} from "../src/graphql.js";

// ---------------------------------------------------------------------------
// GRAPHQL_QUERY — structural validation
// ---------------------------------------------------------------------------

describe("GRAPHQL_QUERY", () => {
  it("is a non-empty string", () => {
    expect(typeof GRAPHQL_QUERY).toBe("string");
    expect(GRAPHQL_QUERY.length).toBeGreaterThan(0);
  });

  it("starts with the query keyword", () => {
    expect(GRAPHQL_QUERY.trimStart()).toMatch(/^query Query\(/);
  });

  it("contains interviewTemplate field", () => {
    expect(GRAPHQL_QUERY).toContain("interviewTemplate(");
  });

  it("contains interviewTemplates field", () => {
    expect(GRAPHQL_QUERY).toContain("interviewTemplates(");
  });

  it("contains company field", () => {
    expect(GRAPHQL_QUERY).toContain("company {");
  });

  it("contains companies field", () => {
    expect(GRAPHQL_QUERY).toContain("companies {");
  });

  it("contains companyTestSession field", () => {
    expect(GRAPHQL_QUERY).toContain("companyTestSession(");
  });

  it("contains companyTestSessions field", () => {
    expect(GRAPHQL_QUERY).toContain("companyTestSessions(");
  });

  it("contains companyTest field", () => {
    expect(GRAPHQL_QUERY).toContain("companyTest(");
  });

  it("contains companyTests field", () => {
    expect(GRAPHQL_QUERY).toContain("companyTests(");
  });

  it("contains liveInterview field", () => {
    expect(GRAPHQL_QUERY).toContain("liveInterview(");
  });

  it("contains liveInterviews field", () => {
    expect(GRAPHQL_QUERY).toContain("liveInterviews {");
  });

  it("contains hasAccess field", () => {
    expect(GRAPHQL_QUERY).toContain("hasAccess(");
  });

  it("contains hasAccessList field", () => {
    expect(GRAPHQL_QUERY).toContain("hasAccessList(");
  });

  it("contains taskSets field", () => {
    expect(GRAPHQL_QUERY).toContain("taskSets(");
  });

  it("contains testLabels field", () => {
    expect(GRAPHQL_QUERY).toContain("testLabels(");
  });

  it("contains aiInterviewers field", () => {
    expect(GRAPHQL_QUERY).toContain("aiInterviewers(");
  });

  it("contains llmModelCategories field", () => {
    expect(GRAPHQL_QUERY).toContain("llmModelCategories(");
  });

  it("contains taskLevel field", () => {
    expect(GRAPHQL_QUERY).toContain("taskLevel(");
  });

  it("contains task field", () => {
    expect(GRAPHQL_QUERY).toContain("task(");
  });

  it("contains codesignalCreatedTasks field", () => {
    expect(GRAPHQL_QUERY).toContain("codesignalCreatedTasks(");
  });

  it("contains frameworks field", () => {
    expect(GRAPHQL_QUERY).toContain("frameworks(");
  });

  it("contains atsCompanyTestSessions field", () => {
    expect(GRAPHQL_QUERY).toContain("atsCompanyTestSessions(");
  });

  it("contains standardizedTestSession field", () => {
    expect(GRAPHQL_QUERY).toContain("standardizedTestSession(");
  });

  it("contains standardizedTest field", () => {
    expect(GRAPHQL_QUERY).toContain("standardizedTest(");
  });

  it("contains certificationTests field", () => {
    expect(GRAPHQL_QUERY).toContain("certificationTests(");
  });

  it("contains role field", () => {
    expect(GRAPHQL_QUERY).toContain("role(");
  });

  it("contains companyRoles field", () => {
    expect(GRAPHQL_QUERY).toContain("companyRoles {");
  });

  it("contains systemRoles field", () => {
    expect(GRAPHQL_QUERY).toContain("systemRoles {");
  });

  it("contains user field", () => {
    expect(GRAPHQL_QUERY).toContain("user {");
  });

  it("contains servicePlans field", () => {
    expect(GRAPHQL_QUERY).toContain("servicePlans {");
  });
});

// ---------------------------------------------------------------------------
// GRAPHQL_MUTATION — structural validation
// ---------------------------------------------------------------------------

describe("GRAPHQL_MUTATION", () => {
  it("is a non-empty string", () => {
    expect(typeof GRAPHQL_MUTATION).toBe("string");
    expect(GRAPHQL_MUTATION.length).toBeGreaterThan(0);
  });

  it("starts with the mutation keyword", () => {
    expect(GRAPHQL_MUTATION.trimStart()).toMatch(/^mutation Mutation\(/);
  });

  it("contains deleteInterviewTemplate mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("deleteInterviewTemplate(");
  });

  it("contains createInterviewTemplate mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("createInterviewTemplate(");
  });

  it("contains editInterviewTemplate mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editInterviewTemplate(");
  });

  it("contains createCompanyTestSession mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("createCompanyTestSession(");
  });

  it("contains deleteCompanyTestSession mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("deleteCompanyTestSession(");
  });

  it("contains editCompanyTestSessionDuration mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editCompanyTestSessionDuration(");
  });

  it("contains editCompanyTestSessionExpiration mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editCompanyTestSessionExpiration(");
  });

  it("contains setCompanyTestSessionReminders mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("setCompanyTestSessionReminders(");
  });

  it("contains gradeCompanyTestResult mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("gradeCompanyTestResult(");
  });

  it("contains markCompanyTestResultAsGraded mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("markCompanyTestResultAsGraded(");
  });

  it("contains archiveCompanyTestSession mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("archiveCompanyTestSession(");
  });

  it("contains unarchiveCompanyTestSession mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("unarchiveCompanyTestSession(");
  });

  it("contains saveRole mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("saveRole(");
  });

  it("contains createCompanyRole mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("createCompanyRole(");
  });

  it("contains editCompanyRole mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editCompanyRole(");
  });

  it("contains deleteRole mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("deleteRole(");
  });

  it("contains createCompanyTest mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("createCompanyTest(");
  });

  it("contains editCompanyTest mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editCompanyTest(");
  });

  it("contains duplicateCompanyTest mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("duplicateCompanyTest(");
  });

  it("contains createLiveInterview mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("createLiveInterview {");
  });

  it("contains editLiveInterview mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editLiveInterview(");
  });

  it("contains deleteLiveInterview mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("deleteLiveInterview(");
  });

  it("contains addTaskToSets mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("addTaskToSets(");
  });

  it("contains removeTaskFromSets mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("removeTaskFromSets(");
  });

  it("contains setTaskInitialSource mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("setTaskInitialSource(");
  });

  it("contains unsetTaskInitialSource mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("unsetTaskInitialSource(");
  });

  it("contains createCodeReviewTask mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("createCodeReviewTask(");
  });

  it("contains editCodeReviewTask mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editCodeReviewTask(");
  });

  it("contains createDatabaseTask mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("createDatabaseTask(");
  });

  it("contains editDatabaseTask mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editDatabaseTask(");
  });

  it("contains createFreeCodingTask mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("createFreeCodingTask(");
  });

  it("contains editFreeCodingTask mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editFreeCodingTask(");
  });

  it("contains updateFrontendTask mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("updateFrontendTask(");
  });

  it("contains createQuizTask mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("createQuizTask(");
  });

  it("contains editQuizTask mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editQuizTask(");
  });

  it("contains createStandardTask mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("createStandardTask(");
  });

  it("contains editStandardTask mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editStandardTask(");
  });

  it("contains updateLockdownFrameworkEnabled mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("updateLockdownFrameworkEnabled(");
  });

  it("contains editCompanyPlanSettings mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("editCompanyPlanSettings(");
  });

  it("contains appendCompanyTestSessionVerificationNote mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("appendCompanyTestSessionVerificationNote(");
  });

  it("contains resendCompanyTestSession mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("resendCompanyTestSession(");
  });

  it("contains reactivateCompanyTestSession mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("reactivateCompanyTestSession(");
  });

  it("contains createCompanyTestFromFramework mutation", () => {
    expect(GRAPHQL_MUTATION).toContain("createCompanyTestFromFramework(");
  });
});

// ---------------------------------------------------------------------------
// GRAPHQL_DEFAULT_VARIABLES
// ---------------------------------------------------------------------------

describe("GRAPHQL_DEFAULT_VARIABLES", () => {
  it("is a plain object", () => {
    expect(typeof GRAPHQL_DEFAULT_VARIABLES).toBe("object");
    expect(GRAPHQL_DEFAULT_VARIABLES).not.toBeNull();
  });

  it("all values are null", () => {
    for (const val of Object.values(GRAPHQL_DEFAULT_VARIABLES)) {
      expect(val).toBeNull();
    }
  });

  it("includes query variables", () => {
    expect("interviewTemplateId" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
    expect("first" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
    expect("offset" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
    expect("frameworksFirst2" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
    expect("liveInterviewId" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
    expect("taskId" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
    expect("name" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
  });

  it("includes mutation variables", () => {
    expect("deleteInterviewTemplateInterviewTemplateId2" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
    expect("interviewTemplateFields" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
    expect("sessionFields" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
    expect("score" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
    expect("patch" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
    expect("language" in GRAPHQL_DEFAULT_VARIABLES).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// executeGraphQL — unit tests with mocked fetch
// ---------------------------------------------------------------------------

describe("executeGraphQL", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("POSTs to the endpoint with Content-Type application/json", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: { company: { id: "1" } } }),
    });
    vi.stubGlobal("fetch", mockFetch);

    await executeGraphQL("https://api.example.com/graphql", "{ company { id } }");

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.example.com/graphql");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("sends operation and variables in the body", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: {} }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const vars = { interviewTemplateId: "tmpl-42" };
    await executeGraphQL("https://api.example.com/graphql", GRAPHQL_QUERY, vars);

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string) as { query: string; variables: unknown };
    expect(body.query).toBe(GRAPHQL_QUERY);
    expect((body.variables as Record<string, unknown>)["interviewTemplateId"]).toBe("tmpl-42");
  });

  it("merges custom headers with Content-Type", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: {} }),
    });
    vi.stubGlobal("fetch", mockFetch);

    await executeGraphQL(
      "https://api.example.com/graphql",
      "{ user { id } }",
      {},
      { Authorization: "Bearer token123" },
    );

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const hdrs = init.headers as Record<string, string>;
    expect(hdrs["Authorization"]).toBe("Bearer token123");
    expect(hdrs["Content-Type"]).toBe("application/json");
  });

  it("returns parsed GraphQL response", async () => {
    const payload = { data: { company: { id: "c1", name: "Acme" } } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    }));

    const result = await executeGraphQL("https://api.example.com/graphql", "{ company { id } }");
    expect(result).toEqual(payload);
  });

  it("throws on non-2xx HTTP status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
    }));

    await expect(
      executeGraphQL("https://api.example.com/graphql", "{ company { id } }"),
    ).rejects.toThrow("401");
  });

  it("returns errors array from GraphQL response", async () => {
    const payload = { data: null, errors: [{ message: "Not found" }] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    }));

    const result = await executeGraphQL("https://api.example.com/graphql", "{ company { id } }");
    expect(result.errors).toHaveLength(1);
    expect(result.errors![0].message).toBe("Not found");
  });

  it("defaults variables to empty object when not provided", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: {} }),
    });
    vi.stubGlobal("fetch", mockFetch);

    await executeGraphQL("https://api.example.com/graphql", "{ company { id } }");

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string) as { variables: unknown };
    expect(body.variables).toEqual({});
  });
});
