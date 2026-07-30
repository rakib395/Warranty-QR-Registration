from odoo import models, fields, api

class ClaimReceiveWizard(models.TransientModel):
    _name = 'claim.receive.wizard'
    _description = 'Claim Receive Wizard'

    claim_id = fields.Many2one('ms.warranty.claim', string='Claim', required=True)
    received_by_id = fields.Many2one(
        'res.users', 
        string='Received By', 
        default=lambda self: self.env.user, 
        required=True
    )

    def action_confirm_receive(self):
        self.ensure_one()
        self.claim_id.write({
            'received_by_id': self.received_by_id.id,
            'state': 'received'  
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }