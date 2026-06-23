# -*- coding: utf-8 -*-
import base64
import logging
from datetime import date
from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError, UserError
_logger = logging.getLogger(__name__)

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
        
        current_user = request.env.user
        is_dealer = False
        if current_user and current_user != request.env.ref('base.public_user'):
            is_dealer = True

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
            'is_dealer': is_dealer,
            'registration': registration,
            'claim_ids': registration.claim_ids if registration and hasattr(registration, 'claim_ids') else False,
        })

    @http.route(['/warranty/submit'], type='http', auth="public", methods=['POST'], website=True, csrf=False)
    def submit_warranty(self, **post):
        _logger.info("RECEIVED POST DATA: %s", post)
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

        qr_token = request.env['ms.warranty.qr.token'].sudo().search([('token', '=', token_str)], limit=1)

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
                if qr_token.product_id._name == 'product.template':
                    product_product = request.env['product.product'].sudo().search([
                        ('product_tmpl_id', '=', qr_token.product_id.id)
                    ], limit=1)
                    product_product_id = product_product.id if product_product else qr_token.product_id.product_variant_id.id
                else:
                    product_product_id = qr_token.product_id.id

        if not product_product_id:
            _logger.error("Warranty submission failed: product_product_id could not be resolved.")
            return request.redirect(f'/warranty/registration?token={token_str}&error=invalid_data')

        product_product_obj = request.env['product.product'].sudo().browse(product_product_id)
        policy = product_product_obj.product_tmpl_id.warranty_policy_id if product_product_obj else False       

        target_state = 'pending'
        if policy and policy.auto_approve_registration:
            target_state = 'approved'

        invoice_file = post.get('invoice_proof')
        invoice_data = False
       
        if invoice_file and hasattr(invoice_file, 'read'):
            read_data = invoice_file.read()
            if read_data:
                invoice_data = base64.b64encode(read_data)

        company_id = qr_token.company_id.id if qr_token and getattr(qr_token, 'company_id', False) else request.env.company.id

        vals = {
            'customer_name': post.get('customer_name'),
            'customer_phone': post.get('customer_phone'),
            'customer_email': post.get('customer_email'),
            'product_id': product_product_id,
            'serial_no': serial_no, 
            'purchase_date': post.get('purchase_date') or date.today(),
            'dealer_id': int(post.get('dealer_id')) if post.get('dealer_id') else False,
            'invoice_proof': invoice_data,
            'state': target_state,
            'policy_id': policy.id if policy else False,
            'company_id': company_id,
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
            _logger.error("Warranty registration validation error: %s", str(ve))
            return request.redirect(f'/warranty/registration?token={token_str}&error=duplicate_serial')
        except Exception as e:
            _logger.error("Warranty registration creation failed directly at database level: %s", str(e))
            return request.redirect(f'/warranty/registration?token={token_str}&error=invalid_data')

        return request.render("ms_warranty_qr_claim_portal.registration_success_page")
    @http.route(['/warranty/claim/submit'], type='http', auth="public", methods=['POST'], website=True, csrf=False)
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

        current_user = request.env.user
        public_user = request.env.ref('base.public_user')
        is_dealer = current_user and current_user != public_user
        
        if is_dealer and registration.dealer_id and registration.dealer_id.id != current_user.partner_id.id:
            return request.redirect(f'/warranty/registration?token={token_str}&error=not_eligible')

        photo_file = post.get('product_photo')
        photo_data = False
        if photo_file and hasattr(photo_file, 'read'):
            read_photo = photo_file.read()
            if read_photo:
                photo_data = base64.b64encode(read_photo).decode('utf-8')

        invoice_file = post.get('invoice_proof')
        invoice_data = False
        if invoice_file and hasattr(invoice_file, 'read'):
            read_invoice = invoice_file.read()
            if read_invoice:
                invoice_data = base64.b64encode(read_invoice).decode('utf-8')

        source_val = 'dealer' if is_dealer else 'public'
        submitted_by_val = current_user.id if is_dealer else False

        claim_company_id = registration.company_id.id if registration.company_id else request.env.company.id

        vals = {
            'registration_id': registration.id,
            'issue_category': post.get('issue_category', 'hardware'),
            'description': post.get('description'),
            'preferred_contact': post.get('preferred_contact'),
            'product_photo': photo_data,
            'invoice_proof': invoice_data,
            'state': 'submitted',
            'claim_source': source_val,                                        
            'submitted_by_id': submitted_by_val,
            'company_id': claim_company_id,          
        }

        try:
            claim = request.env['ms.warranty.claim'].sudo().create(vals)
            return request.redirect(f'/warranty/registration?token={token_str}&claim_success=1&claim_num={claim.name}')
        except Exception as e:
            _logger.error("Warranty claim submission failed: %s", str(e))
            return request.redirect(f'/warranty/registration?token={token_str}&error=claim_failed')

    @http.route(['/warranty/warranty/claim/chargeable_approve', '/warranty/claim/chargeable_approve'], type='http', auth="user", methods=['GET', 'POST'], website=True, csrf=False)
    def approve_chargeable_repair(self, **post):
        token_str = post.get('current_token')
        claim_id = int(post.get('claim_id')) if post.get('claim_id') else False
        
        if claim_id:
            claim = request.env['ms.warranty.claim'].sudo().browse(claim_id)
            if claim.exists():
                claim.sudo().write({'customer_approved': True})
                if token_str:
                    return request.redirect(f'/warranty/registration?token={token_str}&claim_success=1&claim_num={claim.name}')
                return request.redirect('/my/service-center/claims?success=approved')
        
        return request.redirect('/')

class WarrantyServiceCenterPortal(http.Controller):

    @http.route(['/my/service-center/claims'], type='http', auth="user", website=True)
    def warranty_service_center_portal(self, **kw):
        user = request.env.user
        service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)
        
        if not service_center:
            _logger.warning("User %s is not linked to any service center.", user.name)
            return request.redirect('/my?error=no_service_center')
            
        domain = [('service_center_id', '=', service_center.id)]
        claims = request.env['ms.warranty.claim'].sudo().search(domain, order="create_date desc")
        
        return request.render('ms_warranty_qr_claim_portal.service_center_claims_list_template', {
            'claims': claims,
            'today': date.today(),
            'error': kw.get('error'),
            'success': kw.get('success'),
        })

    @http.route(['/my/service-center/claim/<int:claim_id>'], type='http', auth="user", website=True)
    def service_center_claim_detail(self, claim_id, **kw):
        user = request.env.user
        claim = request.env['ms.warranty.claim'].sudo().browse(claim_id)
        user_service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)
        
        if not claim.exists() or not user_service_center or claim.service_center_id.id != user_service_center.id:
            return request.render("http_routing.403")
        
        products = request.env['product.product'].sudo().search([('sale_ok', '=', True)])

        return request.render("ms_warranty_qr_claim_portal.service_center_claim_detail_template", {
            'claim': claim,
            'products': products,
            'today': date.today(),
            'error': kw.get('error'),
            'success': kw.get('success'),
        })

    @http.route(['/my/service-center/claim/update_inspection'], type='http', auth="user", methods=['POST'], website=True, csrf=False)
    def update_inspection(self, **post):
        claim_id = int(post.get('claim_id'))
        user = request.env.user
        claim = request.env['ms.warranty.claim'].sudo().browse(claim_id)
        user_service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)

        if not claim.exists() or not user_service_center or claim.service_center_id.id != user_service_center.id:
            return request.render("http_routing.403")

        vals = {
            'diagnosis': post.get('diagnosis'),
            'inspection_result': post.get('inspection_result'),
            'is_covered': True if post.get('is_covered') == '1' else False,
        }
        claim.sudo().write(vals)
        return request.redirect(f'/my/service-center/claim/{claim_id}?success=inspection_updated')

    @http.route(['/my/service-center/claim/add_lines'], type='http', auth="user", methods=['POST'], website=True, csrf=False)
    def add_repair_lines(self, **post):
        claim_id = int(post.get('claim_id'))
        user = request.env.user
        claim = request.env['ms.warranty.claim'].sudo().browse(claim_id)
        user_service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)

        if not claim.exists() or not user_service_center or claim.service_center_id.id != user_service_center.id:
            return request.render("http_routing.403")

        part_product_ids = request.httprequest.form.getlist('part_product_id')
        part_qtys = request.httprequest.form.getlist('part_qty')
        labor_notes = request.httprequest.form.getlist('labor_note')
        labor_costs = request.httprequest.form.getlist('labor_cost')

        for prod_id, qty in zip(part_product_ids, part_qtys):
            if prod_id and qty:
                request.env['ms.warranty.claim.part.line'].sudo().create({
                    'claim_id': claim.id,
                    'product_id': int(prod_id),
                    'quantity': float(qty),
                })

        for note, cost in zip(labor_notes, labor_costs):
            if note and cost:
                request.env['ms.warranty.claim.labor.line'].sudo().create({
                    'claim_id': claim.id,
                    'description': note,
                    'labor_cost': float(cost),
                })

        if post.get('action_submit') == 'resolved':
            claim.sudo().write({'state': 'resolved'})
            return request.redirect('/my/service-center/claims?success=claim_resolved')

        return request.redirect(f'/my/service-center/claim/{claim_id}?success=lines_added')

    @http.route(['/my/service-center/claim/convert_chargeable'], type='http', auth="user", methods=['POST'], website=True, csrf=False)
    def convert_chargeable(self, **post):
        claim_id = int(post.get('claim_id'))
        user = request.env.user
        claim = request.env['ms.warranty.claim'].sudo().browse(claim_id)
        user_service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)

        if not claim.exists() or not user_service_center or claim.service_center_id.id != user_service_center.id:
            return request.render("http_routing.403")

        estimated_cost = float(post.get('estimated_cost', 0.0))
        claim.sudo().write({
            'is_covered': False,
            'estimated_cost': estimated_cost,
            'customer_approved': False
        })
        return request.redirect(f'/my/service-center/claim/{claim_id}?success=converted_chargeable')

    @http.route(['/my/service-center/claim/reject'], type='http', auth="user", methods=['POST'], website=True, csrf=False)
    def reject_claim(self, **post):
        claim_id = int(post.get('claim_id'))
        user = request.env.user
        claim = request.env['ms.warranty.claim'].sudo().browse(claim_id)
        user_service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)

        if not claim.exists() or not user_service_center or claim.service_center_id.id != user_service_center.id:
            return request.render("http_routing.403")

        rejection_reason = post.get('rejection_reason')
        if not rejection_reason or not rejection_reason.strip():
            return request.redirect(f'/my/service-center/claim/{claim_id}?error=missing_reason')

        claim.sudo().write({
            'state': 'rejected',
            'rejection_reason': rejection_reason
        })
        return request.redirect('/my/service-center/claims?success=claim_rejected')