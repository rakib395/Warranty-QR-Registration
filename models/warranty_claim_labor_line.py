# -*- coding: utf-8 -*-

from odoo import models, fields, api

class WarrantyClaimLaborLine(models.Model):
    _name = 'ms.warranty.claim.labor.line'
    _description = 'Warranty Claim Repair Labor Line'

    claim_id = fields.Many2one(
        'ms.warranty.claim', 
        string='Warranty Claim', 
        ondelete='cascade', 
        required=True
    )
    description = fields.Char(
        string='Labor / Service Description', 
        required=True
    )
    hours = fields.Float(
        string='Hours Spent', 
        default=1.0
    )
    hourly_rate = fields.Float(
        string='Hourly Rate'
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

    @api.depends('hours', 'hourly_rate', 'warranty_covered')
    def _compute_subtotal(self):
        for line in self:
            if line.warranty_covered:
                line.subtotal = 0.0
            else:
                line.subtotal = line.hours * line.hourly_rate