# -*- coding: utf-8 -*-
# Jalankan:
#   odoo shell -d DBNAME < /root/seed_products.py

import logging, time
_logger = logging.getLogger("seed_products")

# ========= PARAMETER =========
N_PRODUCTS         = 40_000   # jumlah produk yang dibuat
BATCH              = 1_000    # besaran batch create (atur sesuai RAM)
OP_MIN             = 5.0
OP_MAX             = 10.0
OP_TRIGGER         = None     # None / 'manual' kalau mau trigger manual

# Supplier & route (untuk Order->Purchase di Replenishment)
MAKE_VENDOR_ROUTE  = True
FIXED_VENDOR_ID    = 429       # ID vendor, fallback auto-create kalau gak ada
VENDOR_SET_LIMIT   = 5_000     # subset produk yang diberi supplierinfo + route Buy

# Quants/Forecast (biar Qty to Order > 0)
MAKE_QUANTS        = True      # set True agar forecast 0 → muncul di To Replenish
QUANT_SET_LIMIT    = 10_000    # subset produk untuk di-set stoknya
QUANT_QTY          = 0         # target qty (0 = kosong)

# Multi-company
COMPANY_FORCE_NONE = False     # True → set company_id=False saat create product
# ============================

# ========= START =========
try:
    env
except NameError as e:
    raise RuntimeError("Jalankan script ini di 'odoo shell' (env tidak tersedia).") from e

t0 = time.time()

sudo_env = env
PT  = sudo_env['product.template'].sudo().with_context(active_test=False)
PP  = sudo_env['product.product'].sudo().with_context(active_test=False)
OP  = sudo_env['stock.warehouse.orderpoint'].sudo()
WH  = sudo_env['stock.warehouse'].sudo()
LOC = sudo_env['stock.location'].sudo()
QNT = sudo_env['stock.quant'].sudo()
RP  = sudo_env['res.partner'].sudo()
SUP = sudo_env['product.supplierinfo'].sudo()

wh = WH.search([], limit=1)
if not wh:
    raise Exception("Tidak ada warehouse. Install & konfigur Inventory dulu.")
uom_unit = sudo_env.ref('uom.product_uom_unit')

print(f"DB: {sudo_env.cr.dbname} | WH: {wh.code}")

# 1) BUAT PRODUCT TEMPLATES
to_create, created_pt = [], 0
for i in range(1, N_PRODUCTS + 1):
    vals = {
        'name': f'LoadTest Product {i:05d}',
        'type': 'consu',          # build Odoo 18 kamu: consu/service/combo
        'uom_id': uom_unit.id,
        'uom_po_id': uom_unit.id,
        'active': True,
        'is_storable': True,      # fixed
    }
    if COMPANY_FORCE_NONE:
        vals['company_id'] = False
    to_create.append(vals)

    if len(to_create) >= BATCH:
        PT.create(to_create)
        created_pt += len(to_create)
        to_create = []
        if created_pt % (BATCH * 5) == 0:
            print(f"  - templates created: {created_pt}")
if to_create:
    PT.create(to_create)
    created_pt += len(to_create)

sudo_env.cr.commit()
print(f"[1/4] Templates created: {created_pt} (elapsed {time.time()-t0:.1f}s)")

# Ambil VARIANTS
templates = PT.search([('name', 'ilike', 'LoadTest Product')], limit=N_PRODUCTS, order='id')
products  = templates.mapped('product_variant_id')
print(f"[1.5/4] Variants fetched: {len(products)}")

# 2) BUAT ORDERPOINTS
vals, created_op = [], 0
for p in products:
    op_vals = {
        'warehouse_id': wh.id,
        'product_id': p.id,
        'product_min_qty': OP_MIN,
        'product_max_qty': OP_MAX,
        'qty_multiple': 1.0,
        'location_id': wh.lot_stock_id.id,
        'company_id': wh.company_id.id,
        'active': True,
    }
    if OP_TRIGGER in ('manual', 'auto'):
        op_vals['trigger'] = OP_TRIGGER
    vals.append(op_vals)

    if len(vals) >= BATCH:
        OP.create(vals)
        created_op += len(vals)
        vals = []
        if created_op % (BATCH * 5) == 0:
            print(f"  - orderpoints created: {created_op} / {len(products)}")
if vals:
    OP.create(vals)
    created_op += len(vals)

sudo_env.cr.commit()
op_count = OP.search_count([('product_id', 'in', products.ids), ('warehouse_id', '=', wh.id)])
print(f"[2/4] Orderpoints created: {created_op} (verify search_count={op_count}) (elapsed {time.time()-t0:.1f}s)")

# 3) SUPPLIERINFO + ROUTE BUY
if MAKE_VENDOR_ROUTE and VENDOR_SET_LIMIT > 0:
    route_buy = sudo_env.ref('purchase_stock.route_warehouse0_buy', raise_if_not_found=False) \
        or sudo_env['stock.route'].sudo().search([('name', 'ilike', 'Buy')], limit=1)

    vendor = RP.browse(FIXED_VENDOR_ID)
    if not vendor.exists():
        vendor = RP.create({'name': 'Seed Vendor', 'supplier_rank': 1})
        print(f"  - Vendor {FIXED_VENDOR_ID} tidak ditemukan, dibuat baru: {vendor.id}")

    subset = products[:VENDOR_SET_LIMIT]
    added, batch_sup = 0, []
    tmpl_to_route = set()

    for p in subset:
        batch_sup.append({
            'partner_id': vendor.id,
            'product_tmpl_id': p.product_tmpl_id.id,
            'price': 10.0,
        })
        tmpl_to_route.add(p.product_tmpl_id.id)

        if len(batch_sup) >= BATCH:
            SUP.create(batch_sup)
            added += len(batch_sup)
            batch_sup = []
            if added % (BATCH * 5) == 0:
                print(f"  - supplierinfos added: {added} / {VENDOR_SET_LIMIT}")
    if batch_sup:
        SUP.create(batch_sup)
        added += len(batch_sup)

    if route_buy and tmpl_to_route:
        tmpl_ids = list(tmpl_to_route)
        for i in range(0, len(tmpl_ids), BATCH):
            chunk = PT.browse(tmpl_ids[i:i+BATCH])
            for t in chunk:
                if route_buy.id not in t.route_ids.ids:
                    t.write({'route_ids': [(4, route_buy.id)]})

    sudo_env.cr.commit()
    print(f"[3/4] Supplierinfo created untuk {added} produk (vendor_id={vendor.id}); route Buy aktif (elapsed {time.time()-t0:.1f}s)")

# 4) QUANTS
if MAKE_QUANTS and QUANT_SET_LIMIT > 0:
    loc = LOC.search([('usage', '=', 'internal')], limit=1)
    if not loc:
        raise Exception("Tidak ada internal location.")
    subset = products[:QUANT_SET_LIMIT]
    updated = 0
    for p in subset:
        current_qty = QNT._get_available_quantity(p, loc)
        target_qty  = QUANT_QTY
        delta = target_qty - current_qty
        if delta:
            QNT._update_available_quantity(p, loc, delta)
            updated += 1
            if updated % (BATCH * 5) == 0:
                print(f"  - quants updated: {updated} / {QUANT_SET_LIMIT}")
    sudo_env.cr.commit()
    print(f"[4/4] Quants set for: {updated} products (qty={QUANT_QTY}) (elapsed {time.time()-t0:.1f}s)")

# Ringkasan
print("===================================================")
print(f"[OK] Seed selesai dalam {time.time()-t0:.1f}s")
print(f"  - products (variants): {len(products)}")
print(f"  - orderpoints:         {op_count} (wh={wh.code})")
if MAKE_VENDOR_ROUTE:
    print(f"  - vendor/route Buy:    up to {min(VENDOR_SET_LIMIT, len(products))} (vendor_id={vendor.id})")
if MAKE_QUANTS:
    print(f"  - quants updated:      up to {min(QUANT_SET_LIMIT, len(products))} → qty={QUANT_QTY}")
print("Buka: Inventory → Operations → Replenishment (clear filter, pilih Warehouse=WH).")
print("===================================================")
