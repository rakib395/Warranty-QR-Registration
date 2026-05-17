import uuid
import qrcode
import base64
from io import BytesIO
from odoo import models, fields, api, _

class WarrantyQRToken(models.Model):
    _name = 'ms.warranty.qr.token'
    _description = 'Warranty QR Token'

    name = fields.Char(string='Name', required=True)
    token = fields.Char(string='Token', required=True, default=lambda self: str(uuid.uuid4()), copy=False)
    token_hash = fields.Char(string='Token Hash')
    
    product_id = fields.Many2one('product.product', string='Product')
    serial_no = fields.Char(string='Serial Number')
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

    # US-002: Generate secure URL using token instead of internal ID
    @api.depends('token', 'purpose')
    def _compute_qr_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.url = f"{base_url}/warranty/{record.purpose}?token={record.token}"

    # QR Code image generation
    @api.depends('url')
    def _compute_qr_code_image(self):
        for record in self:
            if record.url:
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(record.url)
                qr.make(fit=True)
                img = qr.make_image(fill='black', back_color='white')
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                record.qr_code_image = base64.b64encode(buffer.getvalue())