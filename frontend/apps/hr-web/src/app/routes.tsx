import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Shell } from './Shell';
import { WorkbenchPage } from '../pages/WorkbenchPage';
import { CandidateDetailPage } from '../pages/CandidateDetailPage';
import { CandidateListPage } from '../pages/CandidateListPage';
import { PositionListPage } from '../pages/PositionListPage';
import { PositionDetailPage } from '../pages/PositionDetailPage';
import { RequisitionListPage } from '../pages/RequisitionListPage';
import { RequisitionNewPage } from '../pages/RequisitionNewPage';
import { InterviewsPage } from '../pages/InterviewsPage';
import { AutomationSettingsPage } from '../pages/AutomationSettingsPage';
import { PlaceholderPage } from '../pages/PlaceholderPage';

export const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      { index: true, element: <Navigate to="/workbench" replace /> },
      { path: 'workbench', element: <WorkbenchPage /> },
      { path: 'requisitions', element: <RequisitionListPage /> },
      { path: 'requisitions/new', element: <RequisitionNewPage /> },
      { path: 'positions', element: <PositionListPage /> },
      { path: 'positions/:id', element: <PositionDetailPage /> },
      { path: 'candidates', element: <CandidateListPage /> },
      { path: 'candidates/:id', element: <CandidateDetailPage /> },
      { path: 'interviews', element: <InterviewsPage /> },
      { path: 'channels', element: <PlaceholderPage title="渠道" phase="第二期" /> },
      { path: 'insights', element: <PlaceholderPage title="数据洞察" phase="第二期" /> },
      { path: 'settings/automation', element: <AutomationSettingsPage /> },
      { path: '*', element: <PlaceholderPage title="页面不存在" /> },
    ],
  },
]);
