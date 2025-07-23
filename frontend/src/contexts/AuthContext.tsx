import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import Cookies from 'js-cookie'
import { authService, AuthService } from '@/services/authService'
import { User } from '@/types/auth'

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  loginWithWindows: () => Promise<void>
  logout: () => void
  refreshToken: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

interface AuthProviderProps {
  children: ReactNode
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null)
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false)
  const [isLoading, setIsLoading] = useState<boolean>(true)

  // Initialize auth state
  useEffect(() => {
    initializeAuth()
  }, [])

  const initializeAuth = async () => {
    try {
      const accessToken = Cookies.get('access_token')
      if (accessToken) {
        // Verify token and get user info
        const userInfo = await authService.getCurrentUser()
        setUser(userInfo)
        setIsAuthenticated(true)
      }
    } catch (error) {
      // Token invalid or expired, try to refresh
      try {
        await refreshToken()
      } catch (refreshError) {
        // Refresh failed, user needs to log in again
        logout()
      }
    } finally {
      setIsLoading(false)
    }
  }

  const login = async (username: string, password: string): Promise<void> => {
    try {
      setIsLoading(true)
      const response = await authService.login(username, password)
      
      // Store tokens in cookies (Windows-compatible)
      Cookies.set('access_token', response.access_token, { 
        expires: 7, // 7 days
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax'
      })
      Cookies.set('refresh_token', response.refresh_token, { 
        expires: 30, // 30 days
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax'
      })

      setUser(response.user)
      setIsAuthenticated(true)
    } catch (error) {
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const loginWithWindows = async (): Promise<void> => {
    try {
      setIsLoading(true)
      const response = await authService.windowsLogin()
      
      // Store tokens in cookies
      Cookies.set('access_token', response.access_token, { 
        expires: 7,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax'
      })
      Cookies.set('refresh_token', response.refresh_token, { 
        expires: 30,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax'
      })

      setUser(response.user)
      setIsAuthenticated(true)
    } catch (error) {
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const logout = (): void => {
    // Clear tokens from cookies
    Cookies.remove('access_token')
    Cookies.remove('refresh_token')
    
    // Clear user state
    setUser(null)
    setIsAuthenticated(false)
    
    // Clear any cached data
    localStorage.removeItem('user_preferences')
    sessionStorage.clear()
  }

  const refreshToken = async (): Promise<void> => {
    try {
      const refreshToken = Cookies.get('refresh_token')
      if (!refreshToken) {
        throw new Error('No refresh token available')
      }

      const response = await authService.refreshToken(refreshToken)
      
      // Update tokens
      Cookies.set('access_token', response.access_token, { 
        expires: 7,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax'
      })
      
      if (response.refresh_token) {
        Cookies.set('refresh_token', response.refresh_token, { 
          expires: 30,
          secure: process.env.NODE_ENV === 'production',
          sameSite: 'lax'
        })
      }

      // Update user info if provided
      if (response.user) {
        setUser(response.user)
        setIsAuthenticated(true)
      }
    } catch (error) {
      // Refresh failed, logout user
      logout()
      throw error
    }
  }

  // Set up token refresh interval
  useEffect(() => {
    if (isAuthenticated) {
      // Refresh token every 25 minutes (tokens expire in 30 minutes)
      const interval = setInterval(() => {
        refreshToken().catch(() => {
          // Refresh failed, user will be logged out
        })
      }, 25 * 60 * 1000)

      return () => clearInterval(interval)
    }
  }, [isAuthenticated])

  const contextValue: AuthContextType = {
    user,
    isAuthenticated,
    isLoading,
    login,
    loginWithWindows,
    logout,
    refreshToken
  }

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}