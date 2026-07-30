import uuid
from odoo import models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()

        for picking in self:
            if picking.picking_type_code != 'outgoing':
                continue

            for line in picking.move_line_ids:
                if not line.lot_id:
                    continue

                lot = line.lot_id
                if not lot.qr_token:
                    lot.sudo().write({
                        'qr_token': str(uuid.uuid4())
                    })

        return res