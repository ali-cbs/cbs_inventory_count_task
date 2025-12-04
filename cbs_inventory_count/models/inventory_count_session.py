# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

# -------------------------------------------------------------------------
# Requirement 11: Add KPI percentage per product category
# -------------------------------------------------------------------------
class ProductCategory(models.Model):
    _inherit = "product.category"

    accepted_diff_kpi_percent = fields.Float(
        string="KPI %",
        help="Allowed percentage of difference before flagging.",
        default=0.0
    )

class InventoryCountSession(models.Model):
    _name = "inventory.count.session"
    _description = "Inventory Count Session"
    _order = "create_date desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string="Session Name",
        required=True,
        default=lambda self: (fields.Date.context_today(self)).strftime("Count-%Y%m%d"),
    )

    is_finance_manager = fields.Boolean(
        string="Is Finance Manager",
        compute="_compute_is_finance_manager"
    )

    @api.depends('finance_manager_id')
    def _compute_is_finance_manager(self):
        for rec in self:
            rec.is_finance_manager = (self.env.user == rec.finance_manager_id)

    # Req 5: Stages
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("in_progress", "In-Progress"),
            ("review", "Review"),
            ("approval", "Approval"),
            ("done", "Done"),
            ("rejected", "Rejected"),
        ],
        default="draft",
        tracking=True,
    )

    date_start = fields.Datetime(string="Start Time", default=fields.Datetime.now)
    date_end = fields.Datetime(string="End Time")
    
    # Req 4: Effective Date
    count_effective_date = fields.Date(
        string="Count Effective Date",
        default=fields.Date.context_today,
        help="Date used to reflect the Stock Valuation Layer.",
    )

    # Req 9: Review/Approval Dates
    review_date = fields.Datetime(string="Review Date", readonly=True, copy=False)
    approval_date = fields.Datetime(string="Approval Date", readonly=True, copy=False)
    rejection_date = fields.Datetime(string="Rejection Date", readonly=True, copy=False)
    rejection_reason = fields.Text(string="Rejection Reason", readonly=True, copy=False)

    # Req 1: Attendees
    attendee_ids = fields.Many2many(
        comodel_name="res.users",
        string="Attendees",
        domain="[('share', '=', False)]",
        help="Employees participating in the count process",
    )

    # Req 2 & 3: Warehouse/Location & Filters
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse")
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        domain="[('warehouse_id', '=', warehouse_id), ('usage', 'in', ['internal'])]",
    )
    inventory_filter = fields.Selection(
        selection=[
            ('available', 'All available quantities'),
            ('include_zero', 'Include zero quantities'),
        ],
        string="Inventory Filter",
        required=True,
        default='available',
    )

    # ربط مع الموديل الموجود في الملف الآخر
    line_ids = fields.One2many(
        "inventory.count.line",
        "session_id",
        string="Count Lines",
    )

    finance_manager_id = fields.Many2one(
        "res.users",
        string="Finance Manager",
        tracking=True
    )
    
    # Computed totals
    line_count = fields.Integer(string="Lines", compute="_compute_totals")
    qty_counted_total = fields.Float(string="Total Counted Qty", compute="_compute_totals")
    qty_delta_total = fields.Float(string="Total Delta", compute="_compute_totals")

    # Req 16 (a-h): Calculated Outcomes
    total_diff_qty_positive = fields.Float(string="Total Diff Qty (+) Count", compute="_compute_calculated_outcomes") 
    total_diff_qty_negative = fields.Float(string="Total Diff Qty (-) Count", compute="_compute_calculated_outcomes") 
    total_diff_value_positive = fields.Float(string="Total Diff Val (+) Count", compute="_compute_calculated_outcomes") 
    total_diff_value_negative = fields.Float(string="Total Diff Val (-) Count", compute="_compute_calculated_outcomes") 
    total_diff_value_net = fields.Float(string="Total Diff Val (Net)", compute="_compute_calculated_outcomes") 
    
    total_diff_review_value_positive = fields.Float(string="Review Diff Val (+)", compute="_compute_calculated_outcomes") 
    total_diff_review_value_negative = fields.Float(string="Review Diff Val (-)", compute="_compute_calculated_outcomes") 
    total_diff_review_value_net = fields.Float(string="Review Diff Val (Net)", compute="_compute_calculated_outcomes") 
    
    note = fields.Text(string="Notes")
    user_id = fields.Many2one("res.users", string="Owner", default=lambda self: self.env.user)

    @api.depends("line_ids.qty_counted", "line_ids.qty_delta")
    def _compute_totals(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)
            rec.qty_counted_total = sum(rec.line_ids.mapped("qty_counted"))
            rec.qty_delta_total = sum(rec.line_ids.mapped("qty_delta"))

    @api.depends(
        "line_ids.qty_delta",
        "line_ids.count_net_difference_value",
        "line_ids.qty_review_counted",
        "line_ids.product_id.standard_price"
    )
    def _compute_calculated_outcomes(self):
        for rec in self:
            lines = rec.line_ids
            # a & b
            rec.total_diff_qty_positive = sum(l.qty_delta for l in lines if l.qty_delta > 0)
            rec.total_diff_qty_negative = sum(l.qty_delta for l in lines if l.qty_delta < 0)
            
            # c & d & e
            rec.total_diff_value_positive = sum(l.count_net_difference_value for l in lines if l.count_net_difference_value > 0)
            rec.total_diff_value_negative = sum(l.count_net_difference_value for l in lines if l.count_net_difference_value < 0)
            rec.total_diff_value_net = rec.total_diff_value_positive + rec.total_diff_value_negative
            
            # f & g & h (Review Specifics)
            r_pos = 0.0
            r_neg = 0.0
            for line in lines:
                if line.qty_review_counted:
                    diff = line.qty_review_counted - line.qty_system
                    cost = line.product_id.standard_price or 0.0
                    val = diff * cost
                    if val > 0: r_pos += val
                    else: r_neg += val
            
            rec.total_diff_review_value_positive = r_pos
            rec.total_diff_review_value_negative = r_neg
            rec.total_diff_review_value_net = r_pos + r_neg

    def action_generate_lines(self):
        self.ensure_one()

        # 1. التحقق من المستودع بدلاً من الموقع
        # إذا كنت تفضل أن يكون المستودع إجباريًا (أكثر منطقية)
        if not self.warehouse_id:
            raise UserError(_("Please select a Warehouse first."))

        self.line_ids.unlink() 
        
        # 2. بناء مجال البحث (Domain) ديناميكياً
        domain = []
        
        # إذا تم اختيار موقع محدد (جرد جزئي للموقع)
        if self.location_id:
            # نبحث فقط في هذا الموقع
            domain.append(('location_id', '=', self.location_id.id))
        else: 
            # إذا لم يتم اختيار موقع، نبحث عن جميع المواقع الداخلية التابعة للمستودع
            # نحدد أولاً المواقع الداخلية التابعة للمستودع المختار
            location_ids = self.env['stock.location'].search([
                ('warehouse_id', '=', self.warehouse_id.id), 
                ('usage', 'in', ['internal'])
            ]).ids
            
            if not location_ids:
                raise UserError(_("No internal locations found in the selected warehouse."))
                
            # نبحث عن السجلات في جميع هذه المواقع
            domain.append(('location_id', 'in', location_ids))

        # 3. إضافة شرط فلترة الكمية (كما في الكود الأصلي)
        if self.inventory_filter == 'available':
            domain.append(('quantity', '>', 0))
        
        # 4. تنفيذ البحث واستكمال إنشاء السطور
        quants = self.env['stock.quant'].search(domain)
        vals = []
        for q in quants:
            vals.append({
                'session_id': self.id,
                'product_id': q.product_id.id,
                'location_id': q.location_id.id,
                'lot_id': q.lot_id.id,
                'package_id': q.package_id.id,
                'qty_system': q.quantity,
                'qty_counted': 0, 
            })
            
        self.env['inventory.count.line'].create(vals)
        self.state = 'in_progress'

    def action_submit_count(self):
        for rec in self:
            for line in rec.line_ids:
                line.qty_review_counted = line.qty_counted
            rec.write({
                "state": "review",
                "review_date": fields.Datetime.now()
            })

    def action_validate(self):
        if not self.finance_manager_id:
            raise UserError(_('Please assign a Finance Manager first.'))
        
        self.write({
            "state": "approval",
            "approval_date": fields.Datetime.now()
        })
        
        msg = _("Inventory Count %s needs approval.") % self.name
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=self.finance_manager_id.id,
            summary=_("Approve Inventory Count"),
            note=msg
        )

    def action_approved(self):
        self.write({"state": "done", "date_end": fields.Datetime.now()})
        return True

    def action_refuse_recount(self):
        return self._open_refuse_wizard('recount')

    def action_rejected(self):
        return self._open_refuse_wizard('reject')

    def _open_refuse_wizard(self, action_type):
        return {
            'name': _('Reason'),
            'type': 'ir.actions.act_window',
            'res_model': 'inventory.count.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_session_id': self.id, 'default_action_type': action_type}
        }
    
    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        """Allow attendees to see sessions they're part of"""
        # إذا المستخدم مش أدمن ومش مدير مخزون
        if not self.env.user.has_group('base.group_system') and \
           not self.env.user.has_group('stock.group_stock_manager'):
            # أضف شرط: إما المستخدم هو الـ owner أو موجود في attendees
            if domain is None:
                domain = []
            domain = ['|', ('user_id', '=', self.env.uid), 
                      ('attendee_ids', 'in', self.env.uid)] + domain
        
        return super(InventoryCountSession, self).search_read(
            domain=domain, fields=fields, offset=offset, limit=limit, order=order
        )





class InventoryCountRefuseWizard(models.TransientModel):
    _name = "inventory.count.refuse.wizard"
    _description = "Inventory Count Refuse Wizard"

    session_id = fields.Many2one('inventory.count.session', required=True)
    reason = fields.Text(string="Reason", required=True)
    action_type = fields.Selection([('recount', 'Recount'), ('reject', 'Reject')], required=True)

    def action_confirm(self):
        self.ensure_one()
        session = self.session_id
        session.message_post(body=f"Action: {self.action_type}. Reason: {self.reason}")
        if self.action_type == 'recount':
            session.write({"state": "in_progress"})
        elif self.action_type == 'reject':
            session.write({
                "state": "rejected",
                "rejection_date": fields.Datetime.now(),
                "rejection_reason": self.reason
            })
        return {'type': 'ir.actions.act_window_close'}