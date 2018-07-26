"""empty message

Revision ID: caf96244e10b
Revises: 4cac94c86047
Create Date: 2018-05-24 22:52:38.381505

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision = 'caf96244e10b'
down_revision = '4cac94c86047'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('access_codes', 'used_for')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('access_codes', sa.Column('used_for', sa.VARCHAR(), autoincrement=False, nullable=True))
    # ### end Alembic commands ###