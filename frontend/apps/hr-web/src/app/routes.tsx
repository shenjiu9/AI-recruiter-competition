import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Shell } from './Shell';
import { WorkbenchPage } from '../pages/WorkbenchPage';
import { CandidateDetailPage } from '../pages/CandidateDetailPage';
import { CandidateListPage } from '../pages/CandidateListPage';
import { PositionListPage } from '../pages/PositionListPage';
import { PositionDetailPage } from '../pages/PositionDetailPage';
import { RequisitionListPage } from '../pages/RequisitionListPage';
import { RequisitionNewPage } from '../pages/RequisitionNewPage';
import { RequisitionDetailPage } from '../pages/RequisitionDetailPage';
import { RequisitionEditPage } from '../pages/RequisitionEditPage';
import { InterviewsPage } from '../pages/InterviewsPage';
import { LiveInterviewPage } from '../features/interview/ui/LiveInterviews';
import { AutomationSettingsPage } from '../pages/AutomationSettingsPage';
import { PlaceholderPage } from '../pages/PlaceholderPage';
import { HeadcountSettingsPage } from '../pages/HeadcountSettingsPage';
import { SalarySettingsPage } from '../pages/SalarySettingsPage';
import { OrganizationSettingsPage } from '../pages/OrganizationSettingsPage';
import { HiringPage } from '../pages/HiringPage';
import { AiJobsPage } from '../pages/AiJobsPage';

export const router = createBrowserRouter([
  {
    element: <Shell />,
    children: [
      {
        index: true,
        element: (
          <Navigate
            to={import.meta.env.VITE_USE_MOCK === 'false' ? '/requisitions' : '/workbench'}
            replace
          />
        ),
      },
      { path: 'workbench', element: <WorkbenchPage /> },
      { path: 'ai-jobs', element: <AiJobsPage /> },
      { path: 'hiring', element: <HiringPage /> },
      { path: 'hiring/:id', element: <HiringPage /> },
      { path: 'requisitions', element: <RequisitionListPage /> },
      { path: 'requisitions/new', element: <RequisitionNewPage /> },
      { path: 'requisitions/:id', element: <RequisitionDetailPage /> },
      { path: 'requisitions/:id/edit', element: <RequisitionEditPage /> },
      { path: 'positions', element: <PositionListPage /> },
      { path: 'positions/:id', element: <PositionDetailPage /> },
      { path: 'candidates', element: <CandidateListPage /> },
      { path: 'candidates/:id', element: <CandidateDetailPage /> },
      { path: 'interviews', element: <InterviewsPage /> },
      { path: 'interviews/:id', element: <LiveInterviewPage /> },
      { path: 'channels', element: <PlaceholderPage title="渠道" phase="第二期" /> },
      { path: 'insights', element: <PlaceholderPage title="数据洞察" phase="第二期" /> },
      { path: 'settings/automation', element: <AutomationSettingsPage /> },
      { path: 'settings/headcount', element: <HeadcountSettingsPage /> },
      { path: 'settings/salary', element: <SalarySettingsPage /> },
      { path: 'settings/organization', element: <OrganizationSettingsPage /> },
      { path: '*', element: <PlaceholderPage title="页面不存在" /> },
    ],
  },
]);
