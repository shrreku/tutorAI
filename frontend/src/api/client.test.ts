import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from './client'
import { clearAuth } from '../stores/authStore'

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('apiClient', () => {
  it('postPublic omits auth and byok headers', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))

    localStorage.setItem('auth_token', 'secret-token')
    localStorage.setItem('byok_api_key', 'byok-key')
    localStorage.setItem('byok_api_base_url', 'https://example.com/v1')

    await apiClient.postPublic('/auth/login', { email: 'user@example.com' })

    const call = fetchSpy.mock.calls[0]
    const options = call[1] as RequestInit
    const headers = options.headers as Record<string, string>

    expect(headers.Authorization).toBeUndefined()
    expect(headers['X-LLM-Api-Key']).toBeUndefined()
    expect(headers['X-LLM-Api-Base-Url']).toBeUndefined()
    expect(headers['Content-Type']).toBe('application/json')
  })

  it('postForm omits byok headers by default', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ job_id: '1' }), { status: 200 }))

    localStorage.setItem('auth_token', 'secret-token')
    localStorage.setItem('byok_api_key', 'byok-key')
    localStorage.setItem('byok_api_base_url', 'https://example.com/v1')

    const formData = new FormData()
    formData.append('topic', 'architecture')

    await apiClient.postForm('/ingest/upload', formData)

    const call = fetchSpy.mock.calls[0]
    const options = call[1] as RequestInit
    const headers = options.headers as Record<string, string>

    expect(headers.Authorization).toBe('Bearer secret-token')
    expect(headers['X-LLM-Api-Key']).toBeUndefined()
    expect(headers['X-LLM-Api-Base-Url']).toBeUndefined()
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('postForm includes byok headers when explicitly requested', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ job_id: '1' }), { status: 200 }))

    localStorage.setItem('auth_token', 'secret-token')
    localStorage.setItem('byok_api_key', 'byok-key')
    localStorage.setItem('byok_api_base_url', 'https://example.com/v1')

    const formData = new FormData()
    formData.append('topic', 'architecture')

    await apiClient.postForm('/ingest/upload', formData, { includeByok: true })

    const call = fetchSpy.mock.calls[0]
    const options = call[1] as RequestInit
    const headers = options.headers as Record<string, string>

    expect(headers.Authorization).toBe('Bearer secret-token')
    expect(headers['X-LLM-Api-Key']).toBe('byok-key')
    expect(headers['X-LLM-Api-Base-Url']).toBe('https://example.com/v1')
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('normalizes error payload into ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ code: 'BAD_INPUT', detail: 'Nope' }), {
        status: 400,
        statusText: 'Bad Request',
      }),
    )

    await expect(apiClient.post('/x', {})).rejects.toEqual(
      expect.objectContaining({
        status: 400,
        code: 'BAD_INPUT',
        message: 'Nope',
      }),
    )
  })

  it('clearAuth removes persisted byok credentials', () => {
    localStorage.setItem('auth_token', 'secret-token')
    localStorage.setItem('auth_user', JSON.stringify({ id: '1' }))
    localStorage.setItem('byok_api_key', 'byok-key')
    localStorage.setItem('byok_api_base_url', 'https://example.com/v1')

    clearAuth()

    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(localStorage.getItem('auth_user')).toBeNull()
    expect(localStorage.getItem('byok_api_key')).toBeNull()
    expect(localStorage.getItem('byok_api_base_url')).toBeNull()
  })
})
