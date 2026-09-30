{
    'name': 'Gestion Immobilière',
    'version': '18.0.1.0.0',
    'category': 'Immobilier',
    'summary': 'Pilotage du patrimoine, des baux, loyers, factures et créances',
    'description': '''
Gestion Immobilière offre un pilotage complet du patrimoine immobilier : propriétés,
locaux, locataires, baux, échéances, facturation, encaissements et recouvrement.

Son tableau de bord interactif met en avant les indicateurs utiles à la décision :
taux d’occupation, locaux disponibles, créances locataires, factures non réglées,
retards et performance des encaissements.
''',
    'author': 'PrimeTech Services',
    'website': 'https://primetechafrik.com',
    'license': 'LGPL-3',
    'depends': ['account', 'contacts', 'om_account_accountant', 'maintenance', 'mail', 'web'],
    'data': [
        'security/estate_security.xml',
        'security/ir.model.access.csv',
        'data/estate_sequences.xml',
        'data/estate_cron.xml',
        'data/estate_data.xml',
        'views/estate_property_views.xml',
        'views/estate_unit_views.xml',
        'views/estate_maintenance_views.xml',
        'views/res_partner_views.xml',
        'views/estate_lease_views.xml',
        'views/estate_schedule_views.xml',
        'views/estate_deposit_views.xml',
        'views/estate_charge_views.xml',
        'views/account_move_views.xml',
        'views/estate_performance_views.xml',
        'views/estate_terminology_views.xml',
        'views/res_config_settings_views.xml',
        'views/estate_menu_views.xml',
        'report/estate_reports.xml',
        'report/estate_lease_report.xml',
        'report/estate_rent_receipt.xml',
        'report/estate_tenant_statement.xml',
    ],
    'demo': ['demo/estate_demo.xml'],
    'assets': {
        'web.assets_backend': [
            'primetech_estate_management/static/src/dashboard/estate_dashboard.js',
            'primetech_estate_management/static/src/dashboard/estate_dashboard_v2.xml',
            'primetech_estate_management/static/src/dashboard/estate_dashboard.scss',
            'primetech_estate_management/static/src/dashboard/estate_dashboard_v2.scss',
        ],
    },
    'application': True,
    'installable': True,
}
