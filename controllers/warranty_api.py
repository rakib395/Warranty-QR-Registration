# -*- coding: utf-8 -*-
import base64
import logging
from datetime import date, datetime
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class WarrantyJsonAPI(http.Controller):

    def _get_json_payload(self, kwargs):
        if kwargs:
            return kwargs
        try:
            return request.get_json_data() or {}
        except Exception:
            return {}

    @http.route('/api/warranty/validate-token', type='json', auth="public", methods=['POST'], csrf=False)
    def api_validate_token(self, **kwargs):
        data = self._get_json_payload(kwargs)
        token_str = data.get('token')
        
        if not token_str:
            return {'status': 'error', 'message': 'Token is required.'}
            
        qr_token = request.env['ms.warranty.qr.token'].sudo().search([
            ('token', '=', token_str),
            ('active', '=', True)
        ], limit=1)

        if not qr_token:
            return {'status': 'error', 'message': 'Invalid token or inactive.'}

        registration = False
        if qr_token.state == 'used' and qr_token.serial_no:
            registration = request.env['ms.warranty.registration'].sudo().search([
                ('serial_no', '=', qr_token.serial_no),
                ('state', '=', 'approved')
            ], limit=1) or request.env['ms.warranty.registration'].sudo().search([
                ('serial_no', '=', qr_token.serial_no)
            ], order='create_date desc', limit=1)

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

        return {
            'status': 'success',
            'token_state': qr_token.state,
            'live_status': live_status,
            'serial_no': qr_token.serial_no or False,
            'product_name': qr_token.product_id.name if qr_token.product_id else False,
            'expiry_date': str(registration.expiry_date) if registration and registration.expiry_date else False
        }

    @http.route('/api/warranty/submit', type='json', auth="public", methods=['POST'], csrf=False)
    def api_submit_warranty(self, **kwargs):
        post = self._get_json_payload(kwargs)
        token_str = post.get('current_token')
        serial_no = post.get('serial_no', '').strip() if post.get('serial_no') else False

        if not token_str or not serial_no or serial_no == '/':
            return {'status': 'error', 'message': 'Invalid token or serial number.'}
        
        existing = request.env['ms.warranty.registration'].sudo().search([
            ('serial_no', '=', serial_no),
            ('state', 'in', ['approved', 'pending', 'draft']) 
        ], limit=1)

        if existing:
            return {'status': 'error', 'message': f'Duplicate or pending registration found. State: {existing.state}'}
        
        qr_token = request.env['ms.warranty.qr.token'].sudo().search([('token', '=', token_str)], limit=1)
        if not qr_token:
            return {'status': 'error', 'message': 'QR Token not found.'}

        template_id = int(post.get('product_id')) if post.get('product_id') else False
        product_product_id = False

        if template_id:
            product_product = request.env['product.product'].sudo().search([('product_tmpl_id', '=', template_id)], limit=1)
            product_product_id = product_product.id if product_product else request.env['product.template'].sudo().browse(template_id).product_variant_id.id
        
        if not product_product_id and qr_token.product_id:
            product_product_id = qr_token.product_id.product_variant_id.id if qr_token.product_id._name == 'product.template' else qr_token.product_id.id

        if not product_product_id:
            return {'status': 'error', 'message': 'Product could not be resolved.'}

        product_obj = request.env['product.product'].sudo().browse(product_product_id)
        policy = product_obj.product_tmpl_id.warranty_policy_id
        target_state = 'approved' if policy and policy.auto_approve_registration else 'pending'

        invoice_data = post.get('invoice_proof')
        if invoice_data and isinstance(invoice_data, str) and ',' in invoice_data:
            invoice_data = invoice_data.split(',')[1]

        purchase_date_val = date.today()
        if post.get('purchase_date'):
            try:
                purchase_date_val = datetime.strptime(post.get('purchase_date'), '%Y-%m-%d').date()
            except Exception:
                purchase_date_val = date.today()

        try:
            registration = request.env['ms.warranty.registration'].sudo().create({
                'customer_name': post.get('customer_name'),
                'customer_phone': post.get('customer_phone'),
                'customer_email': post.get('customer_email'),
                'product_id': product_product_id,
                'serial_no': serial_no, 
                'purchase_date': purchase_date_val,
                'dealer_id': int(post.get('dealer_id')) if post.get('dealer_id') else False,
                'invoice_proof': invoice_data,
                'state': target_state,
                'policy_id': policy.id if policy else False,
                'company_id': qr_token.company_id.id if getattr(qr_token, 'company_id', False) else request.env.company.id,
            })
            
            qr_token.sudo().write({
                'state': 'used',
                'registration_id': registration.id,
                'use_count': qr_token.use_count + 1,
                'serial_no': serial_no
            })
            return {'status': 'success', 'message': 'Warranty registered successfully!', 'registration_id': registration.id, 'state': target_state}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/api/warranty/claim/submit', type='json', auth="public", methods=['POST'], csrf=False)
    def api_submit_claim(self, **kwargs):
        post = self._get_json_payload(kwargs)
        token_str = post.get('current_token')
        serial_no = post.get('serial_no')

        if not token_str or not serial_no:
            return {'status': 'error', 'message': 'Missing token or serial number.'}

        registration = request.env['ms.warranty.registration'].sudo().search([
            ('serial_no', '=', serial_no),
            ('state', '=', 'approved')
        ], limit=1)

        if not registration or (registration.expiry_date and registration.expiry_date < date.today()):
            return {'status': 'error', 'message': 'Product is not eligible for warranty claim.'}

        photo_data = post.get('product_photo') 
        if photo_data and isinstance(photo_data, str) and ',' in photo_data:
            photo_data = photo_data.split(',')[1]

        invoice_data = post.get('invoice_proof')
        if invoice_data and isinstance(invoice_data, str) and ',' in invoice_data:
            invoice_data = invoice_data.split(',')[1]

        try:
            claim = request.env['ms.warranty.claim'].sudo().create({
                'registration_id': registration.id,
                'issue_category': post.get('issue_category', 'hardware'),
                'description': post.get('description'),
                'preferred_contact': post.get('preferred_contact'),
                'product_photo': photo_data,
                'invoice_proof': invoice_data,
                'state': 'submitted',
                'claim_source': 'public',
                'company_id': registration.company_id.id if registration.company_id else request.env.company.id,
            })
            return {'status': 'success', 'claim_number': claim.name, 'message': 'Claim submitted successfully.'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/api/service-center/claims-list', type='json', auth="user", methods=['POST'], csrf=False)
    def api_service_center_claims(self, **kwargs):
        user = request.env.user
        service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)
        
        if not service_center:
            return {'status': 'error', 'message': 'User is not linked to any service center.'}

        claims = request.env['ms.warranty.claim'].sudo().search([
            ('service_center_id', '=', service_center.id)
        ], order="create_date desc")

        claims_data = []
        for claim in claims:
            claims_data.append({
                'id': claim.id,
                'name': claim.name,
                'state': claim.state,
                'issue_category': claim.issue_category,
                'customer_name': claim.registration_id.customer_name if claim.registration_id else False,
                'serial_no': claim.registration_id.serial_no if claim.registration_id else False,
            })
        return {'status': 'success', 'service_center': service_center.name, 'claims': claims_data}

    @http.route('/api/service-center/update-inspection', type='json', auth="user", methods=['POST'], csrf=False)
    def api_update_inspection(self, **kwargs):
        post = self._get_json_payload(kwargs)
        claim_id = int(post.get('claim_id')) if post.get('claim_id') else False
        
        user = request.env.user
        claim = request.env['ms.warranty.claim'].sudo().browse(claim_id)
        user_service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)

        if not claim.exists() or not user_service_center or claim.service_center_id.id != user_service_center.id:
            return {'status': 'error', 'message': 'Unauthorized or claim does not exist.'}

        try:
            claim.sudo().write({
                'diagnosis': post.get('diagnosis'),
                'inspection_result': post.get('inspection_result'),
                'is_covered': True if post.get('is_covered') == '1' or post.get('is_covered') is True else False,
            })
            return {'status': 'success', 'message': 'Inspection updated successfully.'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}