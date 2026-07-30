# -*- coding: utf-8 -*-
import re
import base64
import logging
from odoo import tools
from datetime import date
from odoo import http, _
from odoo.http import request
from dateutil.relativedelta import relativedelta
from odoo.http import request, content_disposition
from odoo.exceptions import ValidationError, UserError
_logger = logging.getLogger(__name__)


class WarrantyPublic(http.Controller):

    @http.route(['/warranty/get_center_address'], type='jsonrpc', auth="public", methods=['POST'], csrf=False)
    def get_center_address(self, center_id, **kw):
        _logger.info("Center ID received: %s", center_id)
        if not center_id:
            return {'status': 'error', 'address': ''}
        
        try:
            center = request.env['ms.warranty.service.center'].sudo().browse(int(center_id))
            if center.exists():
                _logger.info("Found Center: %s - Address: %s", center.name, center.address)
                return {
                    'status': 'success', 
                    'address': center.address or 'Address details not specified.'
                }
        except Exception as e:
            _logger.error("Error fetching service center address: %s", str(e))
            
        return {'status': 'error', 'address': ''}

    @http.route(['/warranty/registration'], type='http', auth="public", website=True, csrf=False)
    def public_warranty_form(self, **post):
        token_str = post.get('token')

        if not token_str:
            _logger.warning("Warranty Registration page accessed without token in URL query params.")
            return request.render("http_routing.404")

        lot = request.env['stock.lot'].sudo().search([
            ('qr_token', '=', token_str.strip())
        ], limit=1)

        if not lot:
            _logger.error("Invalid Warranty Serial Token searched: %s", token_str)
            return request.render("http_routing.404")

        product = lot.product_id
        policy = getattr(product, 'warranty_policy_id', False) or getattr(product.product_tmpl_id, 'warranty_policy_id', False) if product else False

        error_status = post.get('error')
        live_status = 'not_found'
        expiry_date = False

        registration = request.env['ms.warranty.registration'].sudo().search([
            ('serial_no', '=', lot.id)
        ], order='create_date desc', limit=1)

        sale_order = False
        move_lines = request.env['stock.move.line'].sudo().search([
            ('lot_id', '=', lot.id),
            ('state', '=', 'done')
        ])
        
        sale_orders = request.env['sale.order'].sudo()
        for ml in move_lines:
            sale_line = ml.move_id.sale_line_id
            if sale_line and sale_line.order_id:
                sale_orders |= sale_line.order_id
                
        valid_orders = sale_orders.filtered(lambda o: o.state in ['sale', 'done'])
        if valid_orders:
            sale_order = valid_orders[0]

        if sale_order and policy and not registration:
            purchase_date = sale_order.date_order.date() if sale_order.date_order else False
            warranty_years = getattr(policy, 'duration_years', 0)
            
            if purchase_date and warranty_years > 0:
                expiry_date = purchase_date + relativedelta(years=warranty_years)
                
                if date.today() > expiry_date:
                    error_status = 'warranty_expired'
                    live_status = 'expired'
                    return request.render("ms_warranty_qr_claim_portal.public_registration_template", {
                        'error': error_status,
                        'current_token': token_str,
                        'token_state': 'used' if registration else 'new',
                        'live_status': live_status,
                        'expiry_date': expiry_date,
                        'product_name': product.name if product else False,
                        'token_serial_no': lot.name,
                        'token_id': lot.id,
                        'policy_name': policy.name if policy else "Standard Warranty",
                    })

        is_dealer_registered = False
        if registration:
            expiry_date = registration.expiry_date or expiry_date
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

            public_user = request.env.ref('base.public_user')
            if registration.state == 'approved' and registration.create_uid != public_user:
                is_dealer_registered = True
        else:
            if live_status != 'expired':
                live_status = 'not_found'

        if registration and not error_status:
            error_status = 'already_registered'

        products = request.env['product.template'].sudo().search([('sale_ok', '=', True)])
        dealers = request.env['res.partner'].sudo().search([('is_company', '=', True)])
        countries = request.env['res.country'].sudo().search([])
        courier_services = request.env['warranty.courier.service'].sudo().search([('active', '=', True)])

        current_user = request.env.user
        is_dealer = current_user and current_user != request.env.ref('base.public_user')

        processed_claims = []
        if registration and hasattr(registration, 'claim_ids') and registration.claim_ids:
            for claim in registration.claim_ids:
                state_label = dict(claim._fields['state'].selection).get(claim.state, claim.state) or ""
                pretty_state = state_label.replace('_', ' ').title() if state_label else claim.state.replace('_', ' ').title()
                logistic_label = "N/A"
                if hasattr(claim, 'delivery_method') and claim._fields.get('delivery_method'):
                    logistic_label = dict(claim._fields.get('delivery_method').selection).get(claim.delivery_method, "N/A")

                processed_claims.append({
                    'id': claim.id,
                    'name': claim.name,
                    'pretty_state': pretty_state,
                    'rma_number': getattr(claim, 'rma_number', claim.name) or claim.name,
                    'logistic_status': logistic_label,
                })

        can_submit_claim = True
        if registration and hasattr(registration, 'claim_ids') and registration.claim_ids:
            active_claim = registration.claim_ids.filtered(lambda c: c.state != 'delivered')
            if active_claim:
                can_submit_claim = False

        return request.render("ms_warranty_qr_claim_portal.public_registration_template", {
            'products': products,
            'dealers': dealers,
            'countries': countries,
            'courier_services': courier_services,
            'error': error_status,
            'token_product_id': product.id if product else False,
            'token_serial_no': lot.name,
            'current_token': token_str,
            'token_state': 'used' if registration else 'new',
            'is_dealer_registered': is_dealer_registered,
            'product_name': product.name if product else False,
            'policy_name': registration.policy_id.name if registration and registration.policy_id else (policy.name if policy else "Standard Warranty"),
            'expiry_date': expiry_date,
            'live_status': live_status,
            'claim_success': post.get('claim_success'),
            'claim_num': post.get('claim_num'),
            'is_dealer': is_dealer,
            'registration': registration,
            'claim_ids': registration.claim_ids if registration and hasattr(registration, 'claim_ids') else False,
            'processed_claims': processed_claims,
            'registration_id': registration.id if registration else False,
            'token_id': lot.id, 
            'can_submit_claim': can_submit_claim,
            'rejection_reason': registration.rejection_reason if registration and hasattr(registration, 'rejection_reason') else False,
            'require_reg_invoice': policy.require_reg_invoice if policy else False,
            'require_claim_invoice': registration.policy_id.require_claim_invoice if registration and registration.policy_id else (policy.require_claim_invoice if policy else False),
        })

    @http.route('/warranty/claim/form/<int:token_id>', type='http', auth='public', website=True)
    def warranty_claim_form_view(self, token_id, **kw):
        lot = request.env['stock.lot'].sudo().browse(token_id)
        if not lot.exists():
            return request.render("http_routing.404")

        registration = request.env['ms.warranty.registration'].sudo().search([
            ('serial_no', '=', lot.id),
            ('state', '=', 'approved')
        ], limit=1)
        
        if not registration:
            registration = request.env['ms.warranty.registration'].sudo().search([
                ('serial_no', '=', lot.id)
            ], order='create_date desc', limit=1)

        current_user = request.env.user
        is_dealer = current_user and current_user != request.env.ref('base.public_user')
        
        service_centers = request.env['ms.warranty.service.center'].sudo().search([])

        policy = registration.policy_id if registration else False
        require_claim_invoice = policy.require_claim_invoice if policy else False

        vals = {
            'token_id': lot.id,
            'current_token': lot.qr_token, 
            'token_serial_no': lot.id,
            'is_dealer': is_dealer,
            'registration': registration,
            'service_centers': service_centers,
            'require_claim_invoice': require_claim_invoice,
            'error': kw.get('error'),
        }
        return request.render('ms_warranty_qr_claim_portal.warranty_claim_form_page', vals)

    @http.route(['/warranty/submit'], type='http', auth="public", methods=['POST'], website=True, csrf=False)
    def submit_warranty(self, **post):
        _logger.info("RECEIVED POST DATA: %s", post)
        token_str = post.get('current_token')
        if not token_str:
            return request.redirect('/')
        
        lot = request.env['stock.lot'].sudo().search([('qr_token', '=', token_str.strip())], limit=1)
        
        serial_no = post.get('serial_no')
        if serial_no:
            serial_no = serial_no.strip()

        if not serial_no and lot:
            serial_no = lot.name

        if not serial_no or serial_no == '/':
            return request.redirect(f'/warranty/registration?token={token_str}&error=invalid_data')
        
        if not lot:
            lot = request.env['stock.lot'].sudo().search([
                ('name', '=', serial_no)
            ], limit=1)

        if not lot:
            return request.redirect(f'/warranty/registration?token={token_str}&error=invalid_data')

        existing_registration = request.env['ms.warranty.registration'].sudo().search([
            ('serial_no', '=', lot.id), 
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

        if not product_product_id and lot and lot.product_id:
            product_product_id = lot.product_id.id

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
        
        require_reg_invoice = policy.require_reg_invoice if policy else False
        if require_reg_invoice and not invoice_data:
            _logger.warning("Warranty registration failed: Invoice Proof is required by policy.")
            return request.redirect(f'/warranty/registration?token={token_str}&error=missing_invoice')

        company_id = lot.company_id.id if lot and getattr(lot, 'company_id', False) else request.env.company.id

        email_raw = post.get('customer_email')
        phone_raw = post.get('country_code') or post.get('customer_phone')
        name_raw = post.get('customer_name')
        
        partner = False
        
        if email_raw and email_raw.strip():
            partner = request.env['res.partner'].sudo().search([('email', '=', email_raw.strip())], limit=1)
            
        if not partner and phone_raw and phone_raw.strip():
            partner = request.env['res.partner'].sudo().search([('phone', '=', phone_raw.strip())], limit=1)
            
        if partner and name_raw and name_raw.strip() and partner.name != name_raw.strip():
            partner.sudo().write({'name': name_raw.strip()})

        if not partner and name_raw and name_raw.strip():
            partner = request.env['res.partner'].sudo().create({
                'name': name_raw.strip(),
                'email': email_raw.strip() if email_raw else False,
                'phone': phone_raw.strip() if phone_raw else False,
                'customer_rank': 1,
                'company_id': company_id,
            })
            
        partner_id = partner.id if partner else False

        vals = {
            'partner_id': partner_id,
            'customer_name': post.get('customer_name'),
            'customer_phone': phone_raw,
            'customer_email': post.get('customer_email'),
            'product_id': product_product_id,
            'serial_no': lot.id, 
            'purchase_date': post.get('purchase_date') or date.today(),
            'dealer_id': int(post.get('dealer_id')) if post.get('dealer_id') else False,
            'invoice_proof': invoice_data,
            'state': target_state,
            'policy_id': policy.id if policy else False,
            'company_id': company_id,
        }

        try:
            registration = request.env['ms.warranty.registration'].sudo().create(vals)
            
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
        serial_no_raw = post.get('serial_no')
        
        if not token_str or not serial_no_raw:
            return request.redirect('/')
        
        try:
            serial_no_id = int(serial_no_raw)
        except (ValueError, TypeError):
            serial_no_id = False

        if not serial_no_id:
            _logger.error("Warranty claim failed: serial_no is missing or invalid integer.")
            return request.redirect(f'/warranty/registration?token={token_str}&error=invalid_data')
        
        customer_mobile = post.get('customer_mobile', '').strip()
        clean_mobile = customer_mobile.replace(" ", "").replace("-", "")
        
        if not clean_mobile or not re.match(r'^1[3-9]\d{8}$', clean_mobile):
            _logger.warning("Warranty claim failed: Invalid BD mobile number format -> %s", customer_mobile)
            return request.redirect(f'/warranty/registration?token={token_str}&error=invalid_mobile')
        
        search_domain = [
            ('state', '=', 'approved'),
            ('serial_no', '=', serial_no_id)
        ]

        registration = request.env['ms.warranty.registration'].sudo().search(search_domain, limit=1)

        _logger.info("CLAIM SUBMIT DEBUG - serial_no_id: %s, registration_found: %s", serial_no_id, registration)

        if not registration:
            return request.redirect(f'/warranty/registration?token={token_str}&error=not_eligible')
                
        if registration.expiry_date and registration.expiry_date < date.today():
            _logger.warning("Warranty registration expired for Serial ID: %s", serial_no_id)
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

        policy = registration.policy_id if registration else False
        require_claim_invoice = policy.require_claim_invoice if policy else False

        if require_claim_invoice and not invoice_data:
            _logger.warning("Warranty claim failed: Purchase Invoice Proof is required by policy.")
            return request.redirect(f'/warranty/claim/form/{serial_no_id}?error=missing_invoice')

        source_val = 'dealer' if is_dealer else 'public'
        submitted_by_val = current_user.id if is_dealer else False

        claim_company_id = registration.company_id.id if registration.company_id else request.env.company.id

        portal_service_center = post.get('portal_service_center_id')
        try:
            service_center_int = int(portal_service_center) if portal_service_center else False
        except (ValueError, TypeError):
            service_center_int = False

        delivery_method = post.get('delivery_method', 'walk_in')

        customer_location = False
        if delivery_method == 'courier':
            customer_location = post.get('customer_location')

            if not customer_location or not customer_location.strip():
                return request.redirect(f'/warranty/registration?token={token_str}&error=invalid_data')

        vals = {
            'registration_id': registration.id,
            'issue_category': post.get('issue_category', 'hardware'),
            'description': post.get('description'),
            'customer_mobile': clean_mobile,
            'customer_email': post.get('customer_email'),
            'product_photo': photo_data,
            'invoice_proof': invoice_data,
            'state': 'submitted',
            'claim_source': source_val,                                         
            'submitted_by_id': submitted_by_val,
            'company_id': claim_company_id,
            'portal_service_center_id': service_center_int,
            'service_center_id': service_center_int,
            'delivery_method': delivery_method,
            'customer_location': customer_location,          
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
    def warranty_service_center_portal(self, search='', stage='', **kw):
        user = request.env.user
        service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)
        
        if not service_center:
            _logger.warning("User %s is not linked to any service center.", user.name)
            return request.redirect('/my?error=no_service_center')
            
        domain = [('service_center_id', '=', service_center.id)]

        if search:
            domain += [
                '|', '|', '|',
                ('name', 'ilike', search),
                ('registration_id.customer_name', 'ilike', search),
                ('registration_id.customer_phone', 'ilike', search),
                ('registration_id.serial_no.name', 'ilike', search)
            ]  
            
        if stage:
            domain += [('state', '=', stage)]

        claims = request.env['ms.warranty.claim'].sudo().search(domain, order="create_date desc")
        
        return request.render('ms_warranty_qr_claim_portal.service_center_claims_list_template', {
            'claims': claims,
            'today': date.today(),
            'error': kw.get('error'),
            'success': kw.get('success'),
            'search': search,
            'stage': stage,
        })
    
    @http.route(['/my/service-center/claim/<int:claim_id>'], type='http', auth="user", website=True)
    def service_center_claim_detail(self, claim_id, **kw):
        user = request.env.user
        claim = request.env['ms.warranty.claim'].sudo().browse(claim_id)
        user_service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)
        
        if not claim.exists() or not user_service_center or claim.service_center_id.id != user_service_center.id:
            return request.render("http_routing.403")
        
        error_msg = kw.get('error') or False
        products = request.env['product.product'].sudo().search([('sale_ok', '=', True)])
        
       
        center_users = request.env['res.users'].sudo().search([
            ('share', '=', False), 
            ('active', '=', True)
        ])

        return request.render("ms_warranty_qr_claim_portal.service_center_claim_detail_template", {
            'claim': claim,
            'products': products,
            'center_users': center_users,  
            'today': date.today(),
            'error': error_msg, 
            'success': kw.get('success'),
        })
    
    @http.route(['/my/service-center/claim/approve/<int:claim_id>'], type='http', auth="user", methods=['GET', 'POST'], website=True, csrf=False)
    def portal_approve_claim(self, claim_id, **kw):
        user = request.env.user
        claim = request.env['ms.warranty.claim'].sudo().browse(claim_id)
        user_service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)

        if not claim.exists() or not user_service_center or claim.service_center_id.id != user_service_center.id:
            return request.render("http_routing.403")

        if claim.state == 'received':
            claim.sudo().write({
                'state': 'approved'
            })
            return request.redirect(f'/my/service-center/claim/{claim_id}?success=claim_approved_successfully')
        else:
            return request.redirect(f'/my/service-center/claim/{claim_id}?error=claim_cannot_be_approved')
    
    
    @http.route(['/my/service-center/claim/receive/<int:claim_id>'], type='http', auth="user", methods=['POST'], website=True, csrf=False)
    def portal_receive_claim_product(self, claim_id, **post):
        user = request.env.user
        claim = request.env['ms.warranty.claim'].sudo().browse(claim_id)
        user_service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)

    
        if not claim.exists() or not user_service_center or claim.service_center_id.id != user_service_center.id:
            return request.render("http_routing.403")

        received_by_id = post.get('received_by_id')
        if not received_by_id:
            return request.redirect(f'/my/service-center/claim/{claim_id}?error=missing_receiver')

        if claim.state == 'submitted':
            claim.sudo().write({
                'state': 'received',
                'received_by_id': int(received_by_id),
                'logistics_status': 'received'
            })
            return request.redirect(f'/my/service-center/claim/{claim_id}?success=product_received_successfully')
        
        return request.redirect(f'/my/service-center/claim/{claim_id}')

    @http.route(['/my/service-center/claim/update_inspection'], type='http', auth="user", methods=['POST'], website=True, csrf=False)
    def update_inspection(self, **post):
        claim_id = int(post.get('claim_id'))
        user = request.env.user
        claim = request.env['ms.warranty.claim'].sudo().browse(claim_id)
        user_service_center = getattr(user, 'service_center_id', False) or getattr(user.partner_id, 'service_center_id', False)

        if not claim.exists() or not user_service_center or claim.service_center_id.id != user_service_center.id:
            return request.render("http_routing.403")

        recommended_resolution = post.get('recommended_resolution', 'repair')

        vals = {
            'diagnosis': post.get('diagnosis'),
            'inspection_result': post.get('inspection_result'),
            'is_covered': True if post.get('is_covered') == '1' else False,
        }

        logged_data = {
            'diagnosis': post.get('diagnosis'),
            'inspection_result': post.get('inspection_result'),
            'recommended_resolution': recommended_resolution, 
        }

        claim.action_portal_submit_inspection(vals, logged_data=logged_data)

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


        if post.get('action_submit'):
            claim.action_portal_finalize_repair_lines()

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
    

    @http.route(['/warranty/print/card/<int:lot_id>'], type='http', auth="public", website=True)
    def print_warranty_card(self, lot_id, **kw):
        lot = request.env['stock.lot'].sudo().browse(lot_id)

        if not lot.exists():
            return request.not_found()

        lot._compute_linked_registration()
        lot._compute_live_warranty_status()

        pdf, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'ms_warranty_qr_claim_portal.action_report_warranty_card', [lot.id]
        )
        
        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', content_disposition(f'Warranty_Card_{lot.name}.pdf')) 
        ]
        return request.make_response(pdf, headers=pdfhttpheaders)