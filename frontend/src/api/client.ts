const API_BASE_URL = '/api/v1';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function normalizeErrorData(errorData: unknown, fallbackStatusText: string) {
  if (!errorData || typeof errorData !== 'object') {
    return {
      code: 'UNKNOWN_ERROR',
      message: fallbackStatusText,
      details: undefined as unknown,
    };
  }

  const data = errorData as Record<string, unknown>;
  const detail = data.detail;
  const message =
    (typeof data.message === 'string' && data.message) ||
    (typeof detail === 'string' && detail) ||
    fallbackStatusText;

  let details: unknown = data.details;
  if (details === undefined && Array.isArray(detail)) {
    details = detail;
  }

  const code =
    (typeof data.code === 'string' && data.code) ||
    (typeof data.error === 'string' && data.error) ||
    'UNKNOWN_ERROR';

  return { code, message, details };
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const normalized = normalizeErrorData(errorData, response.statusText);
    throw new ApiError(
      response.status,
      normalized.code,
      normalized.message,
      normalized.details
    );
  }
  
  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }
  
  return response.json();
}

export const apiClient = {
  async get<T>(path: string, params?: Record<string, string>): Promise<T> {
    const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          url.searchParams.append(key, value);
        }
      });
    }
    
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    return handleResponse<T>(response);
  },
  
  async post<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    
    return handleResponse<T>(response);
  },
  
  async postForm<T>(path: string, formData: FormData): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      body: formData,
    });
    
    return handleResponse<T>(response);
  },
  
  async delete<T>(path: string): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      },
    });
    
    return handleResponse<T>(response);
  },
};
