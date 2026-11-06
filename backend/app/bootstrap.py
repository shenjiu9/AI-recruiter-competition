from contextlib import contextmanager
from types import SimpleNamespace

from app.kernel.types import SystemClock
from app.modules.application.adapters.repository import SqlApplications
from app.modules.application.public import ApplicationFacade
from app.modules.automation.public import AutomationFacade
from app.modules.automation.repository import AutomationRecord
from app.modules.candidate.adapters.repository import SqlCandidates
from app.modules.candidate.public import CandidateFacade
from app.modules.conversation.public import ConversationFacade
from app.modules.conversation.repository import SqlConversations
from app.modules.decision.public import DecisionFacade
from app.modules.decision.repository import CardRecord
from app.modules.hiring.public import HiringFacade
from app.modules.hiring.repository import HireRecord
from app.modules.interview.public import InterviewFacade
from app.modules.interview.repository import SqlInterviews
from app.modules.org.adapters.configuration import SqlConfiguration
from app.modules.org.adapters.headcount import SqlHeadcount
from app.modules.org.adapters.repository import SqlDirectory
from app.modules.org.adapters.salary import SqlSalary
from app.modules.org.public import OrgFacade
from app.modules.position.adapters.repository import SqlPositions
from app.modules.position.calendar import WorkCalendar
from app.modules.position.public import PositionFacade
from app.modules.query.public import QueryFacade
from app.modules.requisition.adapters.repository import SqlRepository
from app.modules.requisition.adapters.transfers import SqlTransfers
from app.modules.requisition.public import RequisitionFacade
from app.platform.aggregates import EncryptedStore
from app.platform.auth import Auth
from app.platform.crypto import Crypto
from app.platform.database import Database
from app.platform.idempotency import Idempotency
from app.platform.inbox import InboxRecord  # noqa: F401 - register migration metadata
from app.platform.records import SqlJournal


class Container:
    def __init__(self, settings, clock=None):
        self.settings = settings
        self.clock = clock or SystemClock()
        self.db = Database(settings.database_url)
        self.crypto = Crypto(settings.encryption_key)
        self.interview_gateway = None

    @contextmanager
    def scope(self):
        with self.db.sessions.begin() as session:
            org = OrgFacade(
                SqlDirectory(session),
                SqlHeadcount(session),
                SqlSalary(session, self.crypto),
                self.clock,
                SqlJournal(session, self.clock),
                SqlConfiguration(session),
            )
            requisition = RequisitionFacade(
                SqlRepository(session, self.crypto),
                org,
                self.clock,
                SqlJournal(session, self.clock),
                SqlTransfers(session),
            )
            position = PositionFacade(
                SqlPositions(session, self.crypto),
                requisition,
                org,
                self.clock,
                SqlJournal(session, self.clock),
                WorkCalendar(self.settings.position_holidays, self.settings.position_workdays),
            )
            candidate = CandidateFacade(
                SqlCandidates(session, self.crypto, self.settings.encryption_key),
                org,
                self.clock,
                SqlJournal(session, self.clock),
            )
            application = ApplicationFacade(
                SqlApplications(session, self.crypto),
                candidate,
                position,
                self.clock,
                SqlJournal(session, self.clock),
            )
            candidate.applications = application
            position.applications = application
            conversation = ConversationFacade(
                SqlConversations(session, self.crypto),
                candidate,
                application,
                org,
                self.clock,
                SqlJournal(session, self.clock),
                self.settings,
            )
            candidate.conversations = conversation
            application.conversations = conversation
            interview = InterviewFacade(
                SqlInterviews(session, self.crypto),
                candidate,
                application,
                position,
                org,
                self.clock,
                SqlJournal(session, self.clock),
                self.settings,
                self.interview_gateway,
            )
            candidate.interviews = interview
            application.interviews = interview
            automation = AutomationFacade(
                EncryptedStore(session, self.crypto, AutomationRecord),
                org,
                candidate,
                position,
                self.clock,
                SqlJournal(session, self.clock),
            )
            hiring = HiringFacade(
                EncryptedStore(session, self.crypto, HireRecord),
                application,
                candidate,
                position,
                interview,
                org,
                automation,
                position.calendar,
                self.clock,
                SqlJournal(session, self.clock),
            )
            decision = DecisionFacade(
                EncryptedStore(session, self.crypto, CardRecord),
                hiring,
                application,
                interview,
                position,
                candidate,
                org,
                self.clock,
                SqlJournal(session, self.clock),
            )
            hiring.decisions = decision
            application.hiring = hiring
            query = QueryFacade(position, application, hiring, decision, candidate)
            yield SimpleNamespace(
                hiring=hiring,
                decision=decision,
                automation=automation,
                query=query,
                interview=interview,
                conversation=conversation,
                session=session,
                position=position,
                candidate=candidate,
                application=application,
                org=org,
                auth=Auth(self.settings, self.clock, org),
                requisition=requisition,
                idempotency=Idempotency(session, self.clock, self.crypto),
            )


def build_container(settings, clock=None):
    return Container(settings, clock)
