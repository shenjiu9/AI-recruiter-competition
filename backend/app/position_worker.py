"""Durable position subscriber. Each receipt and business effect commit together."""

import argparse
import logging
from datetime import UTC, timedelta

from sqlalchemy import select

from app.bootstrap import build_container
from app.kernel.types import DomainError
from app.platform.inbox import GROUP, InboxRecord, pending
from app.platform.records import EventRecord
from app.platform.settings import Settings


def consume(container, event_id, force=False):
    with container.scope() as services:
        # Serializes duplicate delivery and same-position matching across API processes.
        services.org.lock_configuration()
        session = services.session
        event = session.get(EventRecord, event_id)
        if not event or event.type != "requisition.approved" or event.schema_version != 1:
            raise DomainError("EVENT_UNSUPPORTED", "事件不存在或版本不支持")
        receipt = session.get(InboxRecord, (event_id, GROUP), populate_existing=True)
        if receipt and receipt.status == "done":
            return False
        if receipt and not force:
            due = receipt.next_attempt
            if receipt.status == "dead" or (
                due and due.replace(tzinfo=UTC) > container.clock.now()
            ):
                return False
        services.position.on_requisition_approved(event)
        if not receipt:
            receipt = InboxRecord(event_id=event_id, consumer=GROUP, attempts=0)
            session.add(receipt)
        receipt.status, receipt.next_attempt, receipt.error_code = "done", None, None
        receipt.attempts += 1
        return True


def run_once(container, limit=20):
    with container.db.sessions() as session:
        ids = pending(session, container.clock.now(), limit)
    completed = failed = 0
    for event_id in ids:
        try:
            completed += int(consume(container, event_id))
        except Exception as error:
            failed += 1
            # Never persist exception text, source payloads or names in retry metadata.
            code = error.code if isinstance(error, DomainError) else type(error).__name__
            with container.scope() as services:
                services.org.lock_configuration()
                receipt = services.session.get(
                    InboxRecord, (event_id, GROUP), populate_existing=True
                )
                if receipt and receipt.status == "done":
                    continue
                if not receipt:
                    receipt = InboxRecord(event_id=event_id, consumer=GROUP, attempts=0)
                    services.session.add(receipt)
                receipt.attempts += 1
                receipt.status = "dead" if receipt.attempts >= 5 else "retry"
                receipt.error_code = code[:80]
                receipt.next_attempt = container.clock.now() + timedelta(
                    seconds=min(300, 2**receipt.attempts)
                )
            logging.getLogger("recruiter").warning(
                "position_event_failed event_id=%s code=%s", event_id, code
            )
    return {"completed": completed, "failed": failed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry-event", help="Explicitly retry one failed persisted event")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    container = build_container(Settings())
    if args.status:
        with container.db.sessions() as session:
            for row in session.scalars(
                select(InboxRecord).where(
                    InboxRecord.consumer == GROUP, InboxRecord.status != "done"
                )
            ):
                print(row.event_id, row.status, row.attempts, row.error_code)
    else:
        print(
            {"completed": consume(container, args.retry_event, force=True)}
            if args.retry_event
            else run_once(container)
        )


if __name__ == "__main__":
    main()
