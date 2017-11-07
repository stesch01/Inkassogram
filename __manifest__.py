# -*- coding: utf-8 -*-
{
    'name': "Inkassogram",

    'summary': """
        inkassogram""",

    'description': """
        inkassogram
    """,

    'author': "UAB Pralo",
    'website': "http://www.pralo.eu",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'account', 'base_vat'],

    # always loaded
    'data': [
        'views/inherited_res_company.xml',
        'views/inherited_account_invoice_views.xml',
    ],
}