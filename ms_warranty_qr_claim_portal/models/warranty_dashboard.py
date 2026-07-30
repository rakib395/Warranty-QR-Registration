# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date, timedelta

class MSWarrantyDashboard(models.TransientModel):
    _name = 'ms.warranty.dashboard'
    _description = 'Warranty & Claims Custom Dashboard'


    date_from = fields.Date(
        string='Start Date', 
        required=True, 
        default=lambda self: date.today().replace(day=1) 
    )
    date_to = fields.Date(
        string='End Date', 
        required=True, 
        default=lambda self: date.today() 
    )
  
    count_registration = fields.Integer(string='Total Registrations', compute='_compute_dashboard_metrics')
    count_claim_submitted = fields.Integer(string='Submitted Claims', compute='_compute_dashboard_metrics')
    count_claim_resolved = fields.Integer(string='Resolved Claims', compute='_compute_dashboard_metrics')
    count_claim_unresolved = fields.Integer(string='Unresolved Claims', compute='_compute_dashboard_metrics')

    count_res_repair = fields.Integer(string='Repaired Units', compute='_compute_dashboard_metrics')
    count_res_replacement = fields.Integer(string='Replacements Given', compute='_compute_dashboard_metrics')
    count_res_refund = fields.Integer(string='Refunds Processed', compute='_compute_dashboard_metrics')

    display_name = fields.Char(compute='_compute_display_name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = "Warranty Performance Dashboard"

    @api.depends('date_from', 'date_to')
    def _compute_dashboard_metrics(self):
        """Calculates all metrics dynamically based on selected date ranges"""
        for record in self:
            if record.date_from > record.date_to:
                raise UserError(_("Start Date cannot be greater than End Date!"))

            reg_domain = [
                ('registration_date', '>=', record.date_from),
                ('registration_date', '<=', record.date_to)
            ]
            record.count_registration = self.env['ms.warranty.registration'].search_count(reg_domain)

            claim_base_domain = [
                ('create_date', '>=', fields.Datetime.to_string(record.date_from)),
                ('create_date', '<=', fields.Datetime.to_string(record.date_to + timedelta(days=1)))
            ]
            
        
            sub_domain = claim_base_domain + [('state', '=', 'submitted')]
            record.count_claim_submitted = self.env['ms.warranty.claim'].search_count(sub_domain)

           
            res_domain = claim_base_domain + [('state', 'in', ['resolved', 'delivered'])]
            record.count_claim_resolved = self.env['ms.warranty.claim'].search_count(res_domain)

           
            unres_domain = claim_base_domain + [('state', 'in', ['received', 'under_review', 'approved', 'repairing'])]
            record.count_claim_unresolved = self.env['ms.warranty.claim'].search_count(unres_domain)

           
            resolved_claims = self.env['ms.warranty.claim'].search(res_domain)
            
            record.count_res_repair = len(resolved_claims.filtered(lambda c: c.resolution_type == 'repair'))
            record.count_res_replacement = len(resolved_claims.filtered(lambda c: c.resolution_type == 'replacement'))
            record.count_res_refund = len(resolved_claims.filtered(lambda c: c.resolution_type == 'refund'))


    def action_view_registrations(self):
        self.ensure_one()
        return {
            'name': _('Warranty Registrations'),
            'type': 'ir.actions.act_window',
            'res_model': 'ms.warranty.registration',
            'view_mode': 'list,form',
            'domain': [('registration_date', '>=', self.date_from), ('registration_date', '<=', self.date_to)],
            'target': 'current',
        }

    def action_view_submitted_claims(self):
        self.ensure_one()
        return {
            'name': _('Submitted Claims'),
            'type': 'ir.actions.act_window',
            'res_model': 'ms.warranty.claim',
            'view_mode': 'list,form',
            'domain': [
                ('create_date', '>=', fields.Datetime.to_string(self.date_from)),
                ('create_date', '<=', fields.Datetime.to_string(self.date_to + timedelta(days=1))),
                ('state', '=', 'submitted')
            ],
            'target': 'current',
        }

    def action_view_resolved_claims(self):
        self.ensure_one()
        return {
            'name': _('Resolved Claims'),
            'type': 'ir.actions.act_window',
            'res_model': 'ms.warranty.claim',
            'view_mode': 'list,form',
            'domain': [
                ('create_date', '>=', fields.Datetime.to_string(self.date_from)),
                ('create_date', '<=', fields.Datetime.to_string(self.date_to + timedelta(days=1))),
                ('state', 'in', ['resolved', 'delivered'])
            ],
            'target': 'current',
        }

    def action_view_unresolved_claims(self):
        self.ensure_one()
        return {
            'name': _('Unresolved Claims'),
            'type': 'ir.actions.act_window',
            'res_model': 'ms.warranty.claim',
            'view_mode': 'list,form',
            'domain': [
                ('create_date', '>=', fields.Datetime.to_string(self.date_from)),
                ('create_date', '<=', fields.Datetime.to_string(self.date_to + timedelta(days=1))),
                ('state', 'in', ['received', 'under_review', 'approved', 'repairing'])
            ],
            'target': 'current',
        }
    
    def action_view_repair_details(self):
        self.ensure_one()
        return {
            'name': _('Repaired Units Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'ms.warranty.claim',
            'view_mode': 'list,form',
            'domain': [
                ('create_date', '>=', fields.Datetime.to_string(self.date_from)),
                ('create_date', '<=', fields.Datetime.to_string(self.date_to + timedelta(days=1))),
                ('state', 'in', ['resolved', 'delivered']),
                ('resolution_type', '=', 'repair')
            ],
            'target': 'current',
        }

    def action_view_replacement_details(self):
        self.ensure_one()
        return {
            'name': _('Replacements Given Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'ms.warranty.claim',
            'view_mode': 'list,form',
            'domain': [
                ('create_date', '>=', fields.Datetime.to_string(self.date_from)),
                ('create_date', '<=', fields.Datetime.to_string(self.date_to + timedelta(days=1))),
                ('state', 'in', ['resolved', 'delivered']),
                ('resolution_type', '=', 'replacement')
            ],
            'target': 'current',
        }

    def action_view_refund_details(self):
        self.ensure_one()
        return {
            'name': _('Refunds Processed Details'),
            'type': 'ir.actions.act_window',
            'res_model': 'ms.warranty.claim',
            'view_mode': 'list,form',
            'domain': [
                ('create_date', '>=', fields.Datetime.to_string(self.date_from)),
                ('create_date', '<=', fields.Datetime.to_string(self.date_to + timedelta(days=1))),
                ('state', 'in', ['resolved', 'delivered']),
                ('resolution_type', '=', 'refund')
            ],
            'target': 'current',
        }