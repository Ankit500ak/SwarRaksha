from __future__ import annotations

import datetime as dt

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey,
                        Integer, LargeBinary, String, Text)
from sqlalchemy.orm import relationship

from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, default="")
    language = Column(String, default="en")
    created_at = Column(DateTime, default=utcnow)


class OtpCode(Base):
    __tablename__ = "otp_codes"
    id = Column(Integer, primary_key=True)
    email = Column(String, index=True, nullable=False)
    code_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)


class Circle(Base):
    __tablename__ = "circles"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    members = relationship("CircleMember", back_populates="circle",
                           cascade="all, delete-orphan")


class CircleMember(Base):
    __tablename__ = "circle_members"
    id = Column(Integer, primary_key=True)
    circle_id = Column(Integer, ForeignKey("circles.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null while invite pending
    invited_email = Column(String, nullable=True)
    invite_code = Column(String, unique=True, nullable=True)
    role = Column(String, default="member")  # owner | member
    status = Column(String, default="active")  # active | invited
    circle = relationship("Circle", back_populates="members")


class Voiceprint(Base):
    __tablename__ = "voiceprints"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    label = Column(String, nullable=False)  # e.g. "Son — Rohan"
    # PRODUCTION TODO (PLAN.md S.11): encrypt at rest. Local build stores
    # the raw float blob — see MODEL_CARD.md.
    embedding = Column(LargeBinary, nullable=False)
    embedding_kind = Column(String, nullable=False)
    sample_count = Column(Integer, default=3)
    consent_at = Column(DateTime, default=utcnow)
    created_at = Column(DateTime, default=utcnow)


class Check(Base):
    __tablename__ = "checks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)  # clip | live
    status = Column(String, default="complete")  # open | complete
    voiceprint_id = Column(Integer, ForeignKey("voiceprints.id"), nullable=True)
    verdict = Column(String, nullable=True)  # green | yellow | red
    risk_score = Column(Float, nullable=True)
    aggregate_spoof = Column(Float, nullable=True)
    voiceprint_similarity = Column(Float, nullable=True)
    model_version = Column(String, nullable=True)
    reasons_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=utcnow)
    windows = relationship("CheckWindow", back_populates="check",
                           cascade="all, delete-orphan")


class CheckWindow(Base):
    __tablename__ = "check_windows"
    id = Column(Integer, primary_key=True)
    check_id = Column(Integer, ForeignKey("checks.id"), nullable=False)
    idx = Column(Integer, nullable=False)
    t_start = Column(Float, nullable=False)
    t_end = Column(Float, nullable=False)
    spoof_score = Column(Float, nullable=True)  # null = insufficient speech
    check = relationship("Check", back_populates="windows")


class Challenge(Base):
    __tablename__ = "challenges"
    id = Column(Integer, primary_key=True)
    check_id = Column(Integer, ForeignKey("checks.id"), nullable=False)
    kind = Column(String, nullable=False)  # liveness_phrase | code_word
    prompt = Column(String, nullable=False)
    result = Column(String, nullable=True)  # passed | failed | None
    created_at = Column(DateTime, default=utcnow)


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    check_id = Column(Integer, ForeignKey("checks.id"), nullable=True)
    details = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # recipient
    check_id = Column(Integer, ForeignKey("checks.id"), nullable=True)
    message = Column(String, nullable=False)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
