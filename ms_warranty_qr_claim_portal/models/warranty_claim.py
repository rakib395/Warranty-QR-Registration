# -*- coding: utf-8 -*-
import re
import logging
from odoo import http
from odoo.http import request
from odoo import models, fields, tools, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta

class WarrantyClaim(models.Model):
    _name = 'ms.warranty.claim'
    _description = 'Warranty Claim Request'
    _inherit = ['mail.thread', 'mail.activity.mixin'] 
    _order = 'id desc'

    name = fields.Char(string='Claim Number', required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    registration_id = fields.Many2one('ms.warranty.registration', string='Warranty Registration', required=True, ondelete='cascade')

    policy_id = fields.Many2one('ms.warranty.policy', string='Warranty Policy', related='registration_id.policy_id', store=True, index=True)

    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        related='registration_id.company_id', 
        store=True, 
        index=True, 
        default=lambda self: self.env.company
    )

    courier_service_id = fields.Many2one(
    'warranty.courier.service', 
    string="Courier Service",
    help="Select the courier service provider used by the customer"
    )
    courier_tracking_url = fields.Char(string="Live Tracking Link", compute="_compute_courier_tracking_url")

    def _compute_courier_tracking_url(self):
        for record in self:
            if record.courier_service_id and record.courier_service_id.website_url and record.courier_tracking_no:
                record.courier_tracking_url = f"{record.courier_service_id.website_url}{record.courier_tracking_no}"
            else:
                record.courier_tracking_url = False

    rma_number = fields.Char(
    string='RMA Number', 
    readonly=True, 
    copy=False, 
    help="Return Merchandise Authorization Number"
    )
    logistics_status = fields.Selection([
        ('none', 'No Return Required'),
        ('pending', 'Waiting for Shipment'),
        ('shipped', 'Shipped by Customer'),
        ('received', 'Received at Service Center'),
        ('returning', 'Sending Back to Customer'),
        ('delivered', 'Delivered to Customer')
    ], string='Logistics Status', default='none', tracking=True)

    portal_service_center_id = fields.Many2one(
        'ms.warranty.service.center', 
        string='Customer Preferred Service Center',
        tracking=True
    )
    received_by_id = fields.Many2one('res.users', string='Received By', readonly=True, tracking=True)

    def action_receive_product(self):
        self.ensure_one()
        return {
            'name': 'Receive Product Info',
            'type': 'ir.actions.act_window',
            'res_model': 'claim.receive.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('ms_warranty_qr_claim_portal.view_claim_receive_wizard_form').id,
            'target': 'new', 
            'context': {
                'default_claim_id': self.id,
                'default_received_by_id': self.env.user.id,
            }
        }

    delivery_method = fields.Selection([
        ('walk_in', 'Drop & Pick'),
        ('courier', 'Via Courier Service')
    ], string='Delivery Method', default='walk_in', tracking=True)
    courier_name = fields.Char(string="Courier Name")
    tracking_reference = fields.Char(string='Tracking Number', tracking=True)
    customer_location = fields.Text(string='Customer Pickup/Return Location', tracking=True)
    courier_tracking_no = fields.Char(string="Courier Tracking No")
    is_courier_visible = fields.Boolean(compute='_compute_is_courier_visible', string="Is Courier Visible")

    @api.depends('delivery_method')
    def _compute_is_courier_visible(self):
        for record in self:
            record.is_courier_visible = record.delivery_method == 'courier'

    @api.constrains('delivery_method', 'customer_location')
    def _check_courier_location(self):
        for record in self:
            if record.delivery_method == 'courier' and not record.customer_location:
                raise ValidationError(_("Error! Customer location/address is mandatory when 'Via Courier Service' is selected."))
            

    return_shipping_address = fields.Text(string='Return Shipping Address') 
    issue_category = fields.Selection([
        ('hardware', 'Hardware Failure'),
        ('software', 'Software / Firmware Issue'),
        ('damage', 'Physical Damage (Check Policy Extension)'),
        ('other', 'Other Technical Faults')
    ], string='Issue Category', default='hardware', required=True)
    
    customer_mobile = fields.Char(string='Mobile Number', required=True, tracking=True)
    customer_email = fields.Char(string='Email Address', tracking=True)
    description = fields.Text(string='Detailed Issue Description', required=True)

    product_photo = fields.Binary(string='Product/Fault Photo', attachment=True)
    invoice_proof = fields.Binary(string='Purchase Invoice Proof', attachment=True)
    
    state = fields.Selection([
        ('submitted', 'Submitted'),
        ('received', 'Received'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('repairing', 'Repairing'),
        ('resolved', 'Resolved'),
        ('delivered', 'Delivered'),
        ('rejected', 'Rejected'),
    ], string='Status', default='submitted', required=True, tracking=True)

    diagnosis = fields.Text(string='Diagnosis', tracking=True)
    inspection_result = fields.Text(string='Inspection Result', tracking=True)
    is_covered = fields.Boolean(string='Is Covered Under Warranty', default=True, tracking=True)
    estimated_cost = fields.Float(string='Estimated Cost', tracking=True)
    rejection_reason = fields.Text(string='Rejection Reason', tracking=True)

    service_center_id = fields.Many2one('ms.warranty.service.center', string='Service Center', tracking=True)
    technician_id = fields.Many2one('res.users', string='Assigned Technician', tracking=True)
    sla_deadline = fields.Date(string='SLA Deadline', readonly=True, tracking=True)

    repair_notes = fields.Text(string='Repair Notes')
    part_lines = fields.One2many('ms.warranty.claim.part.line', 'claim_id', string='Replaced Parts')
    labor_lines = fields.One2many('ms.warranty.claim.labor.line', 'claim_id', string='Labor/Service Lines')

    logistics_portal_message = fields.Char(
        string="Portal Message", 
        compute="_compute_logistics_portal_message"
    )

    @api.depends('customer_mobile', 'customer_email')
    def _compute_preferred_contact(self):
        for record in self:
            contacts = [record.customer_mobile, record.customer_email]
            record.preferred_contact = " / ".join(filter(None, contacts)) if any(contacts) else False

    @api.constrains('customer_mobile')
    def _check_customer_mobile(self):
        for record in self:
            if record.customer_mobile:
                clean_num = record.customer_mobile.replace(" ", "").replace("-", "")
                
                if clean_num.startswith('+880'):
                    raw_num = clean_num[4:]
                elif clean_num.startswith('880'):
                    raw_num = clean_num[3:]
                elif clean_num.startswith('0'):
                    raw_num = clean_num[1:]
                else:
                    raw_num = clean_num

                if not re.match(r'^1[3-9]\d{8}$', raw_num):
                    raise ValidationError(_("Invalid Mobile Number! Please enter a valid BD mobile number (e.g. 17XXXXXXXX)."))

    @api.depends('state', 'delivery_method')
    def _compute_logistics_portal_message(self):
        for record in self:
            if record.state == 'delivered':
                if record.delivery_method == 'courier':
                    record.logistics_portal_message = "Your product has been dispatched via courier successfully! Hope you're happy with our service."
                elif record.delivery_method == 'walk_in':
                    record.logistics_portal_message = "Your product has been handed over successfully via Drop & Pick! Hope you're happy with our service."
                else:
                    record.logistics_portal_message = "Delivered your product successfully, hope you're happy."
            elif record.state == 'received':
                record.logistics_portal_message = "We have received your product safely at our service center. We will begin our inspection shortly."
            elif record.state == 'under_review':
                record.logistics_portal_message = "Your product is currently under technical inspection by our experts."
            else:
                record.logistics_portal_message = False

    resolution_type = fields.Selection([
        ('repair', 'Repair'),
        ('replacement', 'Replacement Product'),
        ('refund', 'Refund')
    ], string='Resolution Type', default='repair', required=True, tracking=True)

    @api.onchange('resolution_type')
    def _onchange_resolution_type_reset_chargeable(self):
        for record in self:
            if record.resolution_type != 'repair':
                record.is_chargeable = False
    
    replacement_product_id = fields.Many2one('product.product', string='Replacement Product', tracking=True)
    
    replacement_serial_no = fields.Many2one(
        'stock.lot', 
        string='Replacement Serial Number'
    )

    old_serial_no = fields.Char(string='Old Serial Linked', readonly=True)

    @api.onchange('registration_id', 'replacement_product_id', 'product_id')
    def _onchange_registration_and_product(self):
        if self.registration_id:
            if self.registration_id.serial_no:
                self.old_serial_no = self.registration_id.serial_no.name
            else:
                self.old_serial_no = False
            
            if self.resolution_type == 'replacement' and not self.replacement_product_id:
                self.replacement_product_id = self.registration_id.product_id.id
        else:
            self.old_serial_no = False

        product_to_filter = self.replacement_product_id or self.product_id
        
        if product_to_filter:
            used_reg_serials = self.env['ms.warranty.registration'].search([
                ('product_id', '=', product_to_filter.id),
                ('state', 'not in', ('expired', 'rejected'))  
            ]).mapped('serial_no').ids
            used_serial_ids = [sid for sid in used_reg_serials if sid]

            used_claim_serials = self.env['ms.warranty.claim'].search([
                ('replacement_serial_no', '!=', False),
                ('state', 'not in', ('draft', 'rejected'))
            ]).mapped('replacement_serial_no').ids
            used_claim_ids = [sid for sid in used_claim_serials if sid]

            if self.registration_id and self.registration_id.serial_no:
                used_serial_ids.append(self.registration_id.serial_no.id)

            final_used_ids = list(set(used_serial_ids + used_claim_ids))
            final_used_ids = [uid for uid in final_used_ids if uid]

            return {
                'domain': {
                    'replacement_serial_no': [
                        ('product_id', '=', product_to_filter.id),
                        ('id', 'not in', final_used_ids)
                    ]
                }
            }
        else:
            return {
                'domain': {
                    'replacement_serial_no': [('id', '=', False)]
                }
            }
        
   
    charge_payment_method = fields.Selection([
        ('bkash', 'bKash / Mobile Banking'),
        ('bank', 'Bank Transfer'),
        ('manual', 'Manual Cash / POS')
    ], string='Payment Method (Chargeable)', tracking=True)

    invoice_ids = fields.Many2many(
        'account.move', 
        string='Linked Invoices/Bills', 
        copy=False
    )
    invoice_count = fields.Integer(
        string='Invoice Count', 
        compute='_compute_invoice_count'
    )

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    refund_amount = fields.Float(string='Refund Amount', tracking=True)
    refund_reason = fields.Text(string='Refund Reason Description')

    is_chargeable = fields.Boolean(string='Is Chargeable Service', default=False, tracking=True)
    charge_reason = fields.Text(string='Charge Reason', tracking=True)

    estimated_charge_amount = fields.Float(
    string="Estimated Amount", 
    digits=(16, 2), 
    default=False  
    )

    
    is_suspect_duplicate = fields.Boolean(string='Suspect Duplicate Claim', compute='_compute_fraud_analysis', store=True)
    fraud_risk_level = fields.Selection([
        ('low', 'Low Risk'),
        ('medium', 'Medium Risk'),
        ('high', 'High Risk/Suspicious')
    ], string='Fraud Risk Level', compute='_compute_fraud_analysis', store=True, default='low', tracking=True)
    fraud_warning_notes = fields.Text(string='Fraud System Detection Logs', compute='_compute_fraud_analysis', store=True)


    customer_name = fields.Char( related='registration_id.customer_name', string="Customer", store=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer', related='registration_id.partner_id', store=True, index=True)
    customer_phone = fields.Char(string='Customer Phone', related='registration_id.customer_phone', store=True)
    dealer_id = fields.Many2one('res.partner', string='Dealer/Store', related='registration_id.dealer_id', store=True, index=True)
    product_id = fields.Many2one('product.product', string='Product', related='registration_id.product_id', store=True, index=True)
    total_claim_cost = fields.Float(string='Total Claim Cost', compute='_compute_total_claim_cost', store=True, tracking=True)

    claim_source = fields.Selection([
        ('public', 'Public Portal/Customer'),
        ('dealer', 'Dealer Portal')
    ], string='Claim Source', default='public', required=True, tracking=True)
    
    submitted_by_id = fields.Many2one('res.users', string='Submitted By (User)', default=lambda self: self.env.user, index=True, tracking=True)
    customer_approved = fields.Boolean(string='Charge Approved by Customer', default=False, tracking=True)

    @api.constrains('is_chargeable', 'estimated_charge_amount')
    def _check_chargeable_amount(self):
        for record in self:
            if record.is_chargeable:
                if not record.estimated_charge_amount or record.estimated_charge_amount <= 0.0:
                    raise ValidationError(_(
                        "Action Blocked!\n\n"
                        "You have marked this claim as a 'Chargeable Service'. "
                        "You MUST enter a valid Estimated Amount greater than 0.00 before saving or proceeding."
                    ))
                


    def action_portal_submit_inspection(self, vals, logged_data=None):
        self.ensure_one()
      
        self.write(vals)
        
        if logged_data:
            diagnosis_text = logged_data.get('diagnosis') or "No diagnosis report provided."
            inspection_result_text = logged_data.get('inspection_result') or "N/A"
            
            if self.is_chargeable:
                coverage_status = "No, Billable / Chargeable Service"
            else:
                coverage_status = "Yes, Free Repair Under Warranty"
            
            rec_type = logged_data.get('recommended_resolution', 'repair')
            resolution_labels = {
                'repair': 'Repair',
                'replacement': 'Replacement Product',
                'refund': 'Refund'
            }
            suggested_label = resolution_labels.get(rec_type, 'Repair')
            
            raw_html = f"""
            <div>
                <p><strong>Warranty Claim Inspected &amp; Logs Submitted</strong></p>
                <ul style="margin:0;padding-left:18px;">
                    <li><strong>Inspection Metric:</strong> {inspection_result_text.title()}</li>
                    <li><strong>Warranty Coverage Evaluation:</strong> {coverage_status}</li>
                    <li><strong>Technical Diagnosis Report:</strong> {diagnosis_text}</li>
                    <li style="color: #bc3a3a;"><strong>🚨 Recommended Resolution:</strong> {suggested_label}</li>
                </ul>
            </div>
            """
            body_html = tools.html_sanitize(raw_html)
            self.message_post(
                body=body_html,
                body_is_html=True,
                message_type='comment',
                subtype_xmlid='mail.mt_comment'
            )
        return True
    
    def action_portal_finalize_repair_lines(self):   
        self.ensure_one()
        return True

    def _send_warranty_sms_notification(self, message_text):
        """Helper method to fire SMS standard gateway"""
        self.ensure_one()
        phone = self.customer_phone or self.preferred_contact
        if not phone:
            return False
        
        try:
            self.env['sms.api']._send_sms(
                numbers=[phone],
                message=message_text
            )
            self.message_post(body=_("SMS Notification Sent successfully to %s") % phone, message_type='notification')
        except Exception as e:
            self.message_post(body=_("Failed to send SMS: %s") % str(e), message_type='notification')

    @api.depends('part_lines.subtotal', 'labor_lines.subtotal', 'refund_amount', 'resolution_type')
    def _compute_total_claim_cost(self):
        for claim in self:
            cost = 0.0
            if claim.resolution_type == 'repair':
                parts_cost = sum(claim.part_lines.mapped('subtotal')) if claim.part_lines else 0.0
                labor_cost = sum(claim.labor_lines.mapped('subtotal')) if claim.labor_lines else 0.0
                cost = parts_cost + labor_cost
            elif claim.resolution_type == 'refund':
                cost = claim.refund_amount
            elif claim.resolution_type == 'replacement':
                cost = claim.replacement_product_id.standard_price if claim.replacement_product_id else 0.0
            
            claim.total_claim_cost = cost

    @api.depends('registration_id', 'create_date', 'registration_id.purchase_date', 'registration_id.serial_no')
    def _compute_fraud_analysis(self):
        for claim in self:
            is_duplicate = False
            risk_level = 'low'
            warning_reasons = []

            if not claim.registration_id:
                claim.is_suspect_duplicate = False
                claim.fraud_risk_level = 'low'
                claim.fraud_warning_notes = False
                continue

           
            duplicate_claims_domain = [
                ('registration_id.serial_no', '=', claim.registration_id.serial_no),
            ]
            if claim.id:
                duplicate_claims_domain.append(('id', '!=', claim.id))

            existing_claims = self.env['ms.warranty.claim'].sudo().search(duplicate_claims_domain)
            
            open_or_resolved_claims = existing_claims.filtered(lambda c: c.state in ('under_review', 'approved', 'resolved'))
            if open_or_resolved_claims:
                is_duplicate = True
                risk_level = 'high'
                claim_names = ", ".join(open_or_resolved_claims.mapped('name'))
                warning_reasons.append(_("DUPLICATE DETECTED: Active or resolved claim(s) [%s] already exist for this serial number.") % claim_names)

            current_date = claim.create_date.date() if claim.create_date else fields.Date.today()
            date_threshold = current_date - timedelta(days=30)
            
            recent_claims = existing_claims.filtered(
                lambda c: c.create_date and c.create_date.date() >= date_threshold and c.state != 'rejected'
            )
            if recent_claims:
                is_duplicate = True
                if risk_level != 'high':
                    risk_level = 'medium'
                warning_reasons.append(_("FREQUENCY WARNING: Multiple claims (%s items) filed within the last 30 days for this resource.") % len(recent_claims))

            reg = claim.registration_id
            if reg.purchase_date and reg.create_date:
                reg_creation_days = (reg.create_date.date() - reg.purchase_date).days
                if reg_creation_days < 0 or reg_creation_days > 365:
                    is_duplicate = True
                    risk_level = 'high'
                    warning_reasons.append(_("MISMATCH: High variance between stated Purchase Invoice Date and system Registration Record Date."))

            claim.is_suspect_duplicate = is_duplicate
            claim.fraud_risk_level = risk_level
            claim.fraud_warning_notes = "\n".join(warning_reasons) if warning_reasons else False


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('customer_mobile'):
                num = str(vals['customer_mobile']).replace(" ", "").replace("-", "").strip()
                if num.startswith('+880'):
                    vals['customer_mobile'] = num
                elif num.startswith('880'):
                    vals['customer_mobile'] = f"+{num}"
                elif num.startswith('0'):
                    vals['customer_mobile'] = f"+880{num[1:]}"
                else:
                    vals['customer_mobile'] = f"+880{num}"

            if vals.get('delivery_method') == 'courier' and not vals.get('customer_location'):
                raise ValidationError(_("Customer pickup location/address is mandatory when 'Via Courier Service' is selected."))

            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('ms.warranty.claim') or _('New')
            
            if vals.get('registration_id'):
                registration = self.env['ms.warranty.registration'].browse(vals['registration_id'])
                policy = registration.policy_id
                
                if policy and hasattr(policy, 'sla_resolution_value') and policy.sla_resolution_value:
                    sla_days = policy.sla_resolution_value
                elif policy and hasattr(policy, 'registration_deadline_days') and policy.registration_deadline_days:
                    sla_days = policy.registration_deadline_days
                else:
                    sla_days = 7  
                
                vals['sla_deadline'] = fields.Date.today() + timedelta(days=sla_days)
            else:
                vals['sla_deadline'] = fields.Date.today() + timedelta(days=7)

        records = super(WarrantyClaim, self).create(vals_list)
        
        for rec in records:
            msg = _("Hello! Your warranty claim %s has been successfully submitted. We are processing your request. - Mindsynth") % rec.name
            rec._send_warranty_sms_notification(msg)

        return records

    def action_inspect(self):
        """Move the claim to the inspection or review state"""
        self.ensure_one()
        self.write({
            'state': 'under_review',
            'logistics_status': 'received',
            'inspection_result': 'Product received and under initial inspection.'
        })
        self.message_post(body=_("Claim status updated to 'Under Review' for technical inspection."))
        
        msg = _("Update: Your warranty claim %s is now under technical review. - Mindsynth") % self.name
        self._send_warranty_sms_notification(msg)


    def action_receive_claim(self):
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_("Only submitted claims can be received."))
            
        self.write({
            'state': 'received',
            'logistics_status': 'received' 
        })
        
        self.message_post(body=_("Product received officially at the center. Awaiting inspection assignment."))
        return True
    
    def action_start_review(self):
        """Move from 'Received' to 'Under Review' when inspection actually begins"""
        self.ensure_one()
        self.write({
            'state': 'under_review',
            'logistics_status': 'received',
            'inspection_result': 'Product received and under initial inspection.'
        })
        self.message_post(body=_("Claim status updated to 'Under Review' for technical inspection."))
        
        msg = _("Update: Your warranty claim %s is now under technical review. - Mindsynth") % self.name
        self._send_warranty_sms_notification(msg)

    def action_mark_delivered(self):
        """Final stage to mark product as delivered to the customer"""
        self.ensure_one()
        self.write({
            'state': 'delivered',
            'logistics_status': 'delivered'  
        })
        self.message_post(body=_("Product has been successfully delivered/handed over to the customer."))
        
        msg = _("Success: Your product for claim %s has been delivered. Hope you are happy! - Mindsynth") % self.name
        self._send_warranty_sms_notification(msg)

    def action_under_review(self):
        self.ensure_one()
        self.write({'state': 'under_review'})

    def action_approve(self):
        self.ensure_one()
        
        vals = {
            'rejection_reason': False
        }

        if self.resolution_type in ['repair', 'replacement', 'refund']:
            vals['state'] = 'approved'  

        if self.resolution_type in ['repair', 'replacement']:
            if not self.rma_number:
                vals['rma_number'] = self.env['ir.sequence'].with_company(self.company_id).next_by_code('ms.warranty.rma') or '/'
            vals['logistics_status'] = 'pending'
        else:
            vals['logistics_status'] = 'none'

        self.write(vals)

        if self.is_chargeable and not self.invoice_ids.filtered(lambda inv: inv.move_type == 'out_invoice'):
            self._create_customer_invoice()         
    
        if self.resolution_type in ['replacement', 'refund']:
            body_msg = _("Dear Customer, Your warranty claim %s has been Approved. Please wait while our team prepares your %s. - Mindsynth") % (self.name, self.resolution_type.title())
            sms_msg = _("Good News! Your warranty claim %s has been Approved via %s. - Mindsynth") % (self.name, self.resolution_type.title())
        else:
            body_msg = _("Dear Customer, Your warranty claim %s has been Approved. RMA Number: %s. Our service center will process it shortly.") % (self.name, self.rma_number or _('N/A'))
            sms_msg = _("Good News! Your warranty claim %s has been Approved. RMA: %s. Our team will contact you shortly. - Mindsynth") % (self.name, self.rma_number or '')

        self.message_post(body=body_msg, subtype_xmlid="mail.mt_comment")
        self._send_warranty_sms_notification(sms_msg)
        
        return True
    
    def action_repair(self):
        """Initiate the repairing process track"""
        self.ensure_one()
        if not self.diagnosis:
            raise UserError(_("Please provide a diagnosis before moving to the repair workflow."))
        
        self.write({
            'state': 'repairing',
            'logistics_status': 'received'
        })

        if self.is_chargeable and not self.invoice_ids.filtered(lambda inv: inv.move_type == 'out_invoice'):
            self._create_customer_invoice()
            
        self.message_post(body=_("Technical diagnosis complete. Repair workflow initiated. Logistics Status updated to 'Received at Service Center'."))
        
        msg = _("Update: Repair has started for your claim %s at our designated service center. - Mindsynth") % self.name
        self._send_warranty_sms_notification(msg)

    def action_resolve(self):
        """Modified: Service center will only update info, admin will change state later"""
        self.ensure_one()
        
        log_body = _(
            "<b>Service Center Update:</b> Diagnosis and charges logged.<br/>"
            "<b>Is Chargeable:</b> %s<br/>"
            "<b>Estimated Charge:</b> %s<br/>"
            "<b>Diagnosis Notes:</b> %s"
        ) % (_('Yes') if self.is_chargeable else _('No'), self.estimated_charge_amount, self.diagnosis or _('N/A'))
        
        self.message_post(body=log_body, subtype_xmlid="mail.mt_comment")
        
        msg = _("Update: Technical diagnosis completed for your claim %s. Admin will review the approval status shortly. - Mindsynth") % self.name
        self._send_warranty_sms_notification(msg)

    def action_resolved(self):
        """Completely resolve the claim based on resolution type with field validations"""
        self.ensure_one()
        
        if self.resolution_type == 'replacement':
            if not self.replacement_product_id or not self.replacement_serial_no:
                raise ValidationError(_(
                    "Error! You cannot resolve this claim. Please fill out the "
                    "'Replacement Product' and 'Replacement Serial Number' in the Product Replacement Mapping tab first."
                ))
            if hasattr(self, 'action_approve_replacement'):
                self.action_approve_replacement()
            else:
                self.write({'state': 'resolved'})
     
        elif self.resolution_type == 'refund':
            if self.refund_amount <= 0.0 or not self.refund_reason:
                raise ValidationError(_(
                    "Error! You cannot resolve this claim. Please ensure you have provided a valid "
                    "'Refund Amount' and 'Refund Reason Description' before resolving."
                ))
            if hasattr(self, 'action_approve_refund'):
                self.action_approve_refund()
            else:
                self.write({'state': 'resolved'})
            
        elif self.resolution_type == 'repair':
            if hasattr(self, 'action_mark_as_repaired'):
                self.action_mark_as_repaired()
            else:
                self.write({'state': 'resolved'})
            
        else:
            self.write({'state': 'resolved'})
            
    
        msg = _("Dear Customer, Your warranty claim %s has been successfully resolved. Thank you for staying with us! - Mindsynth") % self.name
        self._send_warranty_sms_notification(msg)

    def action_reject(self):
        """Reject the warranty claim"""
        self.ensure_one()
        if not self.rejection_reason:
            self.rejection_reason = "Claim rejected after technical review/inspection."
        self.write({'state': 'rejected'})
        self.message_post(body=_("Warranty claim has been rejected. Reason: %s") % self.rejection_reason)
  
        msg = _("Alert: Your warranty claim %s has been rejected. Reason: %s. Please contact support. - Mindsynth") % (self.name, self.rejection_reason)
        self._send_warranty_sms_notification(msg)

    def action_convert_to_chargeable(self):
        self.ensure_one()
        self.write({'is_chargeable': True})

    def action_reset_to_review(self):
        self.ensure_one()
        self.write({'state': 'under_review'})
        self.message_post(body=_("Warranty claim has been reset to 'Under Review' status by the administrator."))

    def action_assign_claim_processing(self, service_center_id, technician_id):
        self.ensure_one()
        calculated_deadline = fields.Date.today() + timedelta(days=7)
            
        self.write({
            'service_center_id': service_center_id.id,
            'technician_id': technician_id.id,
            'sla_deadline': calculated_deadline,
            'state': 'under_review' 
        })

        body_html = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.5; color: #1E293B;">
            <p style="margin-bottom: 8px;">
                <span class="fa fa-user-plus" style="color: #3B82F6; margin-right: 6px;"></span>
                <strong>Claim Has Been Successfully Assigned</strong>
            </p>
            <ul style="margin: 0; padding-left: 20px; list-style-type: square;">
                <li style="margin-bottom: 4px;"><strong>Service Center:</strong> {service_center_id.name}</li>
                <li style="margin-bottom: 4px;"><strong>Technician:</strong> {technician_id.name}</li>
                <li style="margin-bottom: 4px;"><strong>SLA Deadline:</strong> {calculated_deadline}</li>
            </ul>
        </div>
        """
        
        self.message_post(
            body=body_html, 
            body_is_html=True, 
            message_type='comment', 
            subtype_xmlid="mail.mt_comment"
        )

        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        self.activity_schedule(
            activity_type_id=activity_type.id if activity_type else False,
            date_deadline=calculated_deadline,
            summary=_("Inspect and Resolve Claim: %s") % self.name,
            note=_("Please review the detailed issue description and resolve the claim before the SLA deadline."),
            user_id=technician_id.id
        )

    def action_mark_as_repaired(self):
        """Helper to mark claim as repaired and sync logistics status"""
        self.ensure_one()
        if not self.diagnosis:
            raise UserError(_("Please provide a proper diagnosis before marking the claim as repaired."))
        if not self.repair_notes:
            raise UserError(_("Repair notes are mandatory to close the repair lifecycle."))
        
        self.write({
            'state': 'resolved',
            'logistics_status': 'delivered' 
        })
        
        body_html = f"""
        <div>
            <p><strong>Warranty Claim Resolved (Repaired)</strong></p>
            <ul style="margin:0;padding-left:18px;">
                <li><strong>Resolution:</strong> Repair Resolution</li>
                <li><strong>Diagnosis:</strong> {self.diagnosis}</li>
                <li><strong>Repair Notes:</strong> {self.repair_notes}</li>
                <li><strong>Logistics Status:</strong> Automatically updated to Delivered to Customer.</li>
            </ul>
        </div>
        """
        
        self.message_post(
            body=body_html,
            body_is_html=True,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
    def action_approve_replacement(self):
        self.ensure_one()
        if not self.replacement_product_id:
            raise UserError(_("Please capture the Replacement Product before approval."))
        if not self.replacement_serial_no:
            raise UserError(_("Replacement Serial Number is mandatory to execute replacement flow."))
        
        old_reg = self.registration_id
        if not old_reg:
            raise UserError(_("No active warranty registration linked with this claim."))

        new_expiry = old_reg.expiry_date

     
        serial_id = self.replacement_serial_no.id
        serial_name = self.replacement_serial_no.name

        new_reg_vals = {
            'customer_name': old_reg.customer_name,
            'customer_phone': old_reg.customer_phone,
            'customer_email': old_reg.customer_email,
            'product_id': self.replacement_product_id.id,
            'serial_no': serial_id, 
            'purchase_date': old_reg.purchase_date,
            'policy_id': old_reg.policy_id.id if old_reg.policy_id else False,
            'dealer_id': old_reg.dealer_id.id if old_reg.dealer_id else False,
            'state': 'approved', 
        }
        
        new_registration = self.env['ms.warranty.registration'].create(new_reg_vals)
        new_registration.write({'expiry_date': new_expiry})

        old_reg.write({'state': 'expired'})
        
        old_reg.message_post(body=_("This product has been replaced by Claim: %s. New Serial: %s") % (self.name, serial_name))

        self.write({'state': 'resolved'})

        old_serial_display = old_reg.serial_no.name if old_reg.serial_no else self.old_serial_no
        
        log_body = _(
            "Warranty Claim has been approved for <b>Product Replacement</b>.<br/>"
            "<b>Old Serial:</b> %s <br/>"
            "<b>New Replacement Serial:</b> %s <br/>"
            "<b>Warranty Status:</b> Successfully Carry-forwarded till %s."
        ) % (old_serial_display, serial_name, new_expiry)
        
        self.message_post(body=log_body, subtype_xmlid="mail.mt_comment")
        return True

    def action_approve_refund(self):
        self.ensure_one()
        if self.refund_amount <= 0:
            raise UserError(_("Please provide a valid Refund Amount greater than 0."))
        if not self.refund_reason:
            raise UserError(_("Refund Reason Description is mandatory to process a claim liquidation."))
        
        old_reg = self.registration_id
        if not old_reg:
            raise UserError(_("No active warranty registration linked with this claim."))

        partner = old_reg.partner_id
        if not partner and hasattr(self, 'customer_id') and self.customer_id:
            partner = self.customer_id
        if not partner:
            partner = self.env['res.partner'].search([], limit=1) 
        
        invoice_list = []

        credit_note_vals = {
            'move_type': 'out_refund',
            'state': 'draft',
            'partner_id': partner.id,
            'ref': _('Warranty Refund for Claim: %s') % self.name,
            'invoice_origin': self.name,
            'invoice_line_ids': [(0, 0, {
                'name': _('Refund for Product: %s - Reason: %s') % (old_reg.product_id.name, self.refund_reason),
                'product_id': old_reg.product_id.id,
                'quantity': 1.0,
                'price_unit': self.refund_amount,
            })],
        }
        
        try:
            credit_note = self.env['account.move'].create(credit_note_vals)
            invoice_list.append(credit_note.id)
            self.message_post(body=_("Automated Account Bridge: Draft Credit Note %s created for Customer.") % credit_note.name)
        except Exception as e:
            self.message_post(body=_("Account Bridge Log: Failed to generate Credit Note. Error: %s") % str(e))

        seller = old_reg.product_id.seller_ids[0] if old_reg.product_id.seller_ids else False
        if seller and seller.partner_id:
            vendor_bill_vals = {
                'move_type': 'in_refund',  
                'state': 'draft',
                'partner_id': seller.partner_id.id,
                'ref': _('Vendor Claim for Claim: %s') % self.name,
                'invoice_origin': self.name,
                'invoice_line_ids': [(0, 0, {
                    'name': _('Chargeback/Refund claim for product: %s') % old_reg.product_id.name,
                    'product_id': old_reg.product_id.id,
                    'quantity': 1.0,
                    'price_unit': self.refund_amount, 
                })],
            }
            try:
                vendor_bill = self.env['account.move'].create(vendor_bill_vals)
                invoice_list.append(vendor_bill.id)
                self.message_post(body=_("Automated Account Bridge: Draft Vendor Credit Note %s created for Vendor.") % vendor_bill.name)
            except Exception as e:
                self.message_post(body=_("Account Bridge Log: Failed to generate Vendor Bill. Error: %s") % str(e))

        if invoice_list:
            self.write({'invoice_ids': [(6, 0, invoice_list)]})

        old_reg.write({'state': 'expired'})
        self.write({'state': 'resolved'})
        return True
    

    def action_reject_submitted_claim(self):
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_("Only submitted claims can be rejected directly."))
            
        self.write({
            'state': 'rejected',
            'rejection_reason': 'Claim rejected directly upon submission review.'
        })
        
        self.message_post(body=_("Warranty claim has been rejected directly from Submitted state."))
        
        msg = _("Alert: Your warranty claim %s has been rejected upon initial evaluation. Please contact support. - Mindsynth") % self.name
        self._send_warranty_sms_notification(msg)
        return True

    def action_convert_to_chargeable(self):
        self.ensure_one()
        if self.estimated_charge_amount <= 0:
            raise UserError(_("Please provide a valid Estimated Charge Amount greater than 0."))
        if not self.charge_reason:
            raise UserError(_("Charge Reason description is mandatory for paid service conversion."))

        self.write({'is_chargeable': True})

        partner_id = self.registration_id.dealer_id.id if self.registration_id.dealer_id else self.env.user.partner_id.id
        
        quotation_vals = {
            'partner_id': partner_id,
            'state': 'draft',
            'origin': self.name,
            'client_order_ref': _('Chargeable Service: %s') % self.name,
            'order_line': [(0, 0, {
                'name': _('Paid Service Charges for Claim %s - Reason: %s') % (self.name, self.charge_reason),
                'product_id': self.registration_id.product_id.id,
                'product_uom_qty': 1.0,
                'price_unit': self.estimated_charge_amount,
            })],
        }

        try:
            quotation = self.env['sale.order'].create(quotation_vals)
            chatter_msg = _("Sales Bridge: Draft Quotation <b>%s</b> has been generated for this chargeable service.") % quotation.name
        except Exception:
            chatter_msg = _("Sales Bridge Log: Service recorded as Chargeable. Awaiting manual Quotation generation.")

        self.message_post(
            body=_("Claim status updated: Marked as <b>Chargeable Paid Service</b>.<br/>" + chatter_msg),
            subtype_xmlid="mail.mt_comment"
        )
        
        msg = _("Your claim %s has been marked as Chargeable. Estimated Amount: %s. Reason: %s. Please approve to proceed. - Mindsynth") % (self.name, self.estimated_charge_amount, self.charge_reason)
        self._send_warranty_sms_notification(msg)

    def action_logistics_shipped(self):
        """Called when customer ships the product"""
        self.ensure_one()
        self.write({'logistics_status': 'shipped'})
        self.message_post(body=_("Logistics Update: Product has been shipped by the customer. Courier: %s, Tracking: %s") % (self.courier_name or _('N/A'), self.tracking_reference or _('N/A')))

    def action_logistics_received(self):
        """Called when Service Center receives the defective product"""
        self.ensure_one()
        self.write({'logistics_status': 'received'})
        self.message_post(body=_("Logistics Update: Defective product safely received at Service Center for inspection/repair."))

    def action_logistics_returning(self):
        """Before or after resolving, when sending product back to customer"""
        self.ensure_one()
        self.write({'logistics_status': 'returning'})
        self.message_post(body=_("Logistics Update: Product is being dispatched/sent back to the customer address."))

    def action_logistics_delivered(self):
        """Final delivery confirmation"""
        self.ensure_one()
        self.write({'logistics_status': 'delivered'})
        self.message_post(body=_("Logistics Update: Product has been successfully delivered to the customer."))

    def _create_customer_invoice(self):
        """Generates a dynamic Invoice based on claim type (Chargeable Customer Invoice or Vendor Refund)."""
        self.ensure_one()
        
        if self.resolution_type == 'refund':
            move_type = 'in_refund'
            invoice_label = _('Warranty Refund for Product: %s - Reason: %s') % (self.product_id.name if self.product_id else 'Product', self.refund_reason or '')
            price_unit = self.refund_amount or 0.0
            
            partner = False
            if self.product_id and self.product_id.seller_ids:
                partner = self.product_id.seller_ids[0].partner_id
            
            if not partner:
                partner = self.env['res.partner'].search([('supplier_rank', '>', 0)], limit=1) or self.env['res.partner'].search([], limit=1)
        
        else:
            move_type = 'out_invoice'
            partner = self.partner_id or (self.registration_id.partner_id if self.registration_id else False)
               
            if not partner:
                contact = getattr(self, 'preferred_contact', '').strip() or (self.registration_id.customer_email if self.registration_id else '')
                if contact:
                    if '@' in contact:
                        partner = self.env['res.partner'].sudo().search([('email', '=', contact)], limit=1)
                    else:
                        partner = self.env['res.partner'].sudo().search([('phone', '=', contact)], limit=1)
            
         
            customer_name = getattr(self, 'customer_name', False) or (self.registration_id.customer_name if self.registration_id else 'Unknown Customer')
            if partner and customer_name and partner.name != customer_name:
                partner.sudo().write({'name': customer_name})
            
          
            if not partner:
                partner_vals = {
                    'name': customer_name,
                    'customer_rank': 1,
                    'company_id': self.company_id.id if self.company_id else self.env.company.id,
                }
                contact = getattr(self, 'preferred_contact', '').strip()
                if contact:
                    if '@' in contact:
                        partner_vals['email'] = contact
                    else:
                        partner_vals['phone'] = contact
                
                partner = self.env['res.partner'].sudo().create(partner_vals)
                
                if self.registration_id:
                    self.registration_id.sudo().write({'partner_id': partner.id})
                self.sudo().write({'partner_id': partner.id})

            selection_field = self._fields['charge_payment_method']
            selection_choices = selection_field.selection
            choices = selection_choices(self) if callable(selection_choices) else selection_choices
            payment_method_label = dict(choices).get(self.charge_payment_method, 'Not Specified')
            
            invoice_label = _('Chargeable Warranty Repair Service (%s) - Reason: %s') % (payment_method_label, self.charge_reason or '')
            price_unit = self.estimated_charge_amount or 0.0

        target_product_id = self.registration_id.product_id.id if self.registration_id and self.registration_id.product_id else (self.product_id.id if self.product_id else False)

        if not partner:
            raise UserError(_("Invoice generation stopped: No valid customer or vendor partner could be determined."))

        invoice_vals = {
            'move_type': move_type,
            'state': 'draft',
            'partner_id': partner.id, 
            'ref': _('Warranty Action [%s] for Claim: %s') % (self.resolution_type.upper(), self.name),
            'invoice_origin': self.name,
            'company_id': self.company_id.id if self.company_id else self.env.company.id,
            'invoice_line_ids': [(0, 0, {
                'name': invoice_label,
                'product_id': target_product_id,
                'quantity': 1.0,
                'price_unit': price_unit,
            })],
        }
        
        try:
            invoice = self.env['account.move'].create(invoice_vals)
            if invoice and invoice.invoice_line_ids:
                invoice.invoice_line_ids.write({'price_unit': price_unit})
                
            self.write({'invoice_ids': [(4, invoice.id)]})
            self.message_post(body=_("Automated Account Bridge: Draft %s %s created with amount %s for %s.") % (move_type, invoice.name, price_unit, partner.name))
        except Exception as e:
            self.message_post(body=_("Account Bridge Log: Failed to generate Invoice. Error: %s") % str(e))
    
    def action_view_linked_invoices(self):
        """Action for the smart button to view all generated invoices and bills"""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_out_invoice_type")
        
        if self.invoice_count > 1:
            action.update({
                'domain': [('id', 'in', self.invoice_ids.ids)],
                'view_mode': 'list,form', 
                'views': [(False, 'list'), (False, 'form')],
                'res_id': False,
                'name': _('Financial Documents'),
            })
        elif self.invoice_count == 1:
            action.update({
                'view_mode': 'form',
                'views': [(False, 'form')],
                'res_id': self.invoice_ids.id,
            })
        else:
            raise UserError(_("No financial documents have been generated yet for this claim."))
            
        return action

    @api.model
    def _cron_check_sla_breach(self):
        today = fields.Date.today()
        breached_claims = self.search([
            ('state', 'not in', ['resolved', 'rejected']),
            ('sla_deadline', '<', today)
        ])
        
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        
        for claim in breached_claims:
            existing_activity = self.env['mail.activity'].search([
                ('res_model', '=', 'ms.warranty.claim'),
                ('res_id', '=', claim.id),
                ('summary', '=', _("SLA Deadline Breached!"))
            ], limit=1)
            
            if not existing_activity:
                assign_user_id = claim.technician_id.id if claim.technician_id else claim.create_uid.id
                
                claim.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    date_deadline=today,
                    summary=_("SLA Deadline Breached!"),
                    note=_("The claim %s has breached its SLA deadline (%s). Please review immediately.") % (claim.name, claim.sla_deadline),
                    user_id=assign_user_id
                )
                claim.message_post(body=_("System Alert: This claim has breached its SLA deadline without being resolved or rejected."))