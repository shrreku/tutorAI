const API_BASE_URL = '/api/v1';

type HeaderOptions = {
  includeAuth?: boolean;
  includeByok?: boolean;
  includeJsonContentType?: boolean;
};

// ---------------------------------------------------------------------------
// Auth header injection — reads JWT from localStorage
// ---------------------------------------------------------------------------
function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  try {
    const token = localStorage.getItem('auth_token');
    if (token) headers['Authorization'] = `Bearer ${token}`;
  } catch {
    // localStorage unavailable
  }
  return headers;
}

// ---------------------------------------------------------------------------
// BYOK header injection — reads from localStorage (never persisted server-side)
// ---------------------------------------------------------------------------
function getByokHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  try {
    const key = localStorage.getItem('byok_api_key');
    const baseUrl = localStorage.getItem('byok_api_base_url');
    if (key) headers['X-LLM-Api-Key'] = key;
    if (baseUrl) headers['X-LLM-Api-Base-Url'] = baseUrl;
  } catch {
    // localStorage unavailable (SSR, private mode, etc.)
  }
  return headers;
}

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

function buildHeaders(options: HeaderOptions = {}): Record<string, string> {
  const {
    includeAuth = true,
    includeByok = true,
    includeJsonContentType = true,
  } = options;

  return {
    ...(includeJsonContentType ? { 'Content-Type': 'application/json' } : {}),
    ...(includeAuth ? getAuthHeaders() : {}),
    ...(includeByok ? getByokHeaders() : {}),
  };
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
      headers: buildHeaders(),
    });
    
    return handleResponse<T>(response);
  },
  
  async post<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: buildHeaders(),
      body: body ? JSON.stringify(body) : undefined,
    });
    
    return handleResponse<T>(response);
  },

  async patch<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'PATCH',
      headers: buildHeaders(),
      body: body ? JSON.stringify(body) : undefined,
    });

    return handleResponse<T>(response);
  },
  
  async postForm<T>(path: string, formData: FormData): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: buildHeaders({ includeJsonContentType: false }),
      body: formData,
    });
    
    return handleResponse<T>(response);
  },
  
  async delete<T>(path: string): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'DELETE',
      headers: buildHeaders(),
    });
    
    return handleResponse<T>(response);
  },

  async postPublic<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: buildHeaders({ includeAuth: false, includeByok: false }),
      body: body ? JSON.stringify(body) : undefined,
    });

    return handleResponse<T>(response);
  },
};
