import React, { createContext, useContext, useEffect, useState, ReactNode, useRef } from 'react'
import { io, Socket } from 'socket.io-client'
import { useAuth } from './AuthContext'
import toast from 'react-hot-toast'

interface WebSocketContextType {
  socket: Socket | null
  isConnected: boolean
  sendMessage: (type: string, data: any) => void
  subscribeToTaskUpdates: (callback: (data: any) => void) => () => void
  subscribeToChatUpdates: (callback: (data: any) => void) => () => void
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined)

interface WebSocketProviderProps {
  children: ReactNode
}

export const WebSocketProvider: React.FC<WebSocketProviderProps> = ({ children }) => {
  const [socket, setSocket] = useState<Socket | null>(null)
  const [isConnected, setIsConnected] = useState<boolean>(false)
  const { isAuthenticated, user } = useAuth()
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const taskUpdateCallbacksRef = useRef<Set<(data: any) => void>>(new Set())
  const chatUpdateCallbacksRef = useRef<Set<(data: any) => void>>(new Set())

  useEffect(() => {
    if (isAuthenticated && user) {
      connectWebSocket()
    } else {
      disconnectWebSocket()
    }

    return () => {
      disconnectWebSocket()
    }
  }, [isAuthenticated, user])

  const connectWebSocket = () => {
    if (socket?.connected) {
      return
    }

    const wsUrl = process.env.NODE_ENV === 'production' 
      ? `wss://${window.location.host}`
      : 'ws://localhost:8000'

    const newSocket = io(wsUrl, {
      path: '/ws/socket.io/',
      transports: ['websocket', 'polling'],
      timeout: 20000,
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      query: {
        client_id: user?.username || 'anonymous',
      }
    })

    // Connection event handlers
    newSocket.on('connect', () => {
      console.log('WebSocket connected')
      setIsConnected(true)
      
      // Clear any pending reconnection attempts
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
    })

    newSocket.on('disconnect', (reason) => {
      console.log('WebSocket disconnected:', reason)
      setIsConnected(false)
      
      // Attempt to reconnect if it wasn't a manual disconnect
      if (reason !== 'io client disconnect' && isAuthenticated) {
        attemptReconnect()
      }
    })

    newSocket.on('connect_error', (error) => {
      console.error('WebSocket connection error:', error)
      setIsConnected(false)
      attemptReconnect()
    })

    // Message handlers
    newSocket.on('pong', () => {
      // Handle pong response for keep-alive
    })

    newSocket.on('chat_chunk', (data) => {
      // Handle streaming chat responses
      chatUpdateCallbacksRef.current.forEach(callback => callback({
        type: 'chat_chunk',
        ...data
      }))
    })

    newSocket.on('chat_complete', (data) => {
      // Handle chat completion
      chatUpdateCallbacksRef.current.forEach(callback => callback({
        type: 'chat_complete',
        ...data
      }))
    })

    newSocket.on('task_status', (data) => {
      // Handle task status updates
      taskUpdateCallbacksRef.current.forEach(callback => callback({
        type: 'task_status',
        ...data
      }))
    })

    newSocket.on('error', (error) => {
      console.error('WebSocket error:', error)
      toast.error('Connection error occurred')
    })

    // Keep-alive ping
    const pingInterval = setInterval(() => {
      if (newSocket.connected) {
        newSocket.emit('ping')
      }
    }, 30000) // Ping every 30 seconds

    newSocket.on('disconnect', () => {
      clearInterval(pingInterval)
    })

    setSocket(newSocket)
  }

  const disconnectWebSocket = () => {
    if (socket) {
      socket.disconnect()
      setSocket(null)
      setIsConnected(false)
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
  }

  const attemptReconnect = () => {
    if (reconnectTimeoutRef.current) {
      return // Already attempting to reconnect
    }

    reconnectTimeoutRef.current = setTimeout(() => {
      if (isAuthenticated && user) {
        console.log('Attempting WebSocket reconnection...')
        connectWebSocket()
      }
      reconnectTimeoutRef.current = null
    }, 5000) // Wait 5 seconds before reconnecting
  }

  const sendMessage = (type: string, data: any) => {
    if (socket && isConnected) {
      socket.emit('message', {
        type,
        ...data,
        timestamp: new Date().toISOString()
      })
    } else {
      console.warn('WebSocket not connected, message not sent:', { type, data })
    }
  }

  const subscribeToTaskUpdates = (callback: (data: any) => void) => {
    taskUpdateCallbacksRef.current.add(callback)
    
    // Return unsubscribe function
    return () => {
      taskUpdateCallbacksRef.current.delete(callback)
    }
  }

  const subscribeToChatUpdates = (callback: (data: any) => void) => {
    chatUpdateCallbacksRef.current.add(callback)
    
    // Return unsubscribe function
    return () => {
      chatUpdateCallbacksRef.current.delete(callback)
    }
  }

  const contextValue: WebSocketContextType = {
    socket,
    isConnected,
    sendMessage,
    subscribeToTaskUpdates,
    subscribeToChatUpdates
  }

  return (
    <WebSocketContext.Provider value={contextValue}>
      {children}
    </WebSocketContext.Provider>
  )
}

export const useWebSocket = (): WebSocketContextType => {
  const context = useContext(WebSocketContext)
  if (context === undefined) {
    throw new Error('useWebSocket must be used within a WebSocketProvider')
  }
  return context
}