# -*- coding: utf-8 -*-

from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    service_center_id = fields.Many2one(
        'ms.warranty.service.center', 
        string='Warranty Service Center',
        tracking=True
    )