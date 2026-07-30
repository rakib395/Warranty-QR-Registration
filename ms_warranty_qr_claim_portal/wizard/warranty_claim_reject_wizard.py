# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class WarrantyClaimRejectWizard(models.TransientModel):
    _name = 'warranty.claim.reject.wizard'
    _description = 'Reject Warranty Claim Wizard'

    claim_id = fields.Many2one('ms.warranty.claim', string='Claim', required=True, default=lambda self: self.env.context.get('active_id'))
    rejection_reason = fields.Text(string='Reason for Rejection', required=True)

    def action_reject_claim(self):
        self.ensure_one()
        if self.claim_id:
            self.claim_id.write({
                'state': 'rejected',
                'rejection_reason': self.rejection_reason
            })
    
            body_html = f"""
            <div>
                <p>Dear Customer, Your warranty claim <strong>{self.claim_id.name}</strong> has been Rejected.</p>
                <ul style="margin:0;padding-left:18px;">
                    <li><strong>Reason:</strong> {self.rejection_reason}</li>
                </ul>
            </div>
            """

            self.claim_id.message_post(
                body=body_html,
                body_is_html=True,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

        return {'type': 'ir.actions.act_window_close'}