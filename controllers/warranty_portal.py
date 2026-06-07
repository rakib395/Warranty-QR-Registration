# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
import base64
from datetime import date
from odoo.exceptions import ValidationError, UserError

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
            
            if not registration:
                registration = request.env['ms.warranty.registration'].sudo().search([
                    ('serial_no', '=', qr_token.serial_no)
                ], order='create_date desc', limit=1)
            
            public_user = request.env.ref('base.public_user')
            if registration and registration.state == 'approved' and registration.create_uid != public_user:
                is_dealer_registered = True

        live_status = 'not_found'
        if qr_token.state == 'new':
            live_status = 'not_found'
        elif registration:
            if registration.state in ['draft', 'pending']:
                live_status = 'pending'
            elif registration.state == 'rejected':
                live_status = 'rejected'
            elif registration.state == 'approved':
                if registration.expiry_date and registration.expiry_date < date.today():
                    live_status = 'expired'
                else:
                    live_status = 'approved'
            elif registration.state == 'expired':
                live_status = 'expired'

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
            'live_status': live_status,
            'claim_success': post.get('claim_success'),
            'claim_num': post.get('claim_num'), 
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
            ('serial_no', '=', serial_no),
            ('state', 'in', ['approved', 'pending', 'draft']) 
        ], limit=1)

        if existing_registration:
            if existing_registration.state == 'approved':
                return request.redirect(f'/warranty/registration?token={token_str}&error=duplicate_serial')
            else:
                return request.redirect(f'/warranty/registration?token={token_str}&error=pending_registration')
        
        template_id = int(post.get('product_id')) if post.get('product_id') else False
        product_product_id = False

        if template_id:
            product_product = request.env['product.product'].sudo().search([
                ('product_tmpl_id', '=', template_id)
            ], limit=1)
            
            if product_product:
                product_product_id = product_product.id
            else:
                product_template = request.env['product.template'].sudo().browse(template_id)
                if product_template.product_variant_id:
                    product_product_id = product_template.product_variant_id.id

        if not product_product_id:
            qr_token = request.env['ms.warranty.qr.token'].sudo().search([('token', '=', token_str)], limit=1)
            if qr_token and qr_token.product_id:
                product_product_id = qr_token.product_id.id

        if not product_product_id:
            return request.redirect(f'/warranty/registration?token={token_str}&error=invalid_data')

        product_product_obj = request.env['product.product'].sudo().browse(product_product_id)
        policy = product_product_obj.product_tmpl_id.warranty_policy_id if product_product_obj else False       

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
            'product_id': product_product_id,
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
        except ValidationError as ve:
            print("=== WARRANTY SUBMISSION VALIDATION ERROR ===", str(ve))
            return request.redirect(f'/warranty/registration?token={token_str}&error=duplicate_serial')
        except Exception as e:
            print("=== WARRANTY SUBMISSION UNKNOWN ERROR ===", str(e))
            return request.redirect(f'/warranty/registration?token={token_str}&error=invalid_data')

        return request.render("ms_warranty_qr_claim_portal.registration_success_page")

    @http.route(['/warranty/claim/submit'], type='http', auth="public", methods=['POST'], website=True)
    def submit_warranty_claim(self, **post):
        token_str = post.get('current_token')
        serial_no = post.get('serial_no')
        
        if not token_str or not serial_no:
            return request.redirect('/')
        
        registration = request.env['ms.warranty.registration'].sudo().search([
            ('serial_no', '=', serial_no),
            ('state', '=', 'approved')
        ], limit=1)

        if not registration or (registration.expiry_date and registration.expiry_date < date.today()):
            return request.redirect(f'/warranty/registration?token={token_str}&error=not_eligible')

        photo_file = post.get('product_photo')
        photo_data = False
        if photo_file:
            photo_data = base64.b64encode(photo_file.read())

        invoice_file = post.get('invoice_proof')
        invoice_data = False
        if invoice_file:
            invoice_data = base64.b64encode(invoice_file.read())

        vals = {
            'registration_id': registration.id,
            'issue_category': post.get('issue_category', 'hardware'),
            'description': post.get('description'),
            'preferred_contact': post.get('preferred_contact'),
            'product_photo': photo_data,
            'invoice_proof': invoice_data,
            'state': 'submitted',
        }

        try:
            claim = request.env['ms.warranty.claim'].sudo().create(vals)
            return request.redirect(f'/warranty/registration?token={token_str}&claim_success=1&claim_num={claim.name}')
        except Exception as e:
            print("=== WARRANTY CLAIM SUBMISSION ERROR ===", str(e))
            return request.redirect(f'/warranty/registration?token={token_str}&error=claim_failed')