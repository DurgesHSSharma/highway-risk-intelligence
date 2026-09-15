import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import AppLayout from './layout/AppLayout'
import { ProjectsCacheProvider } from './context/ProjectsCacheContext'
import { LoadingState } from './components/StateViews'

// Route-level code splitting: the Dashboard/Analytics charts pull in
// recharts (the largest dependency), so only the page actually visited
// pays for it instead of every page bundling it into one chunk.
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Projects = lazy(() => import('./pages/Projects'))
const ProjectDetails = lazy(() => import('./pages/ProjectDetails'))
const RiskSummary = lazy(() => import('./pages/RiskSummary'))
const DecisionIntelligence = lazy(() => import('./pages/DecisionIntelligence'))
const Simulator = lazy(() => import('./pages/Simulator'))
const DocumentSearch = lazy(() => import('./pages/DocumentSearch'))
const Inconsistencies = lazy(() => import('./pages/Inconsistencies'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Reports = lazy(() => import('./pages/Reports'))
const NotFound = lazy(() => import('./pages/NotFound'))

export default function App() {
  return (
    <BrowserRouter>
      <ProjectsCacheProvider>
        <Suspense fallback={<div className="page"><LoadingState label="Loading page…" /></div>}>
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<Dashboard />} />
              <Route path="projects" element={<Projects />} />
              <Route path="projects/:projectId" element={<ProjectDetails />} />
              <Route path="risk-summary" element={<RiskSummary />} />
              <Route path="projects/:projectId/risk-summary" element={<RiskSummary />} />
              <Route path="decision-intelligence" element={<DecisionIntelligence />} />
              <Route path="projects/:projectId/decision-intelligence" element={<DecisionIntelligence />} />
              <Route path="simulator" element={<Simulator />} />
              <Route path="projects/:projectId/simulator" element={<Simulator />} />
              <Route path="documents" element={<DocumentSearch />} />
              <Route path="inconsistencies" element={<Inconsistencies />} />
              <Route path="analytics" element={<Analytics />} />
              <Route path="reports" element={<Reports />} />
              <Route path="reports/:projectId" element={<Reports />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </Suspense>
      </ProjectsCacheProvider>
    </BrowserRouter>
  )
}
