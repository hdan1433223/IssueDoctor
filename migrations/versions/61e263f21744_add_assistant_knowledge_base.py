"""add assistant knowledge base

Revision ID: 61e263f21744
Revises: f1a6d2c90b31
Create Date: 2026-10-22 20:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "61e263f21744"
down_revision = "f1a6d2c90b31"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assistant_knowledge_bases",
        sa.Column("analysis_run_id", sa.String(length=36), nullable=False),
        sa.Column("index_version", sa.String(length=20), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
        sa.PrimaryKeyConstraint("analysis_run_id"),
    )
    op.create_table(
        "assistant_knowledge_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_key", sa.String(length=160), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("vector_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("rank_boost", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_run_id",
            "source_key",
            name="uq_run_assistant_source_key",
        ),
    )
    op.create_index(
        op.f("ix_assistant_knowledge_chunks_analysis_run_id"),
        "assistant_knowledge_chunks",
        ["analysis_run_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_assistant_knowledge_chunks_analysis_run_id"),
        table_name="assistant_knowledge_chunks",
    )
    op.drop_table("assistant_knowledge_chunks")
    op.drop_table("assistant_knowledge_bases")
