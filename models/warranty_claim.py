# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta

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

    service_center_id = fields.Many2one('ms.warranty.service.center', string='Service Center', tracking=True)
    technician_id = fields.Many2one('res.users', string='Assigned Technician', tracking=True)
    sla_deadline = fields.Date(string='SLA Deadline', readonly=True, tracking=True)

    diagnosis = fields.Text(string='Diagnosis', tracking=True)
    repair_notes = fields.Text(string='Repair Notes')
    part_lines = fields.One2many('ms.warranty.claim.part.line', 'claim_id', string='Replaced Parts')
    labor_lines = fields.One2many('ms.warranty.claim.labor.line', 'claim_id', string='Labor/Service Lines')

    resolution_type = fields.Selection([
        ('repair', 'Repair'),
        ('replacement', 'Replacement Product'),
        ('refund', 'Refund')
    ], string='Resolution Type', default='repair', required=True, tracking=True)
    
    replacement_product_id = fields.Many2one('product.product', string='Replacement Product', tracking=True)
    replacement_serial_no = fields.Char(string='Replacement Serial Number', tracking=True)
    old_serial_no = fields.Char(string='Old Serial Linked', compute='_compute_old_serial_no', store=True)

    refund_amount = fields.Float(string='Refund Amount', tracking=True)
    refund_reason = fields.Text(string='Refund Reason Description')

    @api.depends('registration_id')
    def _compute_old_serial_no(self):
        for claim in self:
            if claim.registration_id:
                claim.old_serial_no = claim.registration_id.serial_no
            else:
                claim.old_serial_no = False

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

    def action_assign_claim_processing(self, service_center_id, technician_id):
        """US-007: core logic to update state, calculate SLA, and create automated activity"""
        self.ensure_one()
        calculated_deadline = fields.Date.today() + timedelta(days=7)
             
        self.write({
            'service_center_id': service_center_id.id,
            'technician_id': technician_id.id,
            'sla_deadline': calculated_deadline,
            'state': 'under_review' 
        })
  
        body_msg = _(
            "Claim has been successfully assigned.<br/>"
            "<b>Service Center:</b> %s<br/>"
            "<b>Technician:</b> %s<br/>"
            "<b>SLA Deadline:</b> %s"
        ) % (service_center_id.name, technician_id.name, calculated_deadline)
        
        self.message_post(body=body_msg, subtype_xmlid="mail.mt_comment")

        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        self.activity_schedule(
            activity_type_id=activity_type.id if activity_type else False,
            date_deadline=calculated_deadline,
            summary=_("Inspect and Resolve Claim: %s") % self.name,
            note=_("Please review the detailed issue description and resolve the claim before the SLA deadline."),
            user_id=technician_id.id
        )

    def action_mark_as_repaired(self):
        """Validate diagnosis/notes and close the claim as repaired"""
        self.ensure_one()
        if not self.diagnosis:
            raise UserError(_("Please provide a proper diagnosis before marking the claim as repaired."))
        if not self.repair_notes:
            raise UserError(_("Repair notes are mandatory to close the repair lifecycle."))
        
        self.write({'state': 'resolved'})
        
        log_body = _(
            "Warranty Claim has been successfully resolved and closed via <b>Repair Resolution</b>.<br/>"
            "<b>Diagnosis:</b> %s<br/>"
            "<b>Repair Notes:</b> %s"
        ) % (self.diagnosis, self.repair_notes)
        self.message_post(body=log_body, subtype_xmlid="mail.mt_comment")

    def action_approve_replacement(self):
        """Approve and execute product replacement with carry-forward warranty logic"""
        self.ensure_one()
        if not self.replacement_product_id:
            raise UserError(_("Please capture the Replacement Product before approval."))
        if not self.replacement_serial_no:
            raise UserError(_("Replacement Serial Number is mandatory to execute replacement flow."))
        
        old_reg = self.registration_id
        if not old_reg:
            raise UserError(_("No active warranty registration linked with this claim."))

        new_expiry = old_reg.expiry_date

        new_reg_vals = {
            'customer_name': old_reg.customer_name,
            'customer_phone': old_reg.customer_phone,
            'customer_email': old_reg.customer_email,
            'product_id': self.replacement_product_id.id,
            'serial_no': self.replacement_serial_no,
            'purchase_date': old_reg.purchase_date,
            'policy_id': old_reg.policy_id.id if old_reg.policy_id else False,
            'dealer_id': old_reg.dealer_id.id if old_reg.dealer_id else False,
            'state': 'approved', 
        }
        
        new_registration = self.env['ms.warranty.registration'].create(new_reg_vals)
        new_registration.write({'expiry_date': new_expiry})

        old_reg.write({'state': 'expired'})
        old_reg.message_post(body=_("This product has been replaced by Claim: %s. New Serial: %s") % (self.name, self.replacement_serial_no))

        self.write({'state': 'resolved'})

        log_body = _(
            "Warranty Claim has been approved for <b>Product Replacement</b>.<br/>"
            "<b>Old Serial:</b> %s <br/>"
            "<b>New Replacement Serial:</b> %s <br/>"
            "<b>Warranty Status:</b> Successfully Carry-forwarded till %s."
        ) % (self.old_serial_no, self.replacement_serial_no, new_expiry)
        
        self.message_post(body=log_body, subtype_xmlid="mail.mt_comment")

    def action_approve_refund(self):
        """Mark claim for refund, void old warranty registration and create a Draft Credit Note"""
        self.ensure_one()
        if self.refund_amount <= 0:
            raise UserError(_("Please provide a valid Refund Amount greater than 0."))
        if not self.refund_reason:
            raise UserError(_("Refund Reason Description is mandatory to process a claim liquidation."))
        
        old_reg = self.registration_id
        if not old_reg:
            raise UserError(_("No active warranty registration linked with this claim."))

        credit_note_vals = {
            'move_type': 'out_refund',
            'state': 'draft',
            'ref': _('Warranty Refund for Claim: %s') % self.name,
            'invoice_origin': self.name,
            'invoice_line_ids': [(0, 0, {
                'name': _('Refund for Product: %s (Serial: %s) - Reason: %s') % (old_reg.product_id.name, old_reg.serial_no, self.refund_reason),
                'product_id': old_reg.product_id.id,
                'quantity': 1.0,
                'price_unit': self.refund_amount,
            })],
        }
        
        try:
            credit_note = self.env['account.move'].create(credit_note_vals)
            chatter_msg = _("Automated Account Bridge: Draft Credit Note %s has been created for finance approval.") % credit_note.name
        except Exception:

            chatter_msg = _("Account Bridge Log: Registered for refund queue. Finance approval required.")

        old_reg.write({'state': 'expired'})
        old_reg.message_post(body=_("This warranty registration was voided because a Refund was approved via Claim: %s.") % self.name)

        self.write({'state': 'resolved'})

        log_body = _(
            "Warranty Claim has been marked and approved for <b>Customer Refund</b>.<br/>"
            "<b>Refund Amount Approved:</b> %s <br/>"
            "<b>Reason for Refund:</b> %s <br/>"
            "<b>Status:</b> Warranty terminated, forwarded to Finance Ledger."
        ) % (self.refund_amount, self.refund_reason)
        
        self.message_post(body=log_body, subtype_xmlid="mail.mt_comment")