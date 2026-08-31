
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import SplashScreen from '../pages/splashscreen'
import Login from '../pages/Login.jsx'
import Copilot from '../pages/Copilot.jsx'
import QuestionHistory from '../pages/QuestionHistory.jsx'
import QuestionDetails from '../pages/QuestionDetails.jsx'
import AdminDashboard from '../pages/AdminDashboard.jsx'
import AdminSemanticLayer from '../pages/AdminSemanticLayer.jsx'
import AdminUsers from '../pages/AdminUsers.jsx'
import AdminReview from '../pages/AdminReview.jsx'
import AdminAuditLogs from '../pages/AdminAuditLogs.jsx'
import '../styles/admin-pages.css'



export default function MainLayout() {
  return (
<>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SplashScreen />} />
        <Route path="/login" element={<Login />} />
        <Route path="/copilot" element={<Copilot />} />
        <Route path="/history" element={<QuestionHistory />} />
        <Route path="/history/:queryId" element={<QuestionDetails />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/admin/semantic-layer" element={<AdminSemanticLayer />} />
        <Route path="/admin/users" element={<AdminUsers />} />
        <Route path="/admin/review" element={<AdminReview />} />
        <Route path="/admin/audit-logs" element={<AdminAuditLogs />} />
      </Routes>
    </BrowserRouter>

</>  )
}
