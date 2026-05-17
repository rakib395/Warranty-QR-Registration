# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class WarrantyClaim(models.Model):
    _name = 'ms.warranty.claim'
    _description = 'Warranty Claim Request'
    _inherit = ['mail.thread', 'mail.activity.mixin'] 

   
    name = fields.Char(string='Claim Number', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    registration_id = fields.Many2one('ms.warranty.registration', string='Warranty Registration', required=True, ondelete='cascade')
    
    issue_category = fields.Selection([
        ('hardware', 'Hardware Failure'),
        ('software', 'Software / Firmware Issue'),
        ('damage', 'Physical Damage (Check Policy Extension)'),
        ('other', 'Other Technical Faults')
    ], string='Issue Category', default='hardware', required=True)
    
    preferred_contact = fields.Char(string='Preferred Contact', required=True)
    description = fields.Text(string='Detailed Issue Description', required=True)
    

    product_photo = fields.Binary(string='Product/Fault Photo', attachment=True)
    invoice_proof = fields.Binary(string='Purchase Invoice Proof', attachment=True)
    
   
    state = fields.Selection([
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('resolved', 'Resolved')
    ], string='Status', default='submitted', required=True, tracking=True)

    rejection_reason = fields.Text(string='Rejection Reason', readonly=True, tracking=True)


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('ms.warranty.claim') or _('New')
        return super(WarrantyClaim, self).create(vals_list)
    
    def action_under_review(self):
        """Put the claim under review state"""
        self.ensure_one()
        self.write({'state': 'under_review'})

    def action_approve(self):
        """US-006: Approve the warranty claim and log/notify"""
        self.ensure_one()
        self.write({
            'state': 'approved',
            'rejection_reason': False  
        })
       
        self.message_post(
            body=_("Dear Customer, Your warranty claim %s has been Approved. Our service center will process it shortly.") % self.name,
            subtype_xmlid="mail.mt_comment"
        )

    def action_resolved(self):
        """Mark the claim as resolved"""
        self.ensure_one()
        self.write({'state': 'resolved'})

    def action_reset_to_review(self):
        """US-006: Reset claim back to Under Review from final states if needed"""
        self.ensure_one()
        self.write({
            'state': 'under_review'
        })
        self.message_post(
            body=_("Warranty claim has been reset to 'Under Review' status by the administrator."),
            subtype_xmlid="mail.mt_comment"
        )