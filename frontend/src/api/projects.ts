import { apiClient, API_BASE_URL } from './client';
import type {
  AnalyzeResponse,
  AnswerSubmissionItem,
  Assumption,
  BRDGenerateResponse,
  BRDVersion,
  ChatHistoryResponse,
  ChatMessage,
  ChatMessageRecord,
  ChatRequest,
  ChatResponse,
  CollaboratorResponse,
  CreateProjectResponse,
  HealthResponse,
  InvitationResponse,
  Project,
  ProjectDetailResponse,
  Question,
  Requirement,
  SourceDocument,
  SourceDocumentListResponse,
  SubmitAnswersResponse,
  UserProfileResponse,
  UserProfileUpdateRequest,
} from '../types';

export type {
  ChatHistoryResponse,
  ChatMessage,
  ChatMessageRecord,
  ChatRequest,
  ChatResponse,
  CollaboratorResponse,
  InvitationResponse,
  UserProfileResponse,
  UserProfileUpdateRequest,
};



/**
 * Check backend API operational health.
 */
export async function checkHealth(): Promise<HealthResponse> {
  const response = await apiClient.get<HealthResponse>('/health');
  return response.data;
}

/**
 * Fetch a list of recent projects.
 */
export async function getProjects(limit: number = 20): Promise<Project[]> {
  const response = await apiClient.get<Project[]>('/projects', {
    params: { limit },
  });
  return response.data;
}

/**
 * Fetch detailed metrics for a specific project.
 */
export async function getProjectDetail(projectId: string): Promise<ProjectDetailResponse> {
  const response = await apiClient.get<ProjectDetailResponse>(`/projects/${projectId}`);
  return response.data;
}

/**
 * Initialize a new BRD project in DRAFT state.
 */
export async function createProject(
  title: string | undefined,
  idea: string
): Promise<CreateProjectResponse> {
  const response = await apiClient.post<CreateProjectResponse>('/projects', {
    title: title && title.trim().length > 0 ? title.trim() : undefined,
    idea,
  });
  return response.data;
}

/**
 * Upload a source grounding document (PDF, DOCX, TXT) up to 10MB.
 */
export async function uploadSourceFile(
  projectId: string,
  file: File
): Promise<SourceDocument> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post<SourceDocument>(
    `/projects/${projectId}/sources`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );
  return response.data;
}

/**
 * Retrieve all parsed source documents for a project.
 */
export async function getSourceFiles(projectId: string): Promise<SourceDocument[]> {
  const response = await apiClient.get<SourceDocumentListResponse>(
    `/projects/${projectId}/sources`
  );
  return response.data.items;
}

/**
 * Trigger AI Core Loop extraction and validation on the project.
 */
export async function analyzeProject(projectId: string): Promise<AnalyzeResponse> {
  const response = await apiClient.post<AnalyzeResponse>(`/projects/${projectId}/analyze`);
  return response.data;
}

/**
 * Retrieve open clarification questions generated for missing requirements.
 */
export async function getQuestions(projectId: string): Promise<Question[]> {
  const response = await apiClient.get<Question[]>(`/projects/${projectId}/questions`);
  return response.data;
}

/**
 * Submit answers to clarification questions and trigger iterative re-analysis.
 */
export async function submitAnswers(
  projectId: string,
  answers: AnswerSubmissionItem[]
): Promise<SubmitAnswersResponse> {
  const response = await apiClient.post<SubmitAnswersResponse>(
    `/projects/${projectId}/answers`,
    { answers }
  );
  return response.data;
}

/**
 * Retrieve all proposed or accepted explicit assumptions.
 */
export async function getAssumptions(projectId: string): Promise<Assumption[]> {
  const response = await apiClient.get<Assumption[]>(
    `/projects/${projectId}/assumptions`
  );
  return response.data;
}

/**
 * Accept or reject a proposed assumption.
 */
export async function decideAssumption(
  projectId: string,
  assumptionId: string,
  decision: 'accepted' | 'rejected'
): Promise<Assumption> {
  const response = await apiClient.post<Assumption>(
    `/projects/${projectId}/assumptions/${assumptionId}/decision`,
    { decision }
  );
  return response.data;
}

/**
 * Compile structured BRD JSON, run quality checks, and render DOCX.
 */
export async function generateBRD(projectId: string): Promise<BRDGenerateResponse> {
  const response = await apiClient.post<BRDGenerateResponse>(
    `/projects/${projectId}/generate`
  );
  return response.data;
}

/**
 * Retrieve the latest generated BRD version metadata and 7-section content.
 */
export async function getBRD(projectId: string): Promise<BRDVersion> {
  const response = await apiClient.get<BRDVersion>(`/projects/${projectId}/brd`);
  return response.data;
}

/**
 * Get the direct download URL for the rendered Word (.docx) document artifact.
 */
export function getBRDDownloadUrl(projectId: string): string {
  return `${API_BASE_URL}/projects/${projectId}/brd/download`;
}

/**
 * Download the generated DOCX document as a binary blob and trigger browser download.
 */
export async function downloadBRDDocx(projectId: string, filename?: string): Promise<void> {
  const response = await apiClient.get(`/projects/${projectId}/brd/download`, {
    responseType: 'blob',
  });

  const blobUrl = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement('a');
  link.href = blobUrl;
  link.setAttribute('download', filename || `BRD_${projectId}.docx`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(blobUrl);
}

/**
 * Recover a project from FAILED status back to previous valid state.
 */
export async function retryProject(projectId: string): Promise<Project> {
  const response = await apiClient.post<Project>(`/projects/${projectId}/retry`);
  return response.data;
}

/**
 * Retrieve all requirements captured for a project.
 */
export async function getRequirements(projectId: string): Promise<Requirement[]> {
  const response = await apiClient.get<Requirement[]>(`/projects/${projectId}/requirements`);
  return response.data;
}

/**
 * Send a conversational clarification message to the AI interviewer.
 */
export async function sendProjectChatMessage(
  projectId: string,
  message: string,
  history: ChatMessage[] = []
): Promise<ChatResponse> {
  const response = await apiClient.post<ChatResponse>(`/projects/${projectId}/chat`, {
    message,
    history,
  });
  return response.data;
}

/**
 * Fetch authenticated user profile metadata.
 */
export async function getUserProfile(): Promise<UserProfileResponse> {
  const response = await apiClient.get<UserProfileResponse>('/user/profile');
  return response.data;
}

/**
 * Update authenticated user profile (full name, role title, avatar).
 */
export async function updateUserProfile(
  data: UserProfileUpdateRequest
): Promise<UserProfileResponse> {
  const response = await apiClient.put<UserProfileResponse>('/user/profile', data);
  return response.data;
}

/**
 * List all team members collaborating on a project.
 */
export async function getCollaborators(projectId: string): Promise<CollaboratorResponse[]> {
  const response = await apiClient.get<CollaboratorResponse[]>(
    `/projects/${projectId}/collaborators`
  );
  return response.data;
}

/**
 * Enroll active authenticated user as a collaborator via share link.
 */
export async function joinProject(projectId: string): Promise<Project> {
  const response = await apiClient.post<Project>(`/projects/${projectId}/join`);
  return response.data;
}

/**
 * Remove a collaborator from a project (owner-only permission).
 */
export async function removeCollaborator(
  projectId: string,
  userId: string
): Promise<void> {
  await apiClient.delete(`/projects/${projectId}/collaborators/${userId}`);
}

/**
 * Retrieve persistent chronological chat history for a project.
 */
export async function getChatHistory(projectId: string): Promise<ChatMessageRecord[]> {
  const response = await apiClient.get<ChatHistoryResponse>(
    `/projects/${projectId}/chat/history`
  );
  return response.data.messages || [];
}

/**
 * Send an email invitation to collaborate on a project.
 */
export async function sendProjectInvitation(
  projectId: string,
  email: string,
  role: string = 'editor'
): Promise<InvitationResponse> {
  const response = await apiClient.post<InvitationResponse>(
    `/projects/${projectId}/invitations`,
    { email, role }
  );
  return response.data;
}

/**
 * Fetch persisted invitations sent for a project (owner-only endpoint).
 */
export async function getProjectInvitations(projectId: string): Promise<InvitationResponse[]> {
  const response = await apiClient.get<InvitationResponse[]>(
    `/projects/${projectId}/invitations`
  );
  return response.data || [];
}

/**
 * Fetch pending project invitations addressed to the active user's email.
 */
export async function getUserInvitations(): Promise<InvitationResponse[]> {
  const response = await apiClient.get<InvitationResponse[]>('/user/invitations');
  return response.data || [];
}

/**
 * Accept a project invitation and enroll as collaborator.
 */
export async function acceptInvitation(invitationId: string): Promise<Project> {
  const response = await apiClient.post<Project>(`/invitations/${invitationId}/accept`);
  return response.data;
}

