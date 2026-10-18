"""Durable conservative X reservations. No budget is created or enabled here.

Reservations survive every ambiguous outcome and crash. They are never refunded
automatically: an estimate is a spending ceiling reservation, not a provider bill.
The caller holds controls/account/publication/target locks, in that order, before
locking this account's budget. No code in this module acquires those locks later.
"""
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, ForeignKey, Uuid, select, text

from .models import Base


def x_global_budget_enabled(value):
    amount=value.get('x_budget_microusd') if isinstance(value,dict) else None
    return type(amount) is int and amount>0


class SocialPlatformBudget(Base):
    __tablename__ = 'social_platform_budgets'
    account_id = Column(Uuid(as_uuid=True), ForeignKey('social_accounts.id'), primary_key=True)
    access_verified = Column(Boolean, nullable=False, default=False, server_default='false')
    enabled = Column(Boolean, nullable=False, default=False, server_default='false')
    limit_microusd = Column(BigInteger, nullable=False, default=0, server_default='0')
    reserved_microusd = Column(BigInteger, nullable=False, default=0, server_default='0')
    spent_microusd = Column(BigInteger, nullable=False, default=0, server_default='0')
    version = Column(BigInteger, nullable=False, default=1, server_default='1')
    __table_args__ = (CheckConstraint('limit_microusd >= 0 AND reserved_microusd >= 0 AND spent_microusd >= 0 AND reserved_microusd + spent_microusd <= limit_microusd AND version > 0', name='ck_social_platform_budget_bounds'),)


def budget_available(row, cost):
    """Strict JSON/ORM/SQL row gate shared by preview, intent and material load."""
    if type(cost) is not int or cost < 1 or cost > 2**63 - 1 or row is None:
        return False
    values = [row.get(k) for k in ('limit_microusd', 'reserved_microusd', 'spent_microusd')]
    return (row.get('enabled') is True and row.get('access_verified') is True
            and all(type(v) is int and 0 <= v <= 2**63 - 1 for v in values)
            and values[0] - values[1] - values[2] >= cost)


def reserve_x_operation(conn, account_id, cost):
    row = conn.execute(select(SocialPlatformBudget.__table__).where(
        SocialPlatformBudget.account_id == account_id).with_for_update()).mappings().first()
    if not budget_available(row, cost):
        return False
    changed = conn.execute(SocialPlatformBudget.__table__.update().where(
        SocialPlatformBudget.account_id == account_id,
        SocialPlatformBudget.version == row['version']).values(
            reserved_microusd=row['reserved_microusd'] + cost, version=row['version'] + 1))
    if changed.rowcount != 1:
        raise RuntimeError('X_BUDGET_RESERVATION_CONFLICT')
    if conn.dialect.name == 'postgresql':
        conn.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    actual = conn.execute(select(SocialPlatformBudget.__table__).where(
        SocialPlatformBudget.account_id == account_id)).mappings().one()
    expected = dict(row) | {'reserved_microusd': row['reserved_microusd'] + cost, 'version': row['version'] + 1}
    if any(type(actual[key]) is not type(value) or actual[key] != value for key,value in expected.items()):
        raise RuntimeError('X_BUDGET_RESERVATION_UNVERIFIED')
    return True
