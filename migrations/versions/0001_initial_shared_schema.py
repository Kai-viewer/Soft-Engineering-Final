"""Create the initial shared schema."""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'equipment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_table(
        'rooms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('floor', sa.Integer(), nullable=False),
        sa.Column('capacity', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('panorama_path', sa.String(length=255), nullable=True),
        sa.Column('floor_plan_path', sa.String(length=255), nullable=True),
        sa.Column('map_x', sa.Float(), nullable=True),
        sa.Column('map_y', sa.Float(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint('(map_x IS NULL AND map_y IS NULL) OR (map_x IS NOT NULL AND map_y IS NOT NULL AND map_x BETWEEN 0 AND 100 AND map_y BETWEEN 0 AND 100)', name='ck_rooms_map_coordinates'),
        sa.CheckConstraint('capacity > 0', name='ck_rooms_capacity'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=16), server_default='member', nullable=False),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.CheckConstraint("role IN ('member', 'teacher', 'admin')", name='ck_users_role'),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name='ck_users_status'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_table(
        'bookings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('room_id', sa.Integer(), nullable=False),
        sa.Column('requester_id', sa.Integer(), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('reviewed_by_id', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('checked_out_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('returned_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'checked_out', 'returned')", name='ck_bookings_status'),
        sa.CheckConstraint('ends_at > starts_at', name='ck_bookings_interval'),
        sa.ForeignKeyConstraint(['requester_id'], ['users.id']),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_bookings_requester_id'), 'bookings', ['requester_id'], unique=False)
    op.create_index('ix_bookings_room_starts', 'bookings', ['room_id', 'starts_at'], unique=False)
    op.create_table(
        'courses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=False),
        sa.Column('room_id', sa.Integer(), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='requested', nullable=False),
        sa.CheckConstraint("status IN ('requested', 'confirmed')", name='ck_courses_status'),
        sa.CheckConstraint('ends_at > starts_at', name='ck_courses_interval'),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id']),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_courses_room_starts', 'courses', ['room_id', 'starts_at'], unique=False)
    op.create_index(op.f('ix_courses_teacher_id'), 'courses', ['teacher_id'], unique=False)
    op.create_table(
        'sessions',
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('csrf_token', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('token_hash'),
    )
    op.create_index(op.f('ix_sessions_expires_at'), 'sessions', ['expires_at'], unique=False)
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_table(
        'booking_items',
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('equipment_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id']),
        sa.PrimaryKeyConstraint('booking_id', 'equipment_id'),
    )


def downgrade() -> None:
    op.drop_table('booking_items')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_expires_at'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_index(op.f('ix_courses_teacher_id'), table_name='courses')
    op.drop_index('ix_courses_room_starts', table_name='courses')
    op.drop_table('courses')
    op.drop_index('ix_bookings_room_starts', table_name='bookings')
    op.drop_index(op.f('ix_bookings_requester_id'), table_name='bookings')
    op.drop_table('bookings')
    op.drop_table('users')
    op.drop_table('rooms')
    op.drop_table('equipment')
