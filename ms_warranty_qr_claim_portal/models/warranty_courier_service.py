# -*- coding: utf-8 -*-

from odoo import models, fields

class WarrantyCourierService(models.Model):
    _name = 'warranty.courier.service'
    _description = 'Warranty Courier Service Providers'
    _order = 'name'

    name = fields.Char(string="Courier Name", required=True, index=True)
    website_url = fields.Char(
        string="Tracking URL Prefix", 
        help="Example: https://sundarbancourierltd.com/tracking?no="
    )
    active = fields.Boolean(string="Active", default=True)