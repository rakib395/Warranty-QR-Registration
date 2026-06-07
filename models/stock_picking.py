from odoo import models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()

        Token = self.env['ms.warranty.qr.token'].sudo()

        for picking in self:
            if picking.picking_type_code != 'outgoing':
                continue

            seen = set()

            for line in picking.move_line_ids:

                if not line.lot_id or not line.product_id:
                    continue

                serial = (line.lot_id.name or '').strip()
                product = line.product_id.id

                if not serial:
                    continue

                key = (product, serial)

                if key in seen:
                    continue
                seen.add(key)

                exists = Token.search_count([
                    ('product_id', '=', product),
                    ('serial_no', '=', serial)
                ])

                if exists:
                    continue

                Token.create({
                    'product_id': product,
                    'serial_no': serial,
                    'purpose': 'registration',
                    'state': 'new'
                })

        return res