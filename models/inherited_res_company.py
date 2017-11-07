# -*- coding: utf-8 -*-

from odoo import models, fields


class InkassogramResPartner(models.Model):
    _inherit = 'res.company'

    inkasso_cust_number = fields.Char(string='Inkassogram Customer Number')
    inkasso_cust_key = fields.Char(string='Inkassogram Customer Key')
    inkasso_public_ip = fields.Char(string='Inkassogram Public Server IP')
    inkasso_test_mode = fields.Boolean(string='Inkassogam Test Mode')
