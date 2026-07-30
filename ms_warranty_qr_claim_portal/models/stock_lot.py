import uuid
from datetime import date
from odoo import models, fields, api, _

class StockLot(models.Model):
    _inherit = 'stock.lot'

    has_warranty_policy = fields.Boolean(
        string="Has Warranty Policy", 
        compute='_compute_has_warranty_policy'
    )

    qr_token = fields.Char(
        string='Reference QR Token', 
        compute='_compute_qr_token',
        store=True,
        readonly=True,
        copy=False
    )
    
    purpose = fields.Selection([
        ('registration', 'Registration'),
        ('status', 'Status'),
        ('claim', 'Claim'),
        ('warranty_card', 'Warranty Card'),
        ('generic', 'Generic')
    ], string='Purpose', default='registration')

    public_url = fields.Char(
        string='URL', 
        compute='_compute_warranty_qr_url',
        store=False
    )

    live_warranty_status = fields.Selection([
        ('not_found', 'Not Registered'),
        ('pending', 'Pending Approval'),
        ('approved', 'Registered'),
        ('expired', 'Expired'),
        ('rejected', 'Revoked')
    ], string='Warranty Status', compute='_compute_live_warranty_status', store=True, readonly=True)

    registration_id = fields.Many2one(
        'ms.warranty.registration', 
        string='Linked Registration', 
        compute='_compute_linked_registration',
        store=True
    )

    @api.depends('product_id', 'product_id.warranty_policy_id', 'product_id.product_tmpl_id.warranty_policy_id')
    def _compute_has_warranty_policy(self):
        for lot in self:
            policy = getattr(lot.product_id, 'warranty_policy_id', False) or getattr(lot.product_id.product_tmpl_id, 'warranty_policy_id', False)
            lot.has_warranty_policy = bool(policy)

    @api.depends('has_warranty_policy', 'product_id')
    def _compute_qr_token(self):
        for lot in self:
            if lot.has_warranty_policy:
                if not lot.qr_token:
                    lot.qr_token = str(uuid.uuid4()).strip()
            else:
                lot.qr_token = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            product_id = vals.get('product_id')
            if product_id:
                product = self.env['product.product'].browse(product_id)
                policy = getattr(product, 'warranty_policy_id', False) or getattr(product.product_tmpl_id, 'warranty_policy_id', False)
                if policy and not vals.get('qr_token'):
                    vals['qr_token'] = str(uuid.uuid4()).strip()

        records = super(StockLot, self).create(vals_list)
        return records

    @api.depends('name')
    def _compute_linked_registration(self):
        for lot in self:
            if not lot.id:
                lot.registration_id = False
                continue
            reg = self.env['ms.warranty.registration'].sudo().search([
                ('serial_no', '=', lot.id),
                ('state', '=', 'approved')
            ], order='create_date desc, id desc', limit=1)

            if not reg:
                reg = self.env['ms.warranty.registration'].sudo().search([
                    ('serial_no', '=', lot.id),
                    ('state', 'in', ['pending', 'draft', 'expired'])
                ], order='create_date desc, id desc', limit=1)

            lot.registration_id = reg or False

    @api.depends('registration_id', 'registration_id.state', 'registration_id.expiry_date')
    def _compute_live_warranty_status(self):
        today = date.today()
        for lot in self:
            reg = lot.registration_id
            if not reg and lot.id:
                reg = self.env['ms.warranty.registration'].sudo().search([
                    ('serial_no', '=', lot.id),
                    ('state', '!=', 'rejected')
                ], limit=1)

            if not reg:
                lot.live_warranty_status = 'not_found'
            elif reg.state in ['draft', 'pending']:
                lot.live_warranty_status = 'pending'
            elif reg.state == 'rejected':
                lot.live_warranty_status = 'rejected'
            elif reg.state == 'expired' or (reg.expiry_date and reg.expiry_date < today):
                lot.live_warranty_status = 'expired'
            elif reg.state == 'approved':
                lot.live_warranty_status = 'approved'
            else:
                lot.live_warranty_status = 'not_found'

    @api.depends('qr_token', 'purpose', 'has_warranty_policy')
    def _compute_warranty_qr_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for lot in self:
            if lot.has_warranty_policy and lot.qr_token:
                lot.public_url = f"{base_url}/warranty/{lot.purpose or 'registration'}?token={lot.qr_token}"
            else:
                lot.public_url = False
    def get_warranty_qr_url(self):
        self.ensure_one()
        if self.public_url:
            return self.public_url
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        if self.qr_token:
            return f"{base_url}/warranty/registration?token={self.qr_token}"
        return f"{base_url}/warranty/registration?serial_no={self.name}"