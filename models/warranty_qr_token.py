import uuid
import qrcode
import base64
from io import BytesIO
from datetime import date
from odoo import models, fields, api, _

class WarrantyQRToken(models.Model):
    _name = 'ms.warranty.qr.token'
    _description = 'Warranty QR Token'

    name = fields.Char( string='Name',required=True,default=lambda self: self.env['ir.sequence'].next_by_code('ms.warranty.qr.token') or '/',copy=False)
    token = fields.Char(string='Token', required=True, default=lambda self: str(uuid.uuid4()), copy=False)
    token_hash = fields.Char(string='Token Hash')
    
    product_id = fields.Many2one('product.product', string='Product')
    serial_no = fields.Char( string='Serial Number', copy=False)
    registration_id = fields.Many2one('ms.warranty.registration', string='Linked Registration')
    
    purpose = fields.Selection([
        ('registration', 'Registration'),
        ('status', 'Status'),
        ('claim', 'Claim'),
        ('warranty_card', 'Warranty Card'),
        ('generic', 'Generic')
    ], string='Purpose', required=True, default='registration')
    
    state = fields.Selection([
        ('new', 'New'),
        ('used', 'Used'),
        ('expired', 'Expired'),
        ('revoked', 'Revoked')
    ], string='Status', default='new', required=True)

    url = fields.Char(string='Public URL', compute='_compute_qr_url')
    qr_code_image = fields.Binary(string='QR Image', compute='_compute_qr_code_image', store=True)
    
    active = fields.Boolean(default=True)
    use_count = fields.Integer(string='Scan Count', default=0)

    _sql_constraints = [
        ('uniq_serial_product', 'unique(product_id, serial_no)', 'Duplicate serial not allowed!')
    ]

    live_warranty_status = fields.Selection([
        ('not_found', 'Not Registered'),
        ('pending', 'Pending Approval'),
        ('approved', 'Active / Valid'),
        ('expired', 'Expired'),
        ('rejected', 'Rejected')
    ], string='Live Warranty Status', compute='_compute_live_warranty_status')

    @api.depends('state', 'serial_no', 'registration_id', 'registration_id.state', 'registration_id.expiry_date')
    def _compute_live_warranty_status(self):
        today = date.today()
        for record in self:
            if record.state == 'new' or not record.serial_no:
                record.live_warranty_status = 'not_found'
                continue

            reg = record.registration_id
            if not reg:
                reg = self.env['ms.warranty.registration'].sudo().search([
                    ('serial_no', '=', record.serial_no)
                ], limit=1)

            if not reg:
                record.live_warranty_status = 'not_found'
            elif reg.state == 'draft' or reg.state == 'pending':
                record.live_warranty_status = 'pending'
            elif reg.state == 'rejected':
                record.live_warranty_status = 'rejected'
            elif reg.state == 'expired' or (reg.expiry_date and reg.expiry_date < today):
                record.live_warranty_status = 'expired'
            elif reg.state == 'approved':
                record.live_warranty_status = 'approved'
            else:
                record.live_warranty_status = 'not_found'

    @api.depends('token', 'purpose')
    def _compute_qr_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if record.token:
                record.url = f"{base_url}/warranty/{record.purpose}?token={record.token}"
            else:
                record.url = False

    @api.depends('url')
    def _compute_qr_code_image(self):
        for record in self:
            if not record.url:
                record.qr_code_image = False
                continue

            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(record.url)
            qr.make(fit=True)

            img = qr.make_image(fill='black', back_color='white')
            buffer = BytesIO()
            img.save(buffer, format="PNG")

            record.qr_code_image = base64.b64encode(buffer.getvalue())

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            self.serial_no = False
            return
        
        used = set(self.env['ms.warranty.qr.token'].sudo().search([
            ('product_id', '=', self.product_id.id),
            ('serial_no', '!=', False)
        ]).mapped('serial_no'))

        lot = self.env['stock.lot'].sudo().search([
            ('product_id', '=', self.product_id.id),
            ('name', '!=', False),
            ('name', 'not in', list(used))
        ], order='id asc', limit=1)

        self.serial_no = lot.name if lot else False