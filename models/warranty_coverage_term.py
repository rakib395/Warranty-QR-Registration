# -*- coding: utf-8 -*-
from odoo import models, fields, api 

class WarrantyCoverageTerm(models.Model):
    _name = 'ms.warranty.coverage.term'
    _description = 'Warranty Coverage Term'

    policy_id = fields.Many2one('ms.warranty.policy', string='Policy', ondelete='cascade')
    name = fields.Char(string='Covered Item', required=True)
    description = fields.Text(string='Details')