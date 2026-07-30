# -*- coding: utf-8 -*-

from odoo import models, fields, api

class WarrantyClaimPartLine(models.Model):
    _name = 'ms.warranty.claim.part.line'
    _description = 'Warranty Claim Repair Part Line'

    claim_id = fields.Many2one(
        'ms.warranty.claim', 
        string='Warranty Claim', 
        ondelete='cascade', 
        required=True
    )
    product_id = fields.Many2one(
        'product.product', 
        string='Part / Component', 
        required=True
    )
    quantity = fields.Float(
        string='Quantity', 
        default=1.0, 
        required=True
    )
    price_unit = fields.Float(
        string='Unit Price'
    )
    subtotal = fields.Float(
        string='Subtotal', 
        compute='_compute_subtotal', 
        store=True
    )
    warranty_covered = fields.Boolean(
        string='Covered Under Warranty', 
        default=True
    )

    @api.depends('quantity', 'price_unit', 'warranty_covered')
    def _compute_subtotal(self):
        for line in self:
            if line.warranty_covered:
                line.subtotal = 0.0
            else:
                line.subtotal = line.quantity * line.price_unit