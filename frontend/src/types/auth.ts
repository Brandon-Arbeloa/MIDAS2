export interface User {
  id: number
  username: string
  email?: string
  display_name?: string
  avatar_url?: string
  is_active: boolean
  is_superuser: boolean
  windows_username?: string
  windows_domain?: string
  is_windows_authenticated: boolean
  preferences: Record<string, any>
  created_at: string
  updated_at: string
  last_login?: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
}

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
  display_name?: string
}

export interface TokenPayload {
  sub: string
  exp: number
  iat: number
  type: 'access' | 'refresh'
}

export interface WindowsAuthInfo {
  username: string
  display_name: string
  domain_user: string
}