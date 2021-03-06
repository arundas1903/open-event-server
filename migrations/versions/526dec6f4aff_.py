"""empty message

Revision ID: 526dec6f4aff
Revises: 8500f5ec6c45
Create Date: 2017-07-17 18:47:02.086751

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '526dec6f4aff'
down_revision = '8500f5ec6c45'

def upgrade():
    # commands auto generated by Alembic - please adjust! #
    op.drop_table('image_config')
    # end Alembic commands #


def downgrade():
    # commands auto generated by Alembic - please adjust! #
    op.create_table('image_config',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('page', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('size', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name=u'image_config_pkey')
    )
    # end Alembic commands #
