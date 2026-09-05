import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import SplashScreen from '../pages/splashscreen.jsx'
import Login from '../pages/Login.jsx'
import Copilot from '../pages/Copilot.jsx'
import QuestionHistory from '../pages/QuestionHistory.jsx'
import QuestionDetails from '../pages/QuestionDetails.jsx'
import AdminDashboard from '../pages/AdminDashboard.jsx'
import AdminSemanticLayer from '../pages/AdminSemanticLayer.jsx'
import AdminSemanticLayers from '../pages/AdminSemanticLayers.jsx'
import AdminSemanticLayerDetails from '../pages/AdminSemanticLayerDetails.jsx'
import AdminSemanticDraftReview from '../pages/AdminSemanticDraftReview.jsx'
import AdminUsers from '../pages/AdminUsers.jsx'
import AdminReview from '../pages/AdminReview.jsx'
import AdminAuditLogs from '../pages/AdminAuditLogs.jsx'
import '../styles/admin-pages.css'
import ProtectedRoute from '../components/ProtectedRoute.jsx'
import RoleRoute from '../components/RoleRoute.jsx'
import { ROLES } from '../config/roles.js'

export default function MainLayout() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SplashScreen />} />
        <Route path="/login" element={<Login />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<RoleRoute roles={[ROLES.NORMAL, ROLES.ADMIN]} />}>
            <Route path="/copilot" element={<Copilot />} />
            <Route path="/history" element={<QuestionHistory />} />
            <Route path="/history/:queryId" element={<QuestionDetails />} />
          </Route>

          <Route element={<RoleRoute role={ROLES.ADMIN} />}>
            <Route path="/admin" element={<AdminDashboard />} />
            <Route path="/admin/semantic-layer" element={<AdminSemanticLayer />} />
            <Route path="/admin/semantic-layer/upload" element={<AdminSemanticLayer />} />
            <Route path="/admin/semantic-layers" element={<AdminSemanticLayers />} />
            <Route path="/admin/semantic-layers/:layerId" element={<AdminSemanticLayerDetails />} />
            <Route path="/admin/semantic-layers/:layerId/:tab" element={<AdminSemanticLayerDetails />} />
            <Route path="/admin/semantic-layers/:layerId/revisions/:revisionId/review" element={<AdminSemanticDraftReview />} />
            <Route path="/admin/users" element={<AdminUsers />} />
            <Route path="/admin/review" element={<AdminReview />} />
            <Route path="/admin/audit-logs" element={<AdminAuditLogs />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
