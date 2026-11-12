import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class MerchantCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")


class MerchantResponse(BaseModel):
    id: str
    slug: str
    name: str
    status: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class MembershipResponse(BaseModel):
    id: str
    merchant_id: str
    merchant_name: Optional[str] = None
    merchant_slug: Optional[str] = None
    user_id: str
    user_email: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    active_merchant_id: Optional[str] = None
    active_role: Optional[str] = None
    memberships: List[MembershipResponse] = []

    model_config = {"from_attributes": True}


class TenantMemberInviteRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    role: str = Field(default="MANAGER", pattern=r"^(OWNER|ADMIN|MANAGER|VIEWER)$")


class SwitchTenantRequest(BaseModel):
    merchant_id: str


class SwitchTenantResponse(BaseModel):
    active_merchant_id: str
    active_merchant_name: str
    active_role: str
    switched: bool
