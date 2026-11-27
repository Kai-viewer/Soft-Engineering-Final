"""Space query module: room details, facilities, borrow methods and floor plans.

rooms 只新增一般欄位（沒有外鍵、CHECK 或非常數預設值），
SQLite 可以直接 ADD / DROP COLUMN，不需要重建資料表。
"""
from alembic import op
import sqlalchemy as sa


revision = '0002_spaces'
down_revision = '0001'
branch_labels = None
depends_on = None

ROOM_COLUMNS = (
    ('building', sa.String(length=20), {'server_default': '管理學院', 'nullable': False}),
    ('room_type', sa.String(length=50), {'nullable': True}),
    ('alias', sa.String(length=50), {'nullable': True}),
    ('category', sa.String(length=20), {'server_default': 'classroom', 'nullable': False}),
    ('bookable', sa.Boolean(), {'server_default': sa.true(), 'nullable': False}),
    ('manager', sa.String(length=100), {'nullable': True}),
    ('borrow_method', sa.String(length=30), {'nullable': True}),
    ('location', sa.String(length=100), {'nullable': True}),
    ('usage_note', sa.Text(), {'nullable': True}),
    ('note', sa.Text(), {'nullable': True}),
    ('source_url', sa.String(length=255), {'nullable': True}),
)


def upgrade() -> None:
    op.create_table(
        'borrow_methods',
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('url', sa.String(length=255), nullable=True),
        sa.Column('sort_order', sa.SmallInteger(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('code'),
    )
    op.create_table(
        'floor_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('building', sa.String(length=20), nullable=False),
        sa.Column('floor', sa.Integer(), nullable=False),
        sa.Column('image_path', sa.String(length=255), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('building', 'floor', name='uq_floor_plans_building_floor'),
    )
    for name, type_, options in ROOM_COLUMNS:
        op.add_column('rooms', sa.Column(name, type_, **options))
    op.create_table(
        'room_facilities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('room_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('room_id', 'name', name='uq_room_facilities_room_name'),
    )
    op.create_index(op.f('ix_room_facilities_room_id'), 'room_facilities', ['room_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_room_facilities_room_id'), table_name='room_facilities')
    op.drop_table('room_facilities')
    for name, _, _ in reversed(ROOM_COLUMNS):
        op.drop_column('rooms', name)
    op.drop_table('floor_plans')
    op.drop_table('borrow_methods')
