import type { ReactElement } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth, type Role } from '../store/auth'

interface Props {
  children: ReactElement
  roles?: Role[]
}

export default function ProtectedRoute({ children, roles }: Props) {
  const user = useAuth((s) => s.user)
  const location = useLocation()

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }
  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/" replace />
  }
  return children
}
