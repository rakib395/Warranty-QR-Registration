# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class WarrantyPolicy(models.Model):
    _name = 'ms.warranty.policy'
    _description = 'Warranty Policy'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Policy Name', required=True, tracking=True)
    code = fields.Char(string='Policy Code', required=True, copy=False, tracking=True)
    active = fields.Boolean(default=True, tracking=True)


    company_id = fields.Many2one(
        'res.company', 
        string='Company/Brand', 
        required=True, 
        index=True, 
        default=lambda self: self.env.company
    )
    parent_policy_id = fields.Many2one(
        'ms.warranty.policy', 
        string='Inherit From Parent Policy',
        tracking=True,
        domain="[('company_id', '!=', company_id)]",
        help="Select a global or parent company policy to inherit fields from."
    )

    description = fields.Text(string='Customer Policy Summary')
    internal_note = fields.Text(string='Internal Instruction')

    
    warranty_duration_value = fields.Integer(string='Duration Number', default=1, required=True, tracking=True)
    warranty_duration_unit = fields.Selection([
        ('days', 'Days'),
        ('months', 'Months'),
        ('years', 'Years')
    ], string='Duration Unit', default='years', required=True, tracking=True)

    warranty_start_basis = fields.Selection([
        ('sale_date', 'Sale Date'),
        ('invoice_date', 'Invoice Date'),
        ('delivery_date', 'Delivery Date'),
        ('registration_date', 'Registration Date'),
        ('manufacture_date', 'Manufacture Date'),
        ('manual', 'Manual Date')
    ], string='Start Basis', default='registration_date', required=True, tracking=True)

    #  Claim & Registration 
    registration_required = fields.Boolean(string='Registration Required', default=True, tracking=True)
    auto_approve_registration = fields.Boolean(string='Auto Approve Registration', default=False)
    registration_deadline_days = fields.Integer(string='Registration Deadline (Days)', help="Days from purchase")
    allow_late_registration = fields.Boolean(string='Allow Late Registration', default=True)
    
    serial_required = fields.Boolean(string='Serial Number Required', default=True)
    invoice_required = fields.Boolean(string='Invoice Proof Required', default=False)
    dealer_required = fields.Boolean(string='Dealer Required', default=False)
    
    max_claim_count = fields.Integer(string='Max Claims Allowed', default=0, help="0 means unlimited")

    allow_transfer = fields.Boolean(
        string='Allow Ownership Transfer', 
        default=True, 
        tracking=True,
        help="If unchecked, manual warranty transfer will be restricted for this policy."
    )

    # Coverage & Exclusions
    coverage_ids = fields.One2many('ms.warranty.coverage.term', 'policy_id', string='Coverage Terms')
    exclusion_ids = fields.One2many('ms.warranty.exclusion', 'policy_id', string='Exclusions')

    # Smart Button Counts 
    registration_count = fields.Integer(compute='_compute_counts', string="Registrations")
    claim_count = fields.Integer(compute='_compute_counts', string="Claims")


    @api.onchange('parent_policy_id')
    def _onchange_parent_policy_id(self):
        if self.parent_policy_id:
            parent = self.parent_policy_id
            self.warranty_duration_value = parent.warranty_duration_value
            self.warranty_duration_unit = parent.warranty_duration_unit
            self.warranty_start_basis = parent.warranty_start_basis
            self.registration_required = parent.registration_required
            self.auto_approve_registration = parent.auto_approve_registration
            self.registration_deadline_days = parent.registration_deadline_days
            self.allow_late_registration = parent.allow_late_registration
            self.serial_required = parent.serial_required
            self.invoice_required = parent.invoice_required
            self.dealer_required = parent.dealer_required
            self.max_claim_count = parent.max_claim_count
            self.allow_transfer = parent.allow_transfer

    def _compute_counts(self):
        for record in self:
            record.registration_count = self.env['ms.warranty.registration'].search_count([('policy_id', '=', record.id)]) if 'ms.warranty.registration' in self.env else 0
            record.claim_count = self.env['ms.warranty.claim'].search_count([('policy_id', '=', record.id)]) if 'ms.warranty.claim' in self.env else 0


    # Validation
    @api.constrains('warranty_duration_value')
    def _check_duration_value(self):
        for record in self:
            if record.warranty_duration_value <= 0:
                raise ValidationError(_("Warranty duration number must be a positive integer."))

    _sql_constraints = [
    ('name_uniq', 'unique(name)', 'The policy name must be unique!')
    ]


    def action_view_registrations(self):
        self.ensure_one()
        return {
            'name': _('Warranty Registrations'),
            'type': 'ir.actions.act_window',
            'res_model': 'ms.warranty.registration',
            'view_mode': 'list,form',
            'view_type': 'form', 
            'domain': [('policy_id', '=', self.id)],
            'context': {'default_policy_id': self.id},
            'target': 'current',
        }


    def action_view_claims(self):
        self.ensure_one()
        return {
            'name': _('Warranty Claims'),
            'type': 'ir.actions.act_window',
            'res_model': 'ms.warranty.claim',
            'view_mode': 'list,form',
            'view_type': 'form', 
            'domain': [('registration_id.policy_id', '=', self.id)],
            'context': {},
            'target': 'current',
        }


