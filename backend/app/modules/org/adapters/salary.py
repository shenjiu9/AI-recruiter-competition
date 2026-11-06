from datetime import date

from sqlalchemy import Date, Integer, LargeBinary, String, UniqueConstraint, func, select, update
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.types import DomainError, new_id
from app.platform.database import Base


class SalaryBandRecord(Base):
    __tablename__ = "salary_band"
    __table_args__ = (
        UniqueConstraint("series", "grade", "city", name="salary_dimensions"),
        {"schema": "org"},
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    series: Mapped[str] = mapped_column(String(80))
    grade: Mapped[str] = mapped_column(String(40))
    city: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)


class SalaryRevisionRecord(Base):
    __tablename__ = "salary_revision"
    __table_args__ = {"schema": "org"}
    band_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    effective_from: Mapped[date] = mapped_column(Date)
    updated_on: Mapped[date] = mapped_column(Date)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class SqlSalary:
    def __init__(self, session, crypto):
        self.session, self.crypto = session, crypto

    def _revision(self, row):
        return self.crypto.decrypt(row.data, f"{row.band_id}:{row.version}") | {
            "version": row.version,
            "effective_from": row.effective_from.isoformat(),
            "updated_on": row.updated_on.isoformat(),
        }

    def get(self, band_id, today):
        row = self.session.get(SalaryBandRecord, band_id, populate_existing=True)
        if not row:
            return None
        latest = self.session.get(SalaryRevisionRecord, (band_id, row.version))
        active = self.session.scalar(
            select(SalaryRevisionRecord)
            .where(
                SalaryRevisionRecord.band_id == band_id,
                SalaryRevisionRecord.effective_from <= today,
                SalaryRevisionRecord.version <= row.version,
            )
            .order_by(SalaryRevisionRecord.version.desc())
            .limit(1)
        )
        return {
            "id": row.id,
            "series": row.series,
            "grade": row.grade,
            "city": row.city,
            "version": row.version,
            "latest": self._revision(latest),
            "active": self._revision(active) if active else None,
            "stale": active is not None and (today - active.updated_on).days > 30,
        }

    def find(self, series, grade, city, today):
        band_id = self.session.scalar(
            select(SalaryBandRecord.id).where(
                SalaryBandRecord.series == series,
                SalaryBandRecord.grade == grade,
                SalaryBandRecord.city == city,
            )
        )
        return self.get(band_id, today) if band_id else None

    def list(self, today, page, size):
        total = self.session.scalar(select(func.count()).select_from(SalaryBandRecord))
        ids = self.session.scalars(
            select(SalaryBandRecord.id)
            .order_by(
                SalaryBandRecord.series,
                SalaryBandRecord.grade,
                SalaryBandRecord.city,
            )
            .offset((page - 1) * size)
            .limit(size)
        )
        return {
            "items": [self.get(band_id, today) for band_id in ids],
            "total": total,
            "page": page,
            "size": size,
        }

    def history(self, band_id):
        return [
            self._revision(row)
            for row in self.session.scalars(
                select(SalaryRevisionRecord)
                .where(
                    SalaryRevisionRecord.band_id == band_id,
                )
                .order_by(SalaryRevisionRecord.version.desc())
            )
        ]

    def save(self, command, today):
        if command.expected_version == 0:
            if self.session.bind.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            else:
                from sqlalchemy.dialects.sqlite import insert
            band_id = self.session.scalar(
                insert(SalaryBandRecord)
                .values(
                    id=new_id("SAL"),
                    series=command.series,
                    grade=command.grade,
                    city=command.city,
                    version=1,
                )
                .on_conflict_do_nothing()
                .returning(SalaryBandRecord.id)
            )
        else:
            band_id = self.session.scalar(
                update(SalaryBandRecord)
                .where(
                    SalaryBandRecord.series == command.series,
                    SalaryBandRecord.grade == command.grade,
                    SalaryBandRecord.city == command.city,
                    SalaryBandRecord.version == command.expected_version,
                )
                .values(version=SalaryBandRecord.version + 1)
                .returning(SalaryBandRecord.id)
            )
        if not band_id:
            raise DomainError("VERSION_CONFLICT", "薪资配置已存在或版本已变化，请刷新后重试", 409)
        version = command.expected_version + 1
        self.session.add(
            SalaryRevisionRecord(
                band_id=band_id,
                version=version,
                effective_from=command.effective_from,
                updated_on=today,
                data=self.crypto.encrypt(
                    {"lower": command.lower, "upper": command.upper, "months": command.months},
                    f"{band_id}:{version}",
                ),
            )
        )
        self.session.flush()
        return self.get(band_id, today)
