from odoo import models, api, _
from odoo.exceptions import UserError

class StockWarehouseOrderpoint(models.Model):
    _inherit = "stock.warehouse.orderpoint"

    @api.model
    def _unlink_processed_orderpoints(self):
        ICP = self.env["ir.config_parameter"].sudo()
        skip = ICP.get_param("stock.replenishment.skip_cleanup_on_open", "True") == "True"
        if skip:
            return self.browse()
        return super()._unlink_processed_orderpoints()

    @api.model
    def cron_cleanup_processed_orderpoints(self):
        domain = [("qty_to_order", "=", 0)]
        ops = self.search(domain, limit=5000)
        if ops:
            ops.unlink()


    def _compute_qty_to_order(self):
        return super()._compute_qty_to_order()