from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, Integer, String, delete, select, update
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.types import DomainError
from app.platform.database import Base


class HeadcountRecord(Base):
    __tablename__ = "headcount"
    __table_args__ = (
        CheckConstraint(
            "planned >= 0 AND used >= 0 AND reserved >= 0 AND planned >= used + reserved",
            name="capacity",
        ),
        {"schema": "org"},
    )
    dept: Mapped[str] = mapped_column(String(100), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    planned: Mapped[int] = mapped_column(Integer)
    used: Mapped[int] = mapped_column(Integer)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    frozen: Mapped[bool] = mapped_column(Boolean)
    effective_from: Mapped[date] = mapped_column(Date)
    updated_on: Mapped[date] = mapped_column(Date)


class ReservationRecord(Base):
    __tablename__ = "hc_reservation"
    __table_args__ = {"schema": "org"}
    requisition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dept: Mapped[str] = mapped_column(String(100))
    year: Mapped[int] = mapped_column(Integer)
    count: Mapped[int] = mapped_column(Integer)


def dto(record):
    return {
        key: getattr(record, key)
        for key in (
            "dept",
            "year",
            "version",
            "planned",
            "used",
            "reserved",
            "frozen",
            "effective_from",
            "updated_on",
        )
    } | {"available": record.planned - record.used - record.reserved}


class SqlHeadcount:
    def __init__(self, session):
        self.session = session

    def get(self, dept, year):
        row = self.session.get(HeadcountRecord, (dept, year), populate_existing=True)
        return dto(row) if row else None

    def release(self, req_id):
        row = self.session.execute(
            delete(ReservationRecord)
            .where(ReservationRecord.requisition_id == req_id)
            .returning(ReservationRecord.dept, ReservationRecord.year, ReservationRecord.count)
        ).first()
        if not row:
            return 0
        result = self.session.execute(
            update(HeadcountRecord)
            .where(
                HeadcountRecord.dept == row.dept,
                HeadcountRecord.year == row.year,
                HeadcountRecord.reserved >= row.count,
            )
            .values(
                reserved=HeadcountRecord.reserved - row.count, version=HeadcountRecord.version + 1
            )
        )
        if result.rowcount != 1:
            raise DomainError("HC_RELEASE_INVALID", "编制预占数据不一致，不能关闭岗位", 409)
        return row.count

    def list(self, departments, year):
        return [
            dto(row)
            for row in self.session.scalars(
                select(HeadcountRecord)
                .where(
                    HeadcountRecord.dept.in_(departments),
                    HeadcountRecord.year == year,
                )
                .order_by(HeadcountRecord.dept)
            )
        ]

    def save(self, dept, command, today):
        values = command.model_dump(exclude={"expected_version"})
        values.update(updated_on=today)
        if command.expected_version == 0:
            dialect = self.session.bind.dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            result = self.session.execute(
                insert(HeadcountRecord)
                .values(
                    dept=dept,
                    version=1,
                    reserved=0,
                    **values,
                )
                .on_conflict_do_nothing()
                .returning(HeadcountRecord.dept)
            )
            changed = result.scalar_one_or_none() is not None
        else:
            result = self.session.execute(
                update(HeadcountRecord)
                .where(
                    HeadcountRecord.dept == dept,
                    HeadcountRecord.year == command.year,
                    HeadcountRecord.version == command.expected_version,
                    HeadcountRecord.reserved + command.used <= command.planned,
                )
                .values(**values, version=HeadcountRecord.version + 1)
            )
            changed = result.rowcount == 1
        if not changed:
            raise DomainError(
                "VERSION_CONFLICT", "编制已变化或调整后无法覆盖已用与预占人数，请刷新", 409
            )
        return self.get(dept, command.year)

    def reserve(self, dept, req_id, count, today):
        # Conditional UPDATE serializes competing final approvals on PostgreSQL.
        # The ledger and request CAS share the caller's transaction; either all commit or all roll back.
        result = self.session.execute(
            update(HeadcountRecord)
            .where(
                HeadcountRecord.dept == dept,
                HeadcountRecord.year == today.year,
                HeadcountRecord.effective_from <= today,
                HeadcountRecord.frozen.is_(False),
                HeadcountRecord.planned - HeadcountRecord.used - HeadcountRecord.reserved >= count,
            )
            .values(reserved=HeadcountRecord.reserved + count, version=HeadcountRecord.version + 1)
        )
        if result.rowcount != 1:
            return False
        self.session.add(
            ReservationRecord(requisition_id=req_id, dept=dept, year=today.year, count=count)
        )
        # Flush after the request CAS so duplicate decisions fail with VERSION_CONFLICT,
        # rather than exposing a unique constraint error from the reservation ledger.
        return True
