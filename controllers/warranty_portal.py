from odoo import http, _
from odoo.http import request
import base64

class WarrantyPublic(http.Controller):

    @http.route(['/warranty/registration'], type='http', auth="public", website=True, sitemap=False)
    def public_warranty_form(self, **post):
        token_str = post.get('token')
        
        qr_token = request.env['ms.warranty.qr.token'].sudo().search([
            ('token', '=', token_str),
            ('active', '=', True)
        ], limit=1)

        if not qr_token:
            return request.render("http_routing.404")
        
        error_status = post.get('error')
        if qr_token.state == 'used' and not error_status:
            error_status = 'already_registered'

        if qr_token.state == 'used' and qr_token.use_count == 0:
            qr_token.sudo().write({'use_count': 1})

        registration = False
        is_dealer_registered = False
        
        if qr_token.state == 'used' and qr_token.serial_no:
            registration = request.env['ms.warranty.registration'].sudo().search([
                ('serial_no', '=', qr_token.serial_no),
                ('state', '=', 'approved')
            ], limit=1)
            
            public_user = request.env.ref('base.public_user')
            if registration and registration.create_uid != public_user:
                is_dealer_registered = True

        products = request.env['product.template'].sudo().search([('sale_ok', '=', True)])
        dealers = request.env['res.partner'].sudo().search([('is_company', '=', True)])
        
        return request.render("ms_warranty_qr_claim_portal.public_registration_template", {
            'products': products,
            'dealers': dealers,
            'error': error_status,
            'token_product_id': qr_token.product_id.id if qr_token.product_id else False,
            'token_serial_no': qr_token.serial_no if qr_token.serial_no else False,
            'current_token': token_str, 
            'token_state': qr_token.state, 
            'is_dealer_registered': is_dealer_registered,
            'product_name': qr_token.product_id.name if qr_token.product_id else False,
            'policy_name': registration.policy_id.name if registration and registration.policy_id else "Standard Warranty",
            'expiry_date': registration.expiry_date if registration else False,
        })

        

    @http.route(['/warranty/submit'], type='http', auth="public", methods=['POST'], website=True)
    def submit_warranty(self, **post):
        token_str = post.get('current_token')
        if not token_str:
            return request.redirect('/')
        
        serial_no = post.get('serial_no')
        if serial_no:
            serial_no = serial_no.strip()

        if not serial_no or serial_no == '/':
            return request.redirect(f'/warranty/registration?token={token_str}&error=invalid_data')
        
        existing_registration = request.env['ms.warranty.registration'].sudo().search([
            ('serial_no', '=', serial_no)
        ], limit=1)

        if existing_registration:
            return request.redirect(f'/warranty/registration?token={token_str}&error=duplicate_serial')
        
        product_id = int(post.get('product_id')) if post.get('product_id') else False
        product = request.env['product.template'].sudo().browse(product_id) if product_id else False
        policy = product.warranty_policy_id if product else False       

        target_state = 'pending'
        if policy and policy.auto_approve_registration:
            target_state = 'approved'

        invoice_file = post.get('invoice_proof')
        invoice_data = False
        if invoice_file:
            invoice_data = base64.b64encode(invoice_file.read())

        vals = {
            'customer_name': post.get('customer_name'),
            'customer_phone': post.get('customer_phone'),
            'customer_email': post.get('customer_email'),
            'product_id': product_id,
            'serial_no': serial_no, 
            'purchase_date': post.get('purchase_date'),
            'dealer_id': int(post.get('dealer_id')) if post.get('dealer_id') else False,
            'invoice_proof': invoice_data,
            'state': target_state,
            'policy_id': policy.id if policy else False,
        }

        try:
            registration = request.env['ms.warranty.registration'].sudo().create(vals)
            
            qr_token = request.env['ms.warranty.qr.token'].sudo().search([('token', '=', token_str)], limit=1)
            if qr_token:
                qr_token.sudo().write({
                    'state': 'used',
                    'registration_id': registration.id,
                    'use_count': qr_token.use_count + 1
                })
        except Exception as e:
            return request.redirect(f'/warranty/registration?token={token_str}&error=invalid_data')

        return request.render("ms_warranty_qr_claim_portal.registration_success_page")