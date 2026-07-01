import uuid
import qrcode
import base64
from io import BytesIO
from datetime import date
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class WarrantyQRToken(models.Model):
    _name = 'ms.warranty.qr.token'
    _inherit = ['mail.thread']
    _description = 'Warranty QR Token'

    name = fields.Char( string='Name',required=True,default=lambda self: self.env['ir.sequence'].next_by_code('ms.warranty.qr.token') or '/',copy=False, tracking=True)
    token = fields.Char(string='Token', required=True, default=lambda self: str(uuid.uuid4()), copy=False)
    token_hash = fields.Char(string='Token Hash')
    
    product_id = fields.Many2one('product.product', string='Product', tracking=True)
    serial_no = fields.Many2one(
        'stock.lot', 
        string='Serial Number', 
        copy=False,
        tracking=True 
    )
    registration_id = fields.Many2one('ms.warranty.registration', string='Linked Registration', tracking=True)

    company_id = fields.Many2one(
    'res.company', 
    string='Company', 
    required=True, 
    default=lambda self: self.env.company
    )
    
    purpose = fields.Selection([
        ('registration', 'Registration'),
        ('status', 'Status'),
        ('claim', 'Claim'),
        ('warranty_card', 'Warranty Card'),
        ('generic', 'Generic')
    ], string='Purpose', required=True, default='registration', tracking=True)
    
    state = fields.Selection([
        ('new', 'New'),
        ('used', 'Used'),
        ('expired', 'Expired'),
        ('revoked', 'Revoked')
    ], string='Status', default='new', required=True)

    url = fields.Char(string='Public URL', compute='_compute_qr_url')
    qr_code_image = fields.Binary(string='QR Image', compute='_compute_qr_code_image', store=True)
    
    active = fields.Boolean(default=True)
    use_count = fields.Integer(string='Scan Count', compute='_compute_use_count', store=True)

    used_serial_ids = fields.Many2many(
        'stock.lot', 
        compute='_compute_used_serial_ids', 
        string='Serials Helper'
    )

    _sql_constraints = [
        ('unique_token', 'unique(token)', 'This token has already been generated!')
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
                    ('serial_no', '=', record.serial_no.id)
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
    
    @api.depends('state', 'registration_id')
    def _compute_use_count(self):
        for record in self:
            if record.state == 'used' or record.registration_id:
                record.use_count = 1
            else:
                record.use_count = 0

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
        for vals in vals_list:
            if not vals.get('company_id'):
                vals['company_id'] = self.env.company.id
        return super().create(vals_list)
    
    
    @api.constrains('serial_no')
    def _check_duplicate_serial(self):
        for rec in self:
            if not rec.serial_no:
                continue
            
            duplicate = self.search([
                ('serial_no', '=', rec.serial_no.id),
                ('id', '!=', rec._origin.id if rec._origin else rec.id)
            ], limit=1)

            if duplicate:
                raise ValidationError(
                    _("This Serial Number (%s) is already assigned to another QR Token.") % rec.serial_no.name
                )
            

    @api.depends('product_id')
    def _compute_used_serial_ids(self):
        for record in self:
            if record.product_id:
    
                token_domain = [('product_id', '=', record.product_id.id), ('serial_no', '!=', False)]
                if record._origin.id:
                    token_domain.append(('id', '!=', record._origin.id))
                token_used_serials = self.env['ms.warranty.qr.token'].sudo().search(token_domain).mapped('serial_no.id')
            
                reg_domain = [
                    ('product_id', '=', record.product_id.id),
                    ('serial_no', '!=', False),
                    ('state', 'not in', ['rejected'])
                ]
                registered_serial_names = self.env['ms.warranty.registration'].sudo().search(reg_domain).mapped('serial_no')     
             
                registered_serial_ids = self.env['stock.lot'].sudo().search([
                    ('product_id', '=', record.product_id.id),
                    ('name', 'in', registered_serial_names)
                ]).ids

                all_used_ids = list(set(token_used_serials + registered_serial_ids))
                record.used_serial_ids = self.env['stock.lot'].browse(all_used_ids)
            else:
                record.used_serial_ids = self.env['stock.lot']
        
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            self.serial_no = False
            return {'domain': {'serial_no': [('id', '=', False)]}}

        used_tokens = self.env['ms.warranty.qr.token'].sudo().search([
            ('product_id', '=', self.product_id.id),
            ('serial_no', '!=', False)
        ])
        used_serial_ids = used_tokens.mapped('serial_no.id')

        final_serial_domain = [
            ('product_id', '=', self.product_id.id),
            ('id', 'not in', used_serial_ids)
        ]

        lot = self.env['stock.lot'].sudo().search(final_serial_domain, order='id asc', limit=1)
        self.serial_no = lot if lot else False

        return {
            'domain': {
                'serial_no': final_serial_domain
            }
        }