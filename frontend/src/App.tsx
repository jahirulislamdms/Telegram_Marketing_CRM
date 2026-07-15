import { Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import ProtectedRoute from './components/ProtectedRoute'
import Accounts from './pages/Accounts'
import Bots from './pages/Bots'
import Campaigns from './pages/Campaigns'
import Contacts from './pages/Contacts'
import Dashboard from './pages/Dashboard'
import GroupsChannels from './pages/GroupsChannels'
import Inbox from './pages/Inbox'
import Login from './pages/Login'
import Pipeline from './pages/Pipeline'
import Sender from './pages/Sender'
import Staff from './pages/Staff'
import Warmup from './pages/Warmup'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route
          path="/accounts"
          element={
            <ProtectedRoute roles={['admin', 'manager']}>
              <Accounts />
            </ProtectedRoute>
          }
        />
        <Route
          path="/warmup"
          element={
            <ProtectedRoute roles={['admin', 'manager']}>
              <Warmup />
            </ProtectedRoute>
          }
        />
        <Route path="/contacts" element={<Contacts />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route
          path="/groups"
          element={
            <ProtectedRoute roles={['admin', 'manager']}>
              <GroupsChannels />
            </ProtectedRoute>
          }
        />
        <Route
          path="/sender"
          element={
            <ProtectedRoute roles={['admin', 'manager']}>
              <Sender />
            </ProtectedRoute>
          }
        />
        <Route
          path="/campaigns"
          element={
            <ProtectedRoute roles={['admin', 'manager']}>
              <Campaigns />
            </ProtectedRoute>
          }
        />
        <Route
          path="/bots"
          element={
            <ProtectedRoute roles={['admin', 'manager']}>
              <Bots />
            </ProtectedRoute>
          }
        />
        <Route
          path="/staff"
          element={
            <ProtectedRoute roles={['admin']}>
              <Staff />
            </ProtectedRoute>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
