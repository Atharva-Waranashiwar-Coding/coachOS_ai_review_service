import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260710_0001"
down_revision = None
branch_labels = None
depends_on = None

outbox_status = postgresql.ENUM(
    "pending",
    "processing",
    "published",
    "failed",
    name="outbox_status",
    create_type=False,
)

def upgrade():
    bind = op.get_bind()
    enum_to_create = postgresql.ENUM(
        "pending",
        "processing",
        "published",
        "failed",
        name="outbox_status",
    )
    enum_to_create.create(bind, checkfirst=True)
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "destination",
            sa.String(100),
            nullable=False,
            server_default="athlete-timeline",
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status",
            outbox_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
    )
    op.create_index("ix_outbox_status_available", "outbox_events", ["status", "available_at"])
    op.create_index("ix_outbox_created_at", "outbox_events", ["created_at"])
    op.create_index("ix_outbox_aggregate", "outbox_events", ["aggregate_type", "aggregate_id"])


def downgrade():
    op.drop_table("outbox_events")
    postgresql.ENUM(name="outbox_status").drop(op.get_bind(), checkfirst=True)
