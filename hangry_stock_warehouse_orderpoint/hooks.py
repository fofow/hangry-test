# hooks.py
from odoo import api

INDEXES = [
    ("idx_quant_product_company_loc",
     "CREATE INDEX IF NOT EXISTS idx_quant_product_company_loc "
     "ON stock_quant (product_id, company_id, location_id)"),
    ("idx_move_product_state_loc",
     "CREATE INDEX IF NOT EXISTS idx_move_product_state_loc "
     "ON stock_move (product_id, state, location_id)"),
    ("idx_move_product_state_locdest",
     "CREATE INDEX IF NOT EXISTS idx_move_product_state_locdest "
     "ON stock_move (product_id, state, location_dest_id)"),
]

def post_init_create_indexes(env):
    cr = env.cr
    for _, sql in INDEXES:
        cr.execute(sql)
    cr.execute("ANALYZE stock_quant")
    cr.execute("ANALYZE stock_move")
