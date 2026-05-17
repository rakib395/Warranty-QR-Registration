# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class WarrantyServiceCenter(models.Model):
    _name = 'ms.warranty.service.center'
    _description = 'Warranty Service Center'
    _order = 'name'
    _inherit = ['mail.thread'] 

    name = fields.Char(string='Service Center Name', required=True, tracking=True)
    code = fields.Char(string='Center Code', required=True, copy=False, tracking=True)
    phone = fields.Char(string='Contact Number')
    email = fields.Char(string='Email Address')
    address = fields.Text(string='Full Address')
    active = fields.Boolean(string='Active', default=True, help="Set active to false to hide the service center without deleting it.")

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'The Service Center Code must be unique!')
    ]

    def name_get(self):
        """Custom display name inside Many2one drop-downs (e.g., [DHK01] Dhaka Central Center)"""
        result = []
        for center in self:
            name = f"[{center.code}] {center.name}" if center.code else center.name
            result.append((center.id, name))
        return result