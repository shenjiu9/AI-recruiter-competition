from contextlib import contextmanager
from types import SimpleNamespace

from app.kernel.types import SystemClock
from app.modules.application.adapters.repository import SqlApplications
from app.modules.application.public import ApplicationFacade
from app.modules.candidate.adapters.repository import SqlCandidates
from app.modules.candidate.public import CandidateFacade
from app.modules.conversation.public import ConversationFacade
from app.modules.conversation.repository import SqlConversations
from app.modules.org.adapters.configuration import SqlConfiguration
from app.modules.org.adapters.headcount import SqlHeadcount
from app.modules.org.adapters.repository import SqlDirectory
from app.modules.org.adapters.salary import SqlSalary
from app.modules.org.public import OrgFacade
from app.modules.position.adapters.repository import SqlPositions
from app.modules.position.calendar import WorkCalendar
from app.modules.position.public import PositionFacade
from app.modules.requisition.adapters.repository import SqlRepository
from app.modules.requisition.adapters.transfers import SqlTransfers
from app.modules.requisition.public import RequisitionFacade
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
            yield SimpleNamespace(
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
