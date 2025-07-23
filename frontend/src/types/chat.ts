export interface ChatSession {
  id: string
  title?: string
  model_name: string
  temperature: number
  use_rag: boolean
  created_at: string
  updated_at: string
  message_count: number
  is_active: boolean
}

export interface ChatMessage {
  id: string
  content: string
  role: 'user' | 'assistant' | 'system'
  sources: string[]
  confidence_score?: number
  created_at: string
  token_count?: number
  processing_time?: number
  is_streaming?: boolean
  is_edited?: boolean
}

export interface CreateChatSessionRequest {
  title?: string
  model_name?: string
  temperature?: number
  use_rag?: boolean
}

export interface SendMessageRequest {
  content: string
  session_id: string
}

export interface ChatStreamEvent {
  type: 'chunk' | 'complete' | 'error'
  content?: string
  message?: string
  message_id?: string
}

export interface ChatSettings {
  model_name: string
  temperature: number
  use_rag: boolean
  max_tokens?: number
  stream_response: boolean
}