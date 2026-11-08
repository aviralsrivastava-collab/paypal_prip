from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.demo_state import DemoState


class DemoStateRepository:
    """
    Repository for managing demo state records with optimistic concurrency control.
    """

    @staticmethod
    def get_by_key(session: Session, key: str) -> Optional[DemoState]:
        stmt = select(DemoState).where(DemoState.key == key)
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def create(session: Session, key: str, value: str) -> DemoState:
        state = DemoState(key=key, value=value, version=1)
        session.add(state)
        session.flush()
        return state

    @staticmethod
    def update(
        session: Session, state: DemoState, new_value: str, expected_version: int
    ) -> DemoState:
        if state.version != expected_version:
            raise ValueError(
                f"Optimistic lock conflict: current version is {state.version}, expected {expected_version}"
            )
        state.value = new_value
        state.version += 1
        session.add(state)
        session.flush()
        return state
