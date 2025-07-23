import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse, AxiosError } from 'axios'
import Cookies from 'js-cookie'
import toast from 'react-hot-toast'

// Create axios instance with default configuration
const apiClient: AxiosInstance = axios.create({
  baseURL: process.env.NODE_ENV === 'production' ? '/api' : 'http://localhost:8000',
  timeout: 30000, // 30 seconds
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Important for Windows authentication
})

// Request interceptor to add auth token
apiClient.interceptors.request.use(
  (config: AxiosRequestConfig): any => {
    const token = Cookies.get('access_token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }

    // Add Windows-specific headers
    if (navigator.userAgent.includes('Windows')) {
      config.headers = {
        ...config.headers,
        'X-Platform': 'Windows',
        'X-User-Agent': navigator.userAgent,
      }
    }

    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  }
)

// Response interceptor to handle errors and token refresh
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    return response
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }

    // Handle 401 errors (unauthorized)
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      try {
        // Try to refresh the token
        const refreshToken = Cookies.get('refresh_token')
        if (refreshToken) {
          const response = await axios.post('/api/v1/auth/refresh', {
            refresh_token: refreshToken
          })

          const { access_token, refresh_token: newRefreshToken } = response.data

          // Update tokens in cookies
          Cookies.set('access_token', access_token, { 
            expires: 7,
            secure: process.env.NODE_ENV === 'production',
            sameSite: 'lax'
          })

          if (newRefreshToken) {
            Cookies.set('refresh_token', newRefreshToken, { 
              expires: 30,
              secure: process.env.NODE_ENV === 'production',
              sameSite: 'lax'
            })
          }

          // Retry the original request with new token
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${access_token}`
          }

          return apiClient(originalRequest)
        }
      } catch (refreshError) {
        // Refresh failed, clear tokens and redirect to login
        Cookies.remove('access_token')
        Cookies.remove('refresh_token')
        
        // Only show toast if we're not already on the login page
        if (!window.location.pathname.includes('/login')) {
          toast.error('Session expired. Please log in again.')
          window.location.href = '/login'
        }
        
        return Promise.reject(refreshError)
      }
    }

    // Handle other error types
    if (error.response) {
      const { status, data } = error.response

      switch (status) {
        case 400:
          toast.error(data.detail || 'Bad request')
          break
        case 403:
          toast.error('Access forbidden')
          break
        case 404:
          toast.error('Resource not found')
          break
        case 422:
          // Validation errors
          if (data.detail && Array.isArray(data.detail)) {
            data.detail.forEach((err: any) => {
              toast.error(`${err.loc?.join(' → ') || 'Field'}: ${err.msg}`)
            })
          } else {
            toast.error(data.detail || 'Validation error')
          }
          break
        case 429:
          toast.error('Too many requests. Please try again later.')
          break
        case 500:
          toast.error('Internal server error. Please try again.')
          break
        case 502:
        case 503:
        case 504:
          toast.error('Service unavailable. Please try again later.')
          break
        default:
          toast.error(data.detail || 'An unexpected error occurred')
      }
    } else if (error.request) {
      // Network error
      toast.error('Network error. Please check your connection.')
    } else {
      // Other error
      toast.error('An unexpected error occurred')
    }

    return Promise.reject(error)
  }
)

// File upload helper
export const uploadFile = async (
  file: File,
  endpoint: string,
  onProgress?: (progress: number) => void
): Promise<any> => {
  const formData = new FormData()
  formData.append('file', file)

  const config: AxiosRequestConfig = {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const progress = (progressEvent.loaded / progressEvent.total) * 100
        onProgress(Math.round(progress))
      }
    },
  }

  const response = await apiClient.post(endpoint, formData, config)
  return response.data
}

// Download file helper
export const downloadFile = async (
  url: string,
  filename?: string
): Promise<void> => {
  const response = await apiClient.get(url, {
    responseType: 'blob',
  })

  const blob = new Blob([response.data])
  const downloadUrl = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = filename || 'download'
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(downloadUrl)
}

// Health check helper
export const healthCheck = async (): Promise<boolean> => {
  try {
    await apiClient.get('/api/health')
    return true
  } catch (error) {
    return false
  }
}

export { apiClient }
export default apiClient