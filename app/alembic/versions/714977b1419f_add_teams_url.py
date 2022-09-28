"""add_teams_url

Revision ID: 714977b1419f
Revises: ba890d61554f
Create Date: 2022-06-08 07:37:22.472284-07:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '714977b1419f'
down_revision = 'ba890d61554f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('settings', sa.Column('teams_url', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('settings', 'teams_url')
    # ### end Alembic commands ###
