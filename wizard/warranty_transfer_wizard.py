# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WarrantyTransferWizard(models.TransientModel):
    _name = 'warranty.transfer.wizard'
    _description = 'Warranty Ownership Transfer'

    registration_id = fields.Many2one(
        'ms.warranty.registration',
        string="Registration",
        default=lambda self: self.env.context.get('active_id')
    )

    # New Owner
    new_customer_name = fields.Char(
        string="New Customer Name",
        required=True
    )

    new_customer_phone = fields.Char(
        string="New Customer Phone",
        required=True
    )

    new_customer_email = fields.Char(
        string="New Customer Email"
    )

    # Transfer Info
    transfer_note = fields.Text(
        string="Transfer Reason / Justification",
        required=True
    )

    transfer_date = fields.Date(
        string="Transfer Date",
        default=fields.Date.today,
        readonly=True
    )

    def action_transfer(self):
        self.ensure_one()

        reg = self.registration_id

        if not reg:
            raise UserError(_("No active warranty registration found!"))

        if reg.policy_id and not reg.policy_id.allow_transfer:
            raise UserError(_(
                "This warranty policy does not allow ownership transfer!"
            ))

        old_owner_name = reg.customer_name
        old_owner_phone = reg.customer_phone
        old_owner_email = reg.customer_email

        self.env['ms.warranty.event.log'].create({
            'registration_id': reg.id,
            'event_type': 'transfer',
            'reason': self.transfer_note,
            'transfer_date': self.transfer_date,
            'old_expiry_date': reg.expiry_date,
            'new_expiry_date': reg.expiry_date,
        })

        reg.write({
            # Previous owner history
            'previous_owner_name': old_owner_name,
            'previous_owner_phone': old_owner_phone,
            'previous_owner_email': old_owner_email,

            # New owner
            'customer_name': self.new_customer_name,
            'customer_phone': self.new_customer_phone,
            'customer_email': self.new_customer_email,

            # Transfer history
            'last_transfer_date': self.transfer_date,
            'last_transfer_note': self.transfer_note,
            'ownership_transfer_count':
                reg.ownership_transfer_count + 1,
        })

        # Chatter Message
        reg.message_post(
            body=_(
                """
                <b>Warranty Ownership Transferred</b><br/>
                <b>Previous Owner:</b> %s<br/>
                <b>New Owner:</b> %s<br/>
                <b>Transfer Date:</b> %s<br/>
                <b>Transfer Reason:</b> %s
                """
            ) % (
                old_owner_name,
                self.new_customer_name,
                self.transfer_date,
                self.transfer_note
            )
        )

        return {'type': 'ir.actions.act_window_close'}