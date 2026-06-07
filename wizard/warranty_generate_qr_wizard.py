# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class WarrantyGenerateQRWizard(models.TransientModel):
    _name = 'warranty.generate.qr.wizard'
    _description = 'Bulk Warranty QR & Serial Generator'

    product_id = fields.Many2one(
        'product.product', 
        string='Product', 
        required=True, 
        domain=[('has_warranty', '=', True)]
    )
    quantity = fields.Integer(string='Quantity to Generate', required=True, default=1)
    prefix = fields.Char(string='Serial Prefix', required=True, help="Example: WATCH-")
    start_number = fields.Integer(string='Start Sequence No.', required=True, default=1)
    purpose = fields.Selection([
        ('registration', 'Registration'),
        ('generic', 'Generic')
    ], string='Purpose', required=True, default='registration')

    def action_generate_tokens(self):
        self.ensure_one()
        if self.quantity <= 0:
            raise UserError(_("Quantity must be greater than zero!"))

        token_obj = self.env['ms.warranty.qr.token']
        current_seq = self.start_number

        for i in range(self.quantity):
            serial_no = f"{self.prefix.strip()}{str(current_seq).zfill(3)}"
            
            existing_token = token_obj.search([('serial_no', '=', serial_no)], limit=1)
            if existing_token:
                raise UserError(_("Serial Number %s already exists! Please adjust start sequence or prefix.") % serial_no)

            token_obj.create({
                'product_id': self.product_id.id,
                'serial_no': serial_no,
                'purpose': self.purpose,
                'state': 'new',
            })
            current_seq += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('%s Unique QR Tokens & Serials generated successfully.') % self.quantity,
                'sticky': False,
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }