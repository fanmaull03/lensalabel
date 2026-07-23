"""
Model SQLAlchemy untuk knowledge base LensaLabel.

Tiga tabel:
- Ingredient           : data final yang dipakai mesin fuzzy matching saat runtime
- IngredientSynonym    : nama alias/kode aditif per bahan (one-to-many)
- ExpertValidation     : audit trail proses validasi pakar, strukturnya mengikuti
                         kolom di Lembar Validasi Knowledge Base
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SafetyCategory(str, enum.Enum):
    AMAN = "aman"
    PERHATIAN = "perhatian"
    HINDARI = "hindari"


class Ingredient(Base):
    """Data bahan makanan yang dipakai mesin RapidFuzz saat runtime."""

    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    standard_name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    category: Mapped[SafetyCategory] = mapped_column(
        SQLEnum(SafetyCategory, name="safety_category"), nullable=False
    )
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    references: Mapped[str | None] = mapped_column(Text, nullable=True)

    # False selama kategori masih usulan peneliti, belum ditandatangani validator
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    synonyms: Mapped[list["IngredientSynonym"]] = relationship(
        back_populates="ingredient", cascade="all, delete-orphan"
    )
    validations: Mapped[list["ExpertValidation"]] = relationship(
        back_populates="ingredient", cascade="all, delete-orphan"
    )


class IngredientSynonym(Base):
    """Nama alias, nama dagang, atau kode aditif (E-code) untuk satu bahan."""

    __tablename__ = "ingredient_synonyms"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )
    synonym: Mapped[str] = mapped_column(String(150), nullable=False)

    ingredient: Mapped["Ingredient"] = relationship(back_populates="synonyms")


class ExpertValidation(Base):
    """
    Catatan proses validasi, satu baris per bahan per validator.
    Field-nya mengikuti persis kolom di Lembar Validasi Knowledge Base:
    Usulan Peneliti, Setuju, Revisi Kategori, Catatan Ahli.
    """

    __tablename__ = "expert_validations"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )

    validator_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    validator_specialization: Mapped[str | None] = mapped_column(String(150), nullable=True)
    validator_institution: Mapped[str | None] = mapped_column(String(150), nullable=True)

    researcher_proposed_category: Mapped[SafetyCategory] = mapped_column(
        SQLEnum(SafetyCategory, name="safety_category"), nullable=False
    )
    is_agreed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    revised_category: Mapped[SafetyCategory | None] = mapped_column(
        SQLEnum(SafetyCategory, name="safety_category"), nullable=True
    )
    expert_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ingredient: Mapped["Ingredient"] = relationship(back_populates="validations")
