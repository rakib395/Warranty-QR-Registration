# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class WarrantyClaimAssignWizard(models.TransientModel):
    _name = 'warranty.claim.assign.wizard'
    _description = 'Assign Warranty Claim Wizard'

    service_center_id = fields.Many2one(
        'ms.warranty.service.center', 
        string='Service Center', 
        required=True
    )
    technician_id = fields.Many2one(
        'res.users', 
        string='Technician / User', 
        required=True,
        domain="[('share', '=', False)]" 
    )

    def action_assign_claim(self):
        """Submit assignment to the active claim record"""
        self.ensure_one()
        claim_id = self.env.context.get('active_id')
        if not claim_id:
            raise UserError(_("No active claim found for assignment context."))
            
        claim = self.env['ms.warranty.claim'].browse(claim_id)
        claim.action_assign_claim_processing(self.service_center_id, self.technician_id)
        return {'type': 'ir.actions.act_window_close'}