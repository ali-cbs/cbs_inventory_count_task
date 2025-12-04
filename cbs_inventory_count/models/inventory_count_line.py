# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class InventoryCountLine(models.Model):
    _name = "inventory.count.line"
    _description = "Inventory Count Line"

    session_id = fields.Many2one("inventory.count.session", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True)
    product_category_id = fields.Many2one(related="product_id.categ_id", string="Category", store=True)
    location_id = fields.Many2one("stock.location", required=True)
    lot_id = fields.Many2one("stock.lot", string="Lot/Serial")
    package_id = fields.Many2one("stock.quant.package", string="Package")
    uom_id = fields.Many2one(related="product_id.uom_id", string="UoM")

    qty_system = fields.Float(string="System Qty", readonly=True)
    qty_counted = fields.Float(string="Counted Qty")
    qty_review_counted = fields.Float(string="Review Counted Qty")
    
    # Delta - يُحسب أولاً
    qty_delta = fields.Float(string="Delta", compute="_compute_delta", store=True)

    # Values - تُحسب بعد Delta
    product_value_before = fields.Float(string="Value Before", compute="_compute_values", store=True) 
    count_net_difference_value = fields.Float(string="Net Diff Value", compute="_compute_values", store=True)
    variant_percentage_value = fields.Float(string="Var %", compute="_compute_values", store=True)
    
    # KPI
    accepted_product_diff_kpi = fields.Float(
        related="product_category_id.accepted_diff_kpi_percent",
        string="KPI %",
        readonly=True
    )

    # Audit info
    barcode_scanned = fields.Char(string="Scanned Barcode")
    scanned_by = fields.Many2one("res.users", string="Scanned By", default=lambda self: self.env.user)
    scanned_at = fields.Datetime(string="Scanned At", default=fields.Datetime.now)
    note = fields.Char(string="Note")
    state = fields.Selection(related="session_id.state", store=True)

    @api.depends('qty_system', 'qty_counted', 'qty_review_counted', 'state')
    def _compute_delta(self):
        """حساب الفرق في الكمية"""
        for line in self:
            # التحقق من المرحلة
            if line.state in ['review', 'approval', 'done', 'rejected']:
                # إذا في Review Qty، استخدمها
                if line.qty_review_counted:
                    line.qty_delta = line.qty_review_counted - line.qty_system
                else:
                    # إذا ما في Review Qty، استخدم Counted Qty
                    line.qty_delta = line.qty_counted - line.qty_system
            else:
                # في مرحلة Draft أو In-Progress
                line.qty_delta = line.qty_counted - line.qty_system
            
            _logger.info(f"Line {line.id}: Delta = {line.qty_delta} (System: {line.qty_system}, Counted: {line.qty_counted}, Review: {line.qty_review_counted}, State: {line.state})")

    @api.depends('qty_delta', 'qty_system', 'product_id.standard_price')
    def _compute_values(self):
        """حساب القيم والنسب"""
        for line in self:
            # جلب السعر
            cost = line.product_id.standard_price or 0.0
            
            # 1. قيمة المنتج قبل الجرد
            line.product_value_before = line.qty_system * cost
            
            # 2. صافي فرق القيمة
            line.count_net_difference_value = line.qty_delta * cost
            
            # 3. نسبة الفرق في الكمية
            if line.qty_system and abs(line.qty_system) > 0.001:
                # حساب النسبة بشكل صحيح
                percentage = (abs(line.qty_delta) / abs(line.qty_system)) * 100.0
                line.variant_percentage_value = round(percentage, 2)
            else:
                # الكمية في النظام = 0
                if abs(line.qty_delta) > 0.001:
                    line.variant_percentage_value = 100.0
                else:
                    line.variant_percentage_value = 0.0
            
            # Debug Log
            _logger.info(f"""
            ========== Line {line.id} ==========
            Product: {line.product_id.display_name}
            Cost: {cost}
            System Qty: {line.qty_system}
            Delta: {line.qty_delta}
            Value Before: {line.product_value_before}
            Net Diff Value: {line.count_net_difference_value}
            Var %: {line.variant_percentage_value}
            ===================================
            """)