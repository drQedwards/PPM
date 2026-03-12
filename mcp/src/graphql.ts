/**
 * graphql.ts — GraphQL execution helper for the PMLL Memory MCP Server.
 *
 * Provides:
 *   1. Pre-built GraphQL operation documents (`GRAPHQL_QUERY`, `GRAPHQL_MUTATION`)
 *      that define the full query/mutation API surface.
 *   2. `executeGraphQL()` — a lightweight fetch-based executor that POSTs
 *      an operation to a GraphQL endpoint and returns the parsed response.
 *
 * The pre-built operations cover the complete API surface:
 *   Query  — interviewTemplate, company, companyTestSession, roles, tasks, etc.
 *   Mutation — CRUD for interview templates, test sessions, roles, tasks, etc.
 *
 * **Note on selection sets:** The pre-built operations use empty selection
 * sets (`{ }`) as placeholders.  These serve as canonical templates that
 * document the available fields and their required variable signatures.
 * Agents should supply a custom `operation` string with the fields they
 * actually need when executing against a real endpoint.
 *
 * **Note on required variables:** All variables in the pre-built operations
 * are declared as required (`!`), matching the API specification.  The
 * `GRAPHQL_DEFAULT_VARIABLES` constant provides an all-null baseline; callers
 * must override every variable that the server treats as non-nullable before
 * executing the operation.
 *
 * These constants are available for agents/tools that need a canonical
 * reference to the full operation shape, while `executeGraphQL` is used
 * by the `graphql` MCP tool to execute arbitrary or pre-built operations.
 */

// ---------------------------------------------------------------------------
// Pre-built operation documents
// ---------------------------------------------------------------------------

/**
 * Canonical Query operation document.
 *
 * Covers every top-level query field in the API.  Variables are typed so
 * callers can supply a subset and leave the rest undefined/null.
 *
 * Selection sets are intentionally empty (`{ }`) — this document is a
 * template/reference.  Provide a custom `operation` string with real
 * field selections when executing against a live endpoint.
 */
export const GRAPHQL_QUERY = `query Query($interviewTemplateId: ID!, $first: Int!, $offset: Int!, $frameworksFirst2: Int!, $atsCompanyTestSessionsId: String!, $idType: AtsIdType!, $companyTestSessionId: ID!, $companyTestId: ID!, $standardizedTestSessionId: ID!, $key: ID!, $companyTestId2: ID!, $companyTestsFirst2: Int!, $certificationTestsFirst2: Int!, $standardizedTestId: ID!, $liveInterviewId: ID!, $type: AccessType!, $accessQueries: [AccessQueryInput!]!, $taskSetsFirst2: Int!, $testLabelsFirst2: Int!, $aiInterviewersFirst2: Int!, $llmModelCategoriesFirst2: Int!, $taskLevelId: ID!, $taskId: ID!, $name: String!) {
  interviewTemplate(interviewTemplateId: $interviewTemplateId) {
    
  }
  interviewTemplates(first: $first, offset: $offset) {
    
  }
  company {
    
  }
  companies {
    
  }
  servicePlans {
    
  }
  frameworks(first: $frameworksFirst2) {
    
  }
  atsCompanyTestSessions(id: $atsCompanyTestSessionsId, idType: $idType) {
    
  }
  companyTestSession(id: $companyTestSessionId) {
    
  }
  companyTestSessions(companyTestId: $companyTestId) {
    
  }
  standardizedTestSession(id: $standardizedTestSessionId) {
    
  }
  companyRoles {
    
  }
  systemRoles {
    
  }
  role(key: $key) {
    
  }
  companyTest(id: $companyTestId2) {
    
  }
  companyTests(first: $companyTestsFirst2) {
    
  }
  certificationTests(first: $certificationTestsFirst2) {
    
  }
  standardizedTest(id: $standardizedTestId) {
    
  }
  liveInterview(liveInterviewId: $liveInterviewId) {
    
  }
  liveInterviews {
    
  }
  hasAccess(type: $type)
  hasAccessList(accessQueries: $accessQueries) {
    
  }
  taskSets(first: $taskSetsFirst2) {
    
  }
  testLabels(first: $testLabelsFirst2) {
    
  }
  user {
    
  }
  aiInterviewers(first: $aiInterviewersFirst2) {
    
  }
  llmModelCategories(first: $llmModelCategoriesFirst2) {
    
  }
  taskLevel(taskLevelId: $taskLevelId) {
    
  }
  task(id: $taskId) {
    
  }
  codesignalCreatedTasks(name: $name) {
    
  }
}`;

/**
 * Canonical Mutation operation document.
 *
 * Covers every top-level mutation field in the API.  Variables are typed
 * and namespaced to avoid conflicts when multiple mutations share the same
 * logical parameter name.
 *
 * Selection sets are intentionally empty (`{ }`) — this document is a
 * template/reference.  Provide a custom `operation` string with real
 * field selections when executing against a live endpoint.
 */
export const GRAPHQL_MUTATION = `mutation Mutation($deleteInterviewTemplateInterviewTemplateId2: ID!, $interviewTemplateFields: CreateInterviewTemplateInput!, $editInterviewTemplateInterviewTemplateId2: ID!, $editInterviewTemplateInterviewTemplateFields2: EditInterviewTemplateInput!, $companyId: ID!, $lockdownFrameworkEnabled: Boolean!, $editCompanyPlanSettingsCompanyId2: ID!, $planSettings: CompanyPlanSettingsInput!, $appendCompanyTestSessionVerificationNoteId: ID!, $note: String!, $sessionFields: TestSessionInput!, $deleteCompanyTestSessionId: ID!, $editCompanyTestSessionDurationId: ID!, $customDuration: Float!, $editCompanyTestSessionExpirationId: ID!, $expirationDate: Timestamp!, $setCompanyTestSessionRemindersId: ID!, $reminders: [EmailReminder!]!, $resendCompanyTestSessionId: ID!, $reactivateCompanyTestSessionId: ID!, $gradeCompanyTestResultId: ID!, $gradeCompanyTestResultTaskId2: ID!, $score: Int!, $markCompanyTestResultAsGradedId: ID!, $archiveCompanyTestSessionId: ID!, $unarchiveCompanyTestSessionId: ID!, $saveRoleKey2: ID!, $title: String!, $permissions: [String!]!, $createCompanyRoleTitle2: String!, $createCompanyRolePermissions2: [String!]!, $editCompanyRoleKey2: ID!, $editCompanyRoleTitle2: String!, $editCompanyRolePermissions2: [String!]!, $deleteRoleKey2: ID!, $testFields: CreateCompanyTestInput!, $createCompanyTestFromFrameworkTestFields2: CreateCompanyTestFromFrameworkInput!, $editCompanyTestId: ID!, $editCompanyTestTestFields2: EditCompanyTestInput!, $duplicateCompanyTestId: ID!, $duplicateCompanyTestTestFields2: EditCompanyTestInput!, $editLiveInterviewId: ID!, $interviewFields: LiveInterviewInput!, $deleteLiveInterviewId: ID!, $editTaskSetsInput: EditTaskSetsInput!, $removeTaskFromSetsEditTaskSetsInput2: EditTaskSetsInput!, $setTaskInitialSourceId: ID!, $language: LanguageName!, $source: String!, $unsetTaskInitialSourceId: ID!, $unsetTaskInitialSourceLanguage2: LanguageName!, $taskFields: CreateCodeReviewTaskInput!, $editCodeReviewTaskId: ID!, $editCodeReviewTaskTaskFields2: EditCodeReviewTaskInput!, $createDatabaseTaskTaskFields2: CreateDatabaseTaskInput!, $editDatabaseTaskId: ID!, $editDatabaseTaskTaskFields2: EditDatabaseTaskInput!, $createFreeCodingTaskTaskFields2: CreateFreeCodingTaskInput!, $editFreeCodingTaskId: ID!, $editFreeCodingTaskTaskFields2: EditStandardTaskInput!, $updateFrontendTaskId: ID!, $patch: UpdateFrontendTaskInput!, $createQuizTaskTaskFields2: CreateQuizInput!, $editQuizTaskId: ID!, $editQuizTaskTaskFields2: EditQuizInput!, $createStandardTaskTaskFields2: CreateStandardTaskInput!, $editStandardTaskId: ID!, $editStandardTaskTaskFields2: EditStandardTaskInput!) {
  deleteInterviewTemplate(interviewTemplateId: $deleteInterviewTemplateInterviewTemplateId2)
  createInterviewTemplate(interviewTemplateFields: $interviewTemplateFields) {
    
  }
  editInterviewTemplate(interviewTemplateId: $editInterviewTemplateInterviewTemplateId2, interviewTemplateFields: $editInterviewTemplateInterviewTemplateFields2) {
    
  }
  updateLockdownFrameworkEnabled(companyId: $companyId, lockdownFrameworkEnabled: $lockdownFrameworkEnabled) {
    
  }
  editCompanyPlanSettings(companyId: $editCompanyPlanSettingsCompanyId2, planSettings: $planSettings) {
    
  }
  appendCompanyTestSessionVerificationNote(id: $appendCompanyTestSessionVerificationNoteId, note: $note) {
    
  }
  createCompanyTestSession(sessionFields: $sessionFields) {
    
  }
  deleteCompanyTestSession(id: $deleteCompanyTestSessionId)
  editCompanyTestSessionDuration(id: $editCompanyTestSessionDurationId, customDuration: $customDuration) {
    
  }
  editCompanyTestSessionExpiration(id: $editCompanyTestSessionExpirationId, expirationDate: $expirationDate) {
    
  }
  setCompanyTestSessionReminders(id: $setCompanyTestSessionRemindersId, reminders: $reminders) {
    
  }
  resendCompanyTestSession(id: $resendCompanyTestSessionId) {
    
  }
  reactivateCompanyTestSession(id: $reactivateCompanyTestSessionId) {
    
  }
  gradeCompanyTestResult(id: $gradeCompanyTestResultId, taskId: $gradeCompanyTestResultTaskId2, score: $score) {
    
  }
  markCompanyTestResultAsGraded(id: $markCompanyTestResultAsGradedId) {
    
  }
  archiveCompanyTestSession(id: $archiveCompanyTestSessionId) {
    
  }
  unarchiveCompanyTestSession(id: $unarchiveCompanyTestSessionId) {
    
  }
  saveRole(key: $saveRoleKey2, title: $title, permissions: $permissions) {
    
  }
  createCompanyRole(title: $createCompanyRoleTitle2, permissions: $createCompanyRolePermissions2) {
    
  }
  editCompanyRole(key: $editCompanyRoleKey2, title: $editCompanyRoleTitle2, permissions: $editCompanyRolePermissions2) {
    
  }
  deleteRole(key: $deleteRoleKey2)
  createCompanyTest(testFields: $testFields) {
    
  }
  createCompanyTestFromFramework(testFields: $createCompanyTestFromFrameworkTestFields2) {
    
  }
  editCompanyTest(id: $editCompanyTestId, testFields: $editCompanyTestTestFields2) {
    
  }
  duplicateCompanyTest(id: $duplicateCompanyTestId, testFields: $duplicateCompanyTestTestFields2) {
    
  }
  createLiveInterview {
    
  }
  editLiveInterview(id: $editLiveInterviewId, interviewFields: $interviewFields) {
    
  }
  deleteLiveInterview(id: $deleteLiveInterviewId)
  addTaskToSets(editTaskSetsInput: $editTaskSetsInput) {
    
  }
  removeTaskFromSets(editTaskSetsInput: $removeTaskFromSetsEditTaskSetsInput2) {
    
  }
  setTaskInitialSource(id: $setTaskInitialSourceId, language: $language, source: $source) {
    
  }
  unsetTaskInitialSource(id: $unsetTaskInitialSourceId, language: $unsetTaskInitialSourceLanguage2) {
    
  }
  createCodeReviewTask(taskFields: $taskFields) {
    
  }
  editCodeReviewTask(id: $editCodeReviewTaskId, taskFields: $editCodeReviewTaskTaskFields2) {
    
  }
  createDatabaseTask(taskFields: $createDatabaseTaskTaskFields2) {
    
  }
  editDatabaseTask(id: $editDatabaseTaskId, taskFields: $editDatabaseTaskTaskFields2) {
    
  }
  createFreeCodingTask(taskFields: $createFreeCodingTaskTaskFields2) {
    
  }
  editFreeCodingTask(id: $editFreeCodingTaskId, taskFields: $editFreeCodingTaskTaskFields2) {
    
  }
  updateFrontendTask(id: $updateFrontendTaskId, patch: $patch) {
    
  }
  createQuizTask(taskFields: $createQuizTaskTaskFields2) {
    
  }
  editQuizTask(id: $editQuizTaskId, taskFields: $editQuizTaskTaskFields2) {
    
  }
  createStandardTask(taskFields: $createStandardTaskTaskFields2) {
    
  }
  editStandardTask(id: $editStandardTaskId, taskFields: $editStandardTaskTaskFields2) {
    
  }
}`;

/**
 * Default variables object for the pre-built operations.
 *
 * All values are null; callers supply only the variables relevant to their
 * specific sub-operation.
 */
export const GRAPHQL_DEFAULT_VARIABLES: Record<string, null> = {
  first: null,
  offset: null,
  appendCompanyTestSessionVerificationNoteId: null,
  note: null,
  interviewTemplateId: null,
  frameworksFirst2: null,
  atsCompanyTestSessionsId: null,
  idType: null,
  companyTestSessionId: null,
  companyTestId: null,
  standardizedTestSessionId: null,
  key: null,
  companyTestId2: null,
  companyTestsFirst2: null,
  certificationTestsFirst2: null,
  standardizedTestId: null,
  liveInterviewId: null,
  type: null,
  accessQueries: null,
  taskSetsFirst2: null,
  testLabelsFirst2: null,
  aiInterviewersFirst2: null,
  llmModelCategoriesFirst2: null,
  taskLevelId: null,
  taskId: null,
  name: null,
  deleteInterviewTemplateInterviewTemplateId2: null,
  interviewTemplateFields: null,
  editInterviewTemplateInterviewTemplateId2: null,
  editInterviewTemplateInterviewTemplateFields2: null,
  companyId: null,
  lockdownFrameworkEnabled: null,
  editCompanyPlanSettingsCompanyId2: null,
  planSettings: null,
  sessionFields: null,
  deleteCompanyTestSessionId: null,
  editCompanyTestSessionDurationId: null,
  customDuration: null,
  editCompanyTestSessionExpirationId: null,
  expirationDate: null,
  setCompanyTestSessionRemindersId: null,
  reminders: null,
  resendCompanyTestSessionId: null,
  reactivateCompanyTestSessionId: null,
  gradeCompanyTestResultId: null,
  gradeCompanyTestResultTaskId2: null,
  score: null,
  markCompanyTestResultAsGradedId: null,
  archiveCompanyTestSessionId: null,
  unarchiveCompanyTestSessionId: null,
  saveRoleKey2: null,
  title: null,
  permissions: null,
  createCompanyRoleTitle2: null,
  createCompanyRolePermissions2: null,
  editCompanyRoleKey2: null,
  editCompanyRoleTitle2: null,
  editCompanyRolePermissions2: null,
  deleteRoleKey2: null,
  testFields: null,
  createCompanyTestFromFrameworkTestFields2: null,
  editCompanyTestId: null,
  editCompanyTestTestFields2: null,
  duplicateCompanyTestId: null,
  duplicateCompanyTestTestFields2: null,
  editLiveInterviewId: null,
  interviewFields: null,
  deleteLiveInterviewId: null,
  editTaskSetsInput: null,
  removeTaskFromSetsEditTaskSetsInput2: null,
  setTaskInitialSourceId: null,
  language: null,
  source: null,
  unsetTaskInitialSourceId: null,
  unsetTaskInitialSourceLanguage2: null,
  taskFields: null,
  editCodeReviewTaskId: null,
  editCodeReviewTaskTaskFields2: null,
  createDatabaseTaskTaskFields2: null,
  editDatabaseTaskId: null,
  editDatabaseTaskTaskFields2: null,
  createFreeCodingTaskTaskFields2: null,
  editFreeCodingTaskId: null,
  editFreeCodingTaskTaskFields2: null,
  updateFrontendTaskId: null,
  patch: null,
  createQuizTaskTaskFields2: null,
  editQuizTaskId: null,
  editQuizTaskTaskFields2: null,
  createStandardTaskTaskFields2: null,
  editStandardTaskId: null,
  editStandardTaskTaskFields2: null,
};

// ---------------------------------------------------------------------------
// GraphQL executor
// ---------------------------------------------------------------------------

/** Shape of a standard GraphQL HTTP response. */
export interface GraphQLResponse {
  data?: Record<string, unknown> | null;
  errors?: Array<{ message: string; locations?: unknown; path?: unknown }>;
}

/**
 * Execute a GraphQL operation against `endpoint` via HTTP POST.
 *
 * Uses the built-in `fetch` API (Node.js 18+).  Returns the parsed JSON
 * response body.  Throws on HTTP-level errors (non-2xx status).
 *
 * @param endpoint   Full URL of the GraphQL endpoint.
 * @param operation  GraphQL operation document (query or mutation string).
 * @param variables  Variables to pass with the operation.
 * @param headers    Additional HTTP headers (e.g. Authorization).
 */
export async function executeGraphQL(
  endpoint: string,
  operation: string,
  variables: Record<string, unknown> = {},
  headers: Record<string, string> = {},
): Promise<GraphQLResponse> {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: JSON.stringify({ query: operation, variables }),
  });

  if (!response.ok) {
    throw new Error(`GraphQL HTTP error: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<GraphQLResponse>;
}
