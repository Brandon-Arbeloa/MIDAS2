import axios, { AxiosResponse } from 'axios'
import { AuthResponse, User, LoginRequest } from '@/types/auth'
import { apiClient } from './apiClient'

export class AuthService {
  private baseURL = '/api/v1'

  async login(username: string, password: string): Promise<AuthResponse> {
    const response: AxiosResponse<AuthResponse> = await apiClient.post(
      `${this.baseURL}/auth/login`,
      { username, password }
    )
    return response.data
  }

  async windowsLogin(): Promise<AuthResponse> {
    const response: AxiosResponse<AuthResponse> = await apiClient.get(
      '/api/auth/windows'
    )
    return response.data
  }

  async register(userData: {
    username: string
    email: string
    password: string
    display_name?: string
  }): Promise<AuthResponse> {
    const response: AxiosResponse<AuthResponse> = await apiClient.post(
      `${this.baseURL}/auth/register`,
      userData
    )
    return response.data
  }

  async refreshToken(refresh_token: string): Promise<AuthResponse> {
    const response: AxiosResponse<AuthResponse> = await apiClient.post(
      `${this.baseURL}/auth/refresh`,
      { refresh_token }
    )
    return response.data
  }

  async getCurrentUser(): Promise<User> {
    const response: AxiosResponse<User> = await apiClient.get(
      `${this.baseURL}/auth/me`
    )
    return response.data
  }

  async updateProfile(userData: Partial<User>): Promise<User> {
    const response: AxiosResponse<User> = await apiClient.put(
      `${this.baseURL}/auth/profile`,
      userData
    )
    return response.data
  }

  async changePassword(oldPassword: string, newPassword: string): Promise<void> {
    await apiClient.post(`${this.baseURL}/auth/change-password`, {
      old_password: oldPassword,
      new_password: newPassword
    })
  }

  async logout(): Promise<void> {
    await apiClient.post(`${this.baseURL}/auth/logout`)
  }

  async requestPasswordReset(email: string): Promise<void> {
    await apiClient.post(`${this.baseURL}/auth/forgot-password`, { email })
  }

  async resetPassword(token: string, newPassword: string): Promise<void> {
    await apiClient.post(`${this.baseURL}/auth/reset-password`, {
      token,
      new_password: newPassword
    })
  }

  // Windows-specific authentication methods
  async checkWindowsAuth(): Promise<boolean> {
    try {
      await apiClient.get('/api/auth/windows/check')
      return true
    } catch (error) {
      return false
    }
  }

  async getWindowsUserInfo(): Promise<{ username: string; display_name: string }> {
    const response = await apiClient.get('/api/auth/windows/info')
    return response.data
  }
}

export const authService = new AuthService()