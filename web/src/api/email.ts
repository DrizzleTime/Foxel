import request from './client';

export interface EmailTestPayload {
  to: string;
  subject: string;
  template?: string;
  context?: Record<string, unknown>;
}

export async function sendTestEmail(payload: EmailTestPayload) {
  return request<{ task_id: string }>('/email/test', {
    method: 'POST',
    json: {
      template: 'test',
      context: {},
      ...payload,
    },
  });
}

export async function listEmailTemplates() {
  return request<{ templates: string[] }>('/email/templates');
}

export async function getEmailTemplate(name: string) {
  return request<{ name: string; content: string }>(`/email/templates/${encodeURIComponent(name)}`);
}

export async function updateEmailTemplate(name: string, content: string) {
  return request(`/email/templates/${encodeURIComponent(name)}`, {
    method: 'POST',
    json: { content },
  });
}

export async function previewEmailTemplate(name: string, context: Record<string, unknown>) {
  return request<{ html: string }>(`/email/templates/${encodeURIComponent(name)}/preview`, {
    method: 'POST',
    json: { context },
  });
}
