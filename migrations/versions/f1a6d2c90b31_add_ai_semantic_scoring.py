"""add ai semantic scoring

Revision ID: f1a6d2c90b31
Revises: e4e382352c43
Create Date: 2026-09-26 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op


revision = "f1a6d2c90b31"
down_revision = "e4e382352c43"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("analysis_runs") as batch_op:
        batch_op.add_column(sa.Column("ai_semantic_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("ai_semantic_confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("enhanced_total_score", sa.Float(), nullable=True))

    with op.batch_alter_table("ai_issue_analyses") as batch_op:
        batch_op.add_column(sa.Column("semantic_quality_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("closure_quality_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("semantic_confidence", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "knowledge_candidate",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("recommended_action", sa.String(length=50), nullable=True))
        batch_op.add_column(
            sa.Column("evidence_json", sa.JSON(), server_default="[]", nullable=False)
        )


def downgrade():
    with op.batch_alter_table("ai_issue_analyses") as batch_op:
        batch_op.drop_column("evidence_json")
        batch_op.drop_column("recommended_action")
        batch_op.drop_column("knowledge_candidate")
        batch_op.drop_column("semantic_confidence")
        batch_op.drop_column("closure_quality_score")
        batch_op.drop_column("semantic_quality_score")

    with op.batch_alter_table("analysis_runs") as batch_op:
        batch_op.drop_column("enhanced_total_score")
        batch_op.drop_column("ai_semantic_confidence")
        batch_op.drop_column("ai_semantic_score")
