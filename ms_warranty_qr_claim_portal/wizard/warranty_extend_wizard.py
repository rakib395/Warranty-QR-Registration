# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta


class WarrantyExtendWizard(models.TransientModel):
    _name = 'warranty.extend.wizard'
    _description = 'Warranty Extension Wizard'

    registration_id = fields.Many2one(
        'ms.warranty.registration', 
        string='Warranty Registration', 
        required=True, 
        default=lambda self: self.env.context.get('active_id')
    )
    current_expiry_date = fields.Date(
        string='Current Expiry Date', 
        related='registration_id.expiry_date', 
        readonly=True
    )
    extension_months = fields.Integer(
        string='Extension Duration (Months)', 
        required=True, 
        default=1
    )
    extension_reason = fields.Text(
        string='Extension Reason', 
        required=True
    )

    @api.constrains('extension_months')
    def _check_duration(self):
        for record in self:
            if record.extension_months <= 0:
                raise ValidationError(_("Extension duration must be greater than 0 months!"))

    def action_extend_warranty(self):
        self.ensure_one()
        if not self.registration_id.expiry_date:
            raise ValidationError(_("Cannot extend warranty because the current registration does not have an expiry date set!"))

        old_expiry = self.registration_id.expiry_date
        new_expiry = old_expiry + timedelta(days=self.extension_months * 30)

        self.registration_id.write({
            'expiry_date': new_expiry
        })

        self.env['ms.warranty.event.log'].create({
            'registration_id': self.registration_id.id,
            'event_type': 'extension',
            'old_expiry_date': old_expiry,
            'new_expiry_date': new_expiry,
            'reason': self.extension_reason,
            'user_id': self.env.user.id,
        })

        body_html = f"""
        <div>
            <p><strong>Warranty Manually Extended</strong></p>
            <ul style="margin:0;padding-left:18px;">
                <li><strong>Duration:</strong> {self.extension_months} Month(s)</li>
                <li><strong>Old Expiry:</strong> {old_expiry}</li>
                <li><strong>New Expiry:</strong> {new_expiry}</li>
                <li><strong>Reason:</strong> {self.extension_reason}</li>
            </ul>
        </div>
        """

        self.registration_id.message_post(
            body=body_html,
            body_is_html=True,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
)