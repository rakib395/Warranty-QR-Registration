# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    has_warranty = fields.Boolean(string="Warranty Applicable", default=False)
    warranty_policy_id = fields.Many2one('ms.warranty.policy', string='Warranty Policy')