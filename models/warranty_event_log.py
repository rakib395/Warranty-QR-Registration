# -*- coding: utf-8 -*-
from odoo import models, fields, api

class WarrantyEventLog(models.Model):
    _name = 'ms.warranty.event.log'
    _description = 'Warranty Event Log'
    _order = 'create_date desc'

    registration_id = fields.Many2one('ms.warranty.registration', string='Warranty Registration', required=True, ondelete='cascade')
    event_type = fields.Selection([
        ('extension', 'Warranty Extension'),
        ('transfer', 'Ownership Transfer'),
        ('void', 'Warranty Voided')
    ], string='Event Type', required=True, default='extension')
    
    old_expiry_date = fields.Date(string='Old Expiry Date')
    new_expiry_date = fields.Date(string='New Expiry Date')
    reason = fields.Text(string='Reason', required=True)
    user_id = fields.Many2one('res.users', string='Authorized User', default=lambda self: self.env.user, readonly=True)
    create_date = fields.Datetime(string='Logged On', readonly=True)
    transfer_date = fields.Date(string="Transfer Date")