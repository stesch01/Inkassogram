# -*- coding: utf-8 -*-

import hashlib
import time
import re

from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from requests import Session
from requests.exceptions import RequestException


from odoo import models, fields, api, _
from lxml import etree
from odoo.exceptions import UserError
import datetime
import logging

logger = logging.getLogger(__name__)


class InkassogramAccountInvoice(models.Model):
    _inherit = 'account.invoice'

    inkasso_code = fields.Char(string='Inkasso code')
    xml_data = fields.Text(string='XML body')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('proforma', 'Pro-forma'),
        ('proforma2', 'Pro-forma'),
        ('open', 'Open'),
        ('inkasso', 'Inkasso'),
        ('error', 'Error'),
        ('paid', 'Paid'),
        ('cancel', 'Cancelled'),
    ], string='Status', index=True, readonly=True, default='draft',
        track_visibility='onchange', copy=False,
        help=" * The 'Draft' status is used when a user is encoding a new and unconfirmed Invoice.\n"
             " * The 'Pro-forma' status is used when the invoice does not have an invoice number.\n"
             " * The 'Open' status is used when user creates invoice, an invoice number is generated. It stays in the open status till the user pays the invoice.\n"
             " * The 'Inkasso' status is used when user sends invoice to Inkassogram\n"
             " * The 'Error' status is used when error occurred during invoice sending to Inkassogram\n"
             " * The 'Paid' status is set automatically when the invoice is paid. Its related journal entries may or may not be reconciled.\n"
             " * The 'Cancelled' status is used when user cancel invoice.")

    @api.multi
    def send_to_inkasso(self):
        self._validate_data()
        for invoice in self:
            header = {}
            date = datetime.date.today()
            api_url = 'https://api.inkassogram.se/API/createInvoiceBookkeeping'
            public_ip = ''
            if invoice.company_id.inkasso_public_ip:
                public_ip = invoice.company_id.inkasso_public_ip
            md_string = str(public_ip) + date.strftime('%Y%m%d') + str(invoice.company_id.inkasso_cust_key)
            hash_key = hashlib.md5(md_string).hexdigest()
            xml_data = invoice._generate_xml()
            if xml_data:
                invoice.xml_data = xml_data
            header.update({'Content-Type': 'text/xml',
                           'customerNo': str(invoice.company_id.inkasso_cust_number),
                           'key': hash_key})
            session = Session()
            retry_policy = Retry(
                                total=5,
                                method_whitelist=frozenset(['POST']),
                                backoff_factor=0.2,
                                status_forcelist=[404, 500, 502, 503, 504]
                                )
            session.mount('https://', HTTPAdapter(max_retries=retry_policy))
            try:
                response = session.post(api_url, headers=header, data=xml_data)
            except RequestException as e:  # This is the correct syntax
                raise UserError(_(
                    'An error have occurred - ' + str(e)))
            #removing namespace from response xml part, because lxml 3.5 which comes default with odoo does not support nsmap with None namespace
            xmlstring = re.sub('\\sxmlns="[^"]+"', '', response.content, count=1)
            root = etree.fromstring(xmlstring)
            status_code = root.find('response/statusCode')
            error_code = root.find('response/errorCode')
            if status_code is not None:
                invoice.inkasso_code = status_code.text
                if status_code.text == '1':
                    invoice._inkasso_done()
                else:
                    invoice._inkasso_error()
                    if error_code is not None:
                        invoice.inkasso_code = error_code.text
            else:
                raise UserError(_('Status Code not received, please contact your system administrator'))

    def _generate_xml(self):
        '''method to generate xml data part for inkassogram'''

        xmlns = "https://api.inkassogram.se/API/createInvoiceBookkeeping"
        xsi = "http://www.w3.org/2001/XMLSchema-instance"
        schemaLocation = "https://api.inkassogram.se/API/createInvoiceBookkeeping https://api.inkassogram.se/API/createInvoiceBookkeepingSchema1.0.xsd"

        root = etree.Element("{" + xmlns + "}methodCall", attrib={"{" + xsi + "}schemaLocation": schemaLocation},
                             nsmap={'xsi': xsi, None: xmlns})
        method_name = etree.SubElement(root, 'methodName')
        method_name.text = 'createInvoice'
        request = etree.SubElement(root, 'request')
        test_invoice = etree.SubElement(request, 'testInvoice')
        if self.company_id.inkasso_test_mode:
            test_invoice.text = 'true'
        else:
            test_invoice.text = 'false'
        make_invoice_reservation = etree.SubElement(request, 'makeInvoiceReservation')
        make_invoice_reservation.text = '0'
        force_to_send = etree.SubElement(request, 'forceToSend')
        force_to_send.text = '0'
        service = etree.SubElement(request, 'service')
        service.text = '1'
        print_setup = etree.SubElement(request, 'printSetup')
        print_setup.text = '1'
        ssn = etree.SubElement(request, 'ssn')
        ssn.text = str(self.partner_id.vat)
        invoice_ref = etree.SubElement(request, 'invoiceRef')
        if self.origin:
            invoice_ref.text = self.origin
        invoice_order_no = etree.SubElement(request, 'invoiceOrderNo')
        if self.number:
            invoice_order_no.text = self.number
        invoice_date = etree.SubElement(request, 'invoiceDate')
        unix_time_now = int(time.time())
        invoice_date.text = str(unix_time_now)
        if self.date_due:
            due_date = etree.SubElement(request, 'dueDate')
            due_date_unix_time = int(time.mktime(time.strptime(self.date_due, "%Y-%m-%d")))
            due_date.text = str(due_date_unix_time)
        callback = etree.SubElement(request, 'callback')
        mobile = etree.SubElement(request, 'mobile')
        mobile.text = str(self.partner_id.mobile)
        email = etree.SubElement(request, 'email')
        email.text = str(self.partner_id.email)
        order_no = etree.SubElement(request, 'orderNo')
        order_no.text = self.number
        our_ref = etree.SubElement(request, 'ourRef')
        your_ref = etree.SubElement(request, 'yourRef')

        invoice_rows = etree.SubElement(request, 'invoiceRows')
        for line in self.invoice_line_ids:
            row = etree.SubElement(invoice_rows, 'row')
            article_no = etree.SubElement(row, 'articleNo')
            article_no.text = str(line.product_id.id)
            text = etree.SubElement(row, 'text')
            line_name = line.name[:120]
            text.text = str(line_name)
            desc = etree.SubElement(row, 'desc')
            # TODO vat value must be changed in future versions
            # if line.invoice_line_tax_ids:
            #     vat = etree.SubElement(row, 'vat')
            #     vat.text = str(int(line.invoice_line_tax_ids.amount))
            vat = etree.SubElement(row, 'vat')
            vat.text = '25'
            quantity = etree.SubElement(row, 'quantity')
            if line.quantity:
                quantity.text = str(line.quantity)
            # TODO price unit field must include VAT
            price = etree.SubElement(row, 'price')
            price.text = str(int(line.price_unit))
            unit = etree.SubElement(row, 'unit')
            if line.product_id.uom_id and line.product_id.uom_id.name:
                unit.text = str(line.product_id.uom_id.name)
            if line.discount:
                discount = etree.SubElement(row, 'discount')
                discount.text = str(line.discount)
            bookkeeping_account = etree.SubElement(row, 'bookkeepingAccount')
            if line.account_id:
                bookkeeping_account.text = str(line.account_id.id)
            profit_unit = etree.SubElement(row, 'profitUnit')
            if line.company_id:
                profit_unit.text = str(line.company_id.id)
            project = etree.SubElement(row, 'project')
            if line.account_analytic_id:
                project.text = line.account_analytic_id.id
        comments = etree.SubElement(request, 'comments')
        if self.comment:
            comments.text = str(self.comment)
        billing_var = etree.SubElement(request, 'billingVar')
        attached_document = etree.SubElement(request, 'attachedDocument')
        attached_document_md5 = etree.SubElement(request, 'attachedDocumentMd5')

        xml_string = etree.tostring(
            root, pretty_print=True, encoding='UTF-8', xml_declaration=True)
        return xml_string

    def _validate_data(self):
        errors_msg = ''
        errors = 0
        for invoice in self:
            if not invoice.number:
                errors_msg += (_("Invoice - %s, dont have invoice number\n").decode('utf-8') % (invoice.id))
                errors += 1
            if not invoice.company_id.inkasso_cust_number:
                errors_msg += (
                _("Invoice - %s, company - %s - dont have Inkassogram Customer Number set\n").decode('utf-8') % (
                invoice.number, invoice.company_id.name))
                errors += 1
            if not invoice.company_id.inkasso_cust_key:
                errors_msg += (
                _("Invoice - %s, company - %s - dont have Inkassogram Customer Key set\n").decode('utf-8') % (
                invoice.number, invoice.company_id.name))
                errors += 1
            if not invoice.partner_id.mobile:
                errors_msg += (_("Invoice - %s, partner %s dont have mobile number set\n").decode('utf-8') % (
                invoice.number, invoice.partner_id.name))
                errors += 1
            if not invoice.partner_id.vat:
                errors_msg += (_("Invoice - %s, partner %s dont SSN(TIN) number set\n").decode('utf-8') % (
                invoice.number, invoice.partner_id.name))
                errors += 1
            if not invoice.partner_id.email:
                errors_msg += (_("Invoice - %s, partner %s dont have email set\n").decode('utf-8') % (
                invoice.number, invoice.partner_id.name))
                errors += 1
            if not invoice.invoice_line_ids:
                errors_msg += (_("Invoice - %s, dont have any invoice lines\n").decode('utf-8') % (invoice.number))
                errors += 1
            if not invoice.partner_id.street:
                errors_msg += (_("Invoice - %s, partner %s dont have street field set\n").decode('utf-8') % (
                invoice.number, invoice.partner_id.name))
                errors += 1
            if not invoice.partner_id.street2:
                errors_msg += (_("Invoice - %s, partner %s dont have street2 field set\n").decode('utf-8') % (
                invoice.number, invoice.partner_id.name))
                errors += 1
            for line in invoice.invoice_line_ids:
                if not line.name:
                    errors_msg += (
                    _("Invoice line - %s, dont have description set\n").decode('utf-8') % (line.product_id.name))
                    errors += 1
                if not line.price_unit:
                    errors_msg += (
                    _("Invoice line - %s, dont have price set\n").decode('utf-8') % (line.product_id.name))
                    errors += 1
        if errors:
            raise UserError(errors_msg)

    @api.multi
    def _inkasso_done(self):
        self.write({'state': 'inkasso'})

    @api.multi
    def _inkasso_error(self):
        self.write({'state': 'error'})
