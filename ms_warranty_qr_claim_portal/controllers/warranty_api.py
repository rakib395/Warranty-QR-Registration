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
        serial_no = data.get('serial_no') or data.get('token')
        
        if not serial_no:
            return {'status': 'error', 'message': 'Serial number is required.'}
            
        lot = request.env['stock.lot'].sudo().search([
            ('name', '=', serial_no)
        ], limit=1)

        if not lot:
            return {'status': 'error', 'message': 'Invalid Serial Number.'}

        registration = request.env['ms.warranty.registration'].sudo().search([
            ('serial_no', '=', lot.id),
            ('state', '=', 'approved')
        ], limit=1) or request.env['ms.warranty.registration'].sudo().search([
            ('serial_no', '=', lot.id)
        ], order='create_date desc', limit=1)

        live_status = 'not_found'
        if registration:
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

        return {
            'status': 'success',
            'live_status': live_status,
            'lot_id': lot.id,
            'serial_no': lot.name,
            'product_id': lot.product_id.id if lot.product_id else False,
            'product_name': lot.product_id.name if lot.product_id else False,
            'expiry_date': str(registration.expiry_date) if registration and registration.expiry_date else False
        }

    @http.route('/api/warranty/submit', type='json', auth="public", methods=['POST'], csrf=False)
    def api_submit_warranty(self, **kwargs):
        post = self._get_json_payload(kwargs)
        serial_no_str = post.get('serial_no', '').strip() if post.get('serial_no') else False

        if not serial_no_str or serial_no_str == '/':
            return {'status': 'error', 'message': 'Invalid serial number.'}
        
        lot = request.env['stock.lot'].sudo().search([('name', '=', serial_no_str)], limit=1)
        if not lot:
            return {'status': 'error', 'message': 'Serial number not found in system.'}

        existing = request.env['ms.warranty.registration'].sudo().search([
            ('serial_no', '=', lot.id),
            ('state', 'in', ['approved', 'pending', 'draft']) 
        ], limit=1)

        if existing:
            return {'status': 'error', 'message': f'Duplicate or pending registration found. State: {existing.state}'}

        product_product_id = lot.product_id.id

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
                'serial_no': lot.id, 
                'purchase_date': purchase_date_val,
                'dealer_id': int(post.get('dealer_id')) if post.get('dealer_id') else False,
                'invoice_proof': invoice_data,
                'state': target_state,
                'policy_id': policy.id if policy else False,
                'company_id': lot.company_id.id if lot.company_id else request.env.company.id,
            })
            
            return {
                'status': 'success', 
                'message': 'Warranty registered successfully!', 
                'registration_id': registration.id, 
                'state': target_state
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/api/warranty/claim/submit', type='json', auth="public", methods=['POST'], csrf=False)
    def api_submit_claim(self, **kwargs):
        post = self._get_json_payload(kwargs)
        serial_no = post.get('serial_no')

        if not serial_no:
            return {'status': 'error', 'message': 'Missing serial number.'}

        registration = request.env['ms.warranty.registration'].sudo().search([
            ('serial_no.name', '=', serial_no),
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