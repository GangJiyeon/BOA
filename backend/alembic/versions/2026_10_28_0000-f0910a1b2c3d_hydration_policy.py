"""Allow explicit hydration maintenance and optional dryness exclusions."""
from alembic import op
import sqlalchemy as sa

revision='f0910a1b2c3d'
down_revision='f0810a1b2c3d'
branch_labels=None
depends_on=None


def replace_checks(effects,conditions):
    existing={c['name'] for c in sa.inspect(op.get_bind()).get_check_constraints('category_ingredients')}
    names={}
    for key in ('rule_effect','rule_condition'):
        names[key]=next((n for n in (key,'ck_category_ingredients_'+key) if n in existing),None)
        if names[key] is None:raise RuntimeError('Missing cosmetic rule check: '+key)
    with op.batch_alter_table('category_ingredients') as batch:
        for key in names:batch.drop_constraint(op.f(names[key]),type_='check')
        batch.create_check_constraint(op.f('ck_category_ingredients_rule_effect'),effects)
        batch.create_check_constraint(op.f('ck_category_ingredients_rule_condition'),conditions)


def upgrade():
    replace_checks("effect IN ('match','exclude','caution','maintain')",
                   "condition IN ('always','redness_opt_in','dryness_opt_in')")


def downgrade():
    count=op.get_bind().execute(sa.text("SELECT COUNT(*) FROM category_ingredients WHERE effect='maintain' OR condition='dryness_opt_in'")).scalar()
    if count:raise RuntimeError('New hydration rule history exists; refusing a lossy downgrade.')
    replace_checks("effect IN ('match','exclude','caution')","condition IN ('always','redness_opt_in')")
