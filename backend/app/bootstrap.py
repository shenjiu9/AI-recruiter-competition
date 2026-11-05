from contextlib import contextmanager
from types import SimpleNamespace

from app.kernel.types import SystemClock
from app.modules.org.adapters.headcount import SqlHeadcount
from app.modules.org.adapters.repository import SqlDirectory
from app.modules.org.public import OrgFacade
from app.modules.requisition.adapters.repository import SqlRepository
from app.modules.requisition.public import RequisitionFacade
from app.platform.auth import Auth
from app.platform.crypto import Crypto
from app.platform.database import Database
from app.platform.idempotency import Idempotency
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
                self.clock,
                SqlJournal(session, self.clock),
            )
            yield SimpleNamespace(
                org=org,
                auth=Auth(self.settings, self.clock, org),
                requisition=RequisitionFacade(
                    SqlRepository(session, self.crypto),
                    org,
                    self.clock,
                    SqlJournal(session, self.clock),
                ),
                idempotency=Idempotency(session, self.clock, self.crypto),
            )


def build_container(settings, clock=None):
    return Container(settings, clock)
