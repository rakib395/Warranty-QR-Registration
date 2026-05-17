# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta

class WarrantyRegistration(models.Model):
    _name = 'ms.warranty.registration'
    _description = 'Warranty Registration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'registration_date desc'

    name = fields.Char(string='Registration No', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    
    # Customer Details
    customer_name = fields.Char(string='Customer Name', required=True, tracking=True)
    customer_phone = fields.Char(string='Phone', required=True, tracking=True)
    customer_email = fields.Char(string='Email', tracking=True)
    
    # Product & Purchase Details
    product_id = fields.Many2one('product.product', string='Product', required=True, tracking=True)
    serial_no = fields.Char(string='Serial Number', required=True, tracking=True)
    purchase_date = fields.Date(string='Purchase Date', default=fields.Date.context_today, required=True)
    dealer_id = fields.Many2one('res.partner', string='Dealer/Store', help="Where the product was bought")
    invoice_proof = fields.Binary(string='Invoice Proof/Photo')
    
    # Link with US-001 Policy
    policy_id = fields.Many2one('ms.warranty.policy', string='Warranty Policy', required=False)
    registration_date = fields.Date(string='Registration Date', default=fields.Date.context_today, readonly=True)
    expiry_date = fields.Date(string='Warranty Expiry', compute='_compute_expiry_date', store=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired/Voided') 
    ], string='Status', default='draft', tracking=True)

    # Duplicate Serial Validation
    @api.constrains('serial_no', 'product_id')
    def _check_duplicate_registration(self):
        for record in self:
            domain = [
                ('serial_no', '=', record.serial_no),
                ('product_id', '=', record.product_id.id),
                ('id', '!=', record.id),
                ('state', 'not in', ['rejected'])
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(_("This Serial Number is already registered for this product!"))

    @api.depends('purchase_date', 'policy_id')
    def _compute_expiry_date(self):
        for record in self:
            if record.id and not record.policy_id:
                continue
            if record.purchase_date and record.policy_id:
                duration = record.policy_id.warranty_duration_value
                unit = record.policy_id.warranty_duration_unit
                if unit == 'days':
                    record.expiry_date = record.purchase_date + timedelta(days=duration)
                elif unit == 'months':
                    record.expiry_date = record.purchase_date + timedelta(days=duration * 30)
                elif unit == 'years':
                    record.expiry_date = record.purchase_date + timedelta(days=duration * 365)
            else:
                record.expiry_date = False

    def action_submit(self):
        self.write({'state': 'pending'})

    def action_approve(self):
        self.write({'state': 'approved'})

        for record in self:
            if record.serial_no:
                token_record = self.env['ms.warranty.qr.token'].sudo().search([
                    ('serial_no', '=', record.serial_no)
                ], limit=1)
                if token_record:
                    token_record.write({
                        'state': 'used',
                        'registration_id': record.id,
                        'use_count': token_record.use_count + 1
                    })

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_reject(self):
        self.write({'state': 'rejected'})

    def action_expire(self):
        self.write({'state': 'expired'})
        
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('ms.warranty.registration') or _('New')
        return super(WarrantyRegistration, self).create(vals_list)