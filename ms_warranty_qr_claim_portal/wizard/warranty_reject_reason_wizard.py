# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class WarrantyRejectReasonWizard(models.TransientModel):
    _name = 'warranty.reject.reason.wizard'
    _description = 'Warranty Rejection Reason Wizard'

    reason = fields.Text(string="Rejection Reason", required=True)

    def action_reject_confirm(self):
        self.ensure_one()
        
        active_id = self.env.context.get('active_id')
        if active_id:
            registration = self.env['ms.warranty.registration'].browse(active_id)
            if registration:
                registration.write({
                    'state': 'rejected',
                    'rejection_reason': self.reason  
                })
                
                body_html = f"""
                <div>
                    <p><strong>Warranty Request Rejected</strong></p>
                    <ul style="margin:0;padding-left:18px;">
                        <li><strong>Reason:</strong> {self.reason}</li>
                    </ul>
                </div>
                """
                
                registration.message_post(
                    body=body_html,
                    body_is_html=True,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )
                
        return {'type': 'ir.actions.act_window_close'}