"""empty message

Revision ID: e4311ef3ddf5
Revises: 0044c9631c7e
Create Date: 2018-08-01 14:17:47.445218

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision = 'e4311ef3ddf5'
down_revision = '699b64daa444'


def upgrade():
    op.create_table('events_orga',
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('payment_currency', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.add_column('events', sa.Column('events_orga_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'events', 'events_orga', ['events_orga_id'], ['id'], ondelete='CASCADE')
    op.add_column('events_version', sa.Column('events_orga_id', sa.Integer(), autoincrement=False, nullable=True))
    # ### end Alembic commands ###


def downgrade():

    op.drop_column('events_version', 'events_orga_id')
    op.drop_constraint(None, 'events', type_='foreignkey')
    op.drop_column('events', 'events_orga_id')
    op.drop_table('events_orga')
    # ### end Alembic commands ###