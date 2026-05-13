# -*- coding: utf-8 -*-
# Part of Mehedi Hasan Rakib. See LICENSE file for full copyright and licensing details.

{
    'name': 'Warranty QR Registration & Claim Portal',
    'version': '19.0.1.0.0',
    'summary': 'QR warranty registration, warranty card, claim portal, and service workflow.',
    'sequence': 1,
    'description': "QR-based Product Warranty Registration and Claim Portal.",
    'category': 'Sales/After-Sales',
    'author': 'MindSynth Technologies',
    'maintainer': 'Mehedi Hasan Rakib',
    'website': 'https://mindsynthtech.com',
    'license': 'OPL-1',
    'depends': [
        'base',
        'mail',
        'product',
        'website',
        'portal',
    ],
    'data': [
        # Security
        # 'security/security.xml',
        'security/ir.model.access.csv',
        # 'security/record_rules.xml',
        
        # Data
        # 'data/sequence.xml',
        # 'data/mail_activity_type.xml',
        # 'data/mail_template.xml',
        # 'data/warranty_claim_stage_data.xml',
        # 'data/warranty_issue_type_data.xml',
        # 'data/warranty_resolution_data.xml',
        # 'data/ir_cron.xml',
        
        # Views
         'views/warranty_policy_views.xml',
         'views/warranty_menu.xml',
        # 'views/warranty_registration_views.xml',
        # 'views/warranty_claim_views.xml',
        # 'views/warranty_service_center_views.xml',
        # 'views/warranty_dashboard_views.xml',
         'views/product_template_views.xml',
        # 'views/res_partner_views.xml',
        # 'views/res_config_settings_views.xml',
        
        # Templates
        # 'templates/warranty_public_templates.xml',
        # 'templates/warranty_portal_templates.xml',
        # 'templates/warranty_email_templates.xml',
        
        # Reports
        # 'reports/warranty_certificate_report.xml',
        # 'reports/warranty_card_report.xml',
        # 'reports/warranty_claim_report.xml',
        # 'reports/warranty_label_report.xml',
    ],
    # 'demo': [
    #  'data/warranty_demo_data.xml',
    #],
    'images': [
        'static/description/banner.png',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}