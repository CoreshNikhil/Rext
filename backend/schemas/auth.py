"""Pydantic v2 request/response DTOs for auth endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    message: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# --- Resident signup ---------------------------------------------------


class SignupRequestOtpRequest(BaseModel):
    house_number: str = Field(min_length=1, max_length=20)
    mobile_number: str = Field(min_length=1, max_length=15)


class SignupRequestOtpResponse(BaseModel):
    message: str
    # Populated only when settings.ENVIRONMENT == "development" — lets you
    # test the flow without a real SMS gateway. Never present in production.
    dev_otp: str | None = None


class SignupVerifyOtpRequest(BaseModel):
    house_number: str = Field(min_length=1, max_length=20)
    mobile_number: str = Field(min_length=1, max_length=15)
    otp_code: str = Field(min_length=4, max_length=8)


class SignupVerifyOtpResponse(BaseModel):
    signup_token: str


class SignupSetPasswordRequest(BaseModel):
    signup_token: str
    password: str = Field(min_length=8, max_length=128)


# --- Resident login ------------------------------------------------------


class ResidentLoginRequest(BaseModel):
    house_number: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=128)


# --- Resident password reset -----------------------------------------------


class PasswordResetRequestOtpRequest(BaseModel):
    house_number: str = Field(min_length=1, max_length=20)
    mobile_number: str = Field(min_length=1, max_length=15)


class PasswordResetVerifyOtpRequest(BaseModel):
    house_number: str = Field(min_length=1, max_length=20)
    mobile_number: str = Field(min_length=1, max_length=15)
    otp_code: str = Field(min_length=4, max_length=8)


class PasswordResetVerifyOtpResponse(BaseModel):
    reset_token: str


class PasswordResetConfirmRequest(BaseModel):
    reset_token: str
    new_password: str = Field(min_length=8, max_length=128)


# --- Shared refresh/logout -------------------------------------------------


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


# --- Admin login -----------------------------------------------------------


class AdminLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)
