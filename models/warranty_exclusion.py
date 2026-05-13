from odoo import models, fields, api 
class WarrantyExclusion(models.Model):
    _name = 'ms.warranty.exclusion'
    _description = 'Warranty Exclusion'

    policy_id = fields.Many2one('ms.warranty.policy', string='Policy', ondelete='cascade')
    name = fields.Char(string='Excluded Item', required=True)
    description = fields.Text(string='Reason')