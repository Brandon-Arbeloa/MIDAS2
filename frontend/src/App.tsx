import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Box } from '@mui/material'
import { Helmet } from 'react-helmet-async'

import Layout from '@/components/Layout/Layout'
import ProtectedRoute from '@/components/Auth/ProtectedRoute'
import { useAuth } from '@/contexts/AuthContext'

// Pages
import LoginPage from '@/pages/Auth/LoginPage'
import HomePage from '@/pages/Home/HomePage'
import ChatPage from '@/pages/Chat/ChatPage'
import DocumentsPage from '@/pages/Documents/DocumentsPage'
import DashboardsPage from '@/pages/Dashboards/DashboardsPage'
import DashboardViewPage from '@/pages/Dashboards/DashboardViewPage'
import TasksPage from '@/pages/Tasks/TasksPage'
import ProfilePage from '@/pages/Profile/ProfilePage'
import NotFoundPage from '@/pages/NotFound/NotFoundPage'
import LoadingPage from '@/pages/Loading/LoadingPage'

const App: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return <LoadingPage />
  }

  return (
    <>
      <Helmet>
        <title>MIDAS - Intelligence & Data Analysis</title>
        <meta name="description" content="Modular Intelligence & Data Analysis System - Production scalable platform" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Helmet>

      <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <Routes>
          {/* Public routes */}
          <Route 
            path="/login" 
            element={
              !isAuthenticated ? <LoginPage /> : <Navigate to="/" replace />
            } 
          />

          {/* Protected routes */}
          <Route path="/" element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }>
            <Route index element={<HomePage />} />
            
            <Route path="chat" element={<ChatPage />} />
            <Route path="chat/:sessionId" element={<ChatPage />} />
            
            <Route path="documents" element={<DocumentsPage />} />
            
            <Route path="dashboards" element={<DashboardsPage />} />
            <Route path="dashboards/:dashboardId" element={<DashboardViewPage />} />
            
            <Route path="tasks" element={<TasksPage />} />
            
            <Route path="profile" element={<ProfilePage />} />
          </Route>

          {/* 404 route */}
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Box>
    </>
  )
}

export default App