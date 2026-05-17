# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class WarrantyClaimRejectWizard(models.TransientModel):
    _name = 'warranty.claim.reject.wizard'
    _description = 'Reject Warranty Claim Wizard'

    claim_id = fields.Many2one('ms.warranty.claim', string='Claim', required=True, default=lambda self: self.env.context.get('active_id'))
    rejection_reason = fields.Text(string='Reason for Rejection', required=True)

    def action_reject_claim(self):
        """US-006: Process rejection from wizard, save reason and notify customer"""
        self.ensure_one()
        if self.claim_id:
            self.claim_id.write({
                'state': 'rejected',
                'rejection_reason': self.rejection_reason
            })
    
            self.claim_id.message_post(
                body=_("Dear Customer, Your warranty claim %s has been Rejected.<br/><b>Reason:</b> %s") % (self.claim_id.name, self.rejection_reason),
                subtype_xmlid="mail.mt_comment"
            )
        return {'type': 'ir.actions.act_window_close'}