"""Add immutable coach approval workflow persistence."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260716_0003"
down_revision = "20260710_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    visibility = postgresql.ENUM("coach_only", "athlete_visible", name="review_visibility")
    rejection_category = postgresql.ENUM(
        "inaccurate",
        "insufficient",
        "unsafe",
        "irrelevant",
        "too_generic",
        "inadequate_context",
        "other",
        name="review_rejection_category",
    )
    audit_action = postgresql.ENUM(
        "review_generated",
        "revision_created",
        "preview_requested",
        "review_approved",
        "review_rejected",
        name="review_audit_action",
    )
    for enum in (visibility, rejection_category, audit_action):
        enum.create(op.get_bind(), checkfirst=True)

    op.add_column("ai_reviews", sa.Column("latest_revision_number", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ai_reviews", sa.Column("approved_snapshot_id", sa.UUID(), nullable=True))
    op.add_column("ai_reviews", sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE ai_reviews SET latest_revision_number = COALESCE((SELECT MAX(revision_number) FROM review_revisions WHERE review_revisions.review_id = ai_reviews.id), 0)"
    )
    op.execute(
        "UPDATE ai_reviews SET generated_at = generation_completed_at WHERE status IN ('generated', 'approved', 'rejected')"
    )
    op.alter_column("ai_reviews", "latest_revision_number", server_default=None)

    op.add_column("review_revisions", sa.Column("athlete_message", sa.Text(), nullable=True))
    op.add_column("review_revisions", sa.Column("change_summary", sa.String(500), nullable=True))
    op.add_column("review_revisions", sa.Column("based_on_revision_number", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_revision_number_positive", "review_revisions", "revision_number > 0")
    op.create_check_constraint(
        "ck_revision_based_on_lower",
        "review_revisions",
        "based_on_revision_number IS NULL OR based_on_revision_number < revision_number",
    )

    op.create_table(
        "approved_review_snapshots",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("review_id", sa.UUID(), sa.ForeignKey("ai_reviews.id"), nullable=False, unique=True),
        sa.Column("source_revision_id", sa.UUID(), sa.ForeignKey("review_revisions.id"), nullable=True),
        sa.Column("approved_by_user_id", sa.UUID(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("observations", postgresql.JSONB(), nullable=False),
        sa.Column("strengths", postgresql.JSONB(), nullable=False),
        sa.Column("improvement_areas", postgresql.JSONB(), nullable=False),
        sa.Column("recommended_drills", postgresql.JSONB(), nullable=False),
        sa.Column("athlete_message", sa.Text(), nullable=True),
        sa.Column("visibility", visibility, nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_foreign_key(
        "fk_review_approved_snapshot", "ai_reviews", "approved_review_snapshots", ["approved_snapshot_id"], ["id"]
    )

    op.create_table(
        "review_rejections",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("review_id", sa.UUID(), sa.ForeignKey("ai_reviews.id"), nullable=False, unique=True),
        sa.Column("rejected_by_user_id", sa.UUID(), nullable=False),
        sa.Column("category", rejection_category, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "review_audit_events",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("review_id", sa.UUID(), sa.ForeignKey("ai_reviews.id"), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("action_type", audit_action, nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_review_occurred", "review_audit_events", ["review_id", "occurred_at"])
    op.create_index("ix_audit_actor", "review_audit_events", ["actor_user_id"])
    op.create_index("ix_audit_action", "review_audit_events", ["action_type"])


def downgrade() -> None:
    op.drop_index("ix_audit_action", table_name="review_audit_events")
    op.drop_index("ix_audit_actor", table_name="review_audit_events")
    op.drop_index("ix_audit_review_occurred", table_name="review_audit_events")
    op.drop_table("review_audit_events")
    op.drop_table("review_rejections")
    op.drop_constraint("fk_review_approved_snapshot", "ai_reviews", type_="foreignkey")
    op.drop_table("approved_review_snapshots")
    op.drop_constraint("ck_revision_based_on_lower", "review_revisions", type_="check")
    op.drop_constraint("ck_revision_number_positive", "review_revisions", type_="check")
    op.drop_column("review_revisions", "based_on_revision_number")
    op.drop_column("review_revisions", "change_summary")
    op.drop_column("review_revisions", "athlete_message")
    op.drop_column("ai_reviews", "generated_at")
    op.drop_column("ai_reviews", "approved_snapshot_id")
    op.drop_column("ai_reviews", "latest_revision_number")
    for name in ("review_audit_action", "review_rejection_category", "review_visibility"):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
