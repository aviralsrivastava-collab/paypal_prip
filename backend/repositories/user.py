from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.user import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, user_id: str) -> Optional[User]:
        return self.session.get(User, user_id)

    def get_by_issuer_sub(self, iss: str, sub: str) -> Optional[User]:
        stmt = select(User).where(User.iss == iss, User.sub == sub)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email.strip().lower())
        return self.session.execute(stmt).scalar_one_or_none()

    def create(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user

    def get_or_create_from_claims(
        self,
        iss: str,
        sub: str,
        email: str,
        full_name: Optional[str] = None,
    ) -> User:
        user = self.get_by_issuer_sub(iss, sub)
        if user:
            # Sync email if it changed
            clean_email = email.strip().lower()
            if user.email != clean_email:
                user.email = clean_email
            if full_name and user.full_name != full_name:
                user.full_name = full_name
            self.session.flush()
            return user

        user = User(
            iss=iss,
            sub=sub,
            email=email.strip().lower(),
            full_name=full_name,
            is_active=True,
        )
        return self.create(user)
