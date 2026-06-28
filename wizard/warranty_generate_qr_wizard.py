# -*- coding: utf-8 -*-
from odoo import models, fields, _
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

    quantity = fields.Integer(
        string='Quantity to Generate',
        required=True,
        default=1
    )

    prefix = fields.Char(
        string='Serial Prefix',
        required=True,
        help="Example: WATCH-"
    )

    start_number = fields.Integer(
        string='Start Sequence No.',
        required=True,
        default=1
    )

    purpose = fields.Selection([
        ('registration', 'Registration'),
        ('generic', 'Generic')
    ], string='Purpose', required=True, default='registration')

    def action_generate_tokens(self):
        self.ensure_one()

        if self.quantity <= 0:
            raise UserError(_("Quantity must be greater than zero!"))

        token_obj = self.env['ms.warranty.qr.token']
        lot_obj = self.env['stock.lot']

        current_seq = self.start_number

        for i in range(self.quantity):

            serial_name = f"{self.prefix.strip()}{str(current_seq).zfill(3)}"

            lot = lot_obj.search([
                ('name', '=', serial_name),
                ('product_id', '=', self.product_id.id),
            ], limit=1)

            if not lot:
                lot = lot_obj.create({
                    'name': serial_name,
                    'product_id': self.product_id.id,
                    'company_id': self.env.company.id,
                })

            existing_token = token_obj.search([
                ('serial_no', '=', lot.id)
            ], limit=1)

            if existing_token:
                raise UserError(
                    _("Serial Number %s already exists! Please adjust start sequence or prefix.") % serial_name
                )

            token_obj.create({
                'product_id': self.product_id.id,
                'serial_no': lot.id,
                'purpose': self.purpose,
                'state': 'new',
                'company_id': self.env.company.id,
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