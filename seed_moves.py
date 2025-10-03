# -*- coding: utf-8 -*-
# Jalankan:
#   odoo shell -d DBNAME < /root/seed_moves.py
#
# Catatan:
# - Skrip ini mengasumsikan produk "LoadTest Product ...." sudah dibuat.
# - Kamu bilang ingin "Track Inventory = True" → pastikan sudah dieksekusi
#   (atau jalankan dulu skrip enable_inventory_tracking kamu).
# - Untuk tipe 'service' & 'combo' akan di-skip. 'consu' akan dipakai.
# - Tidak memunculkan wizard; langsung confirm → assign → isi qty_done → _action_done().

from datetime import datetime

# ========= PARAMETER =========
PRODUCT_NAME_PREFIX      = 'LoadTest Product'  # prefix dari seed kamu
PRODUCT_LIMIT_FOR_MOVES  = 3000               # subset produk untuk transaksi (biar cepat)

COMMIT_EVERY_PICKINGS    = 5                  # commit tiap n picking

# Receipts (Vendor -> Stock)
MAKE_RECEIPTS            = True
RECEIPT_NUM_PICKS        = 50
RECEIPT_LINES_PER_PICK   = 50
RECEIPT_QTY_PER_LINE     = 10.0

# Internal Transfers (Stock -> Internal2)
MAKE_INTERNALS           = True
INTERNAL_NUM_PICKS       = 30
INTERNAL_LINES_PER_PICK  = 50
INTERNAL_QTY_PER_LINE    = 3.0

# Deliveries (Stock -> Customer)
MAKE_DELIVERIES          = True
DELIVERY_NUM_PICKS       = 50
DELIVERY_LINES_PER_PICK  = 50
DELIVERY_QTY_PER_LINE    = 2.0
# ============================

try:
    env
except NameError as e:
    raise RuntimeError("Jalankan script ini di 'odoo shell'.") from e

sudo = env
WH   = sudo['stock.warehouse'].search([], limit=1)
if not WH:
    raise Exception("Tidak ada warehouse. Install & konfigur Inventory dulu.")

PT   = sudo['product.template'].sudo()
PP   = sudo['product.product'].sudo()
PK   = sudo['stock.picking'].sudo()
MV   = sudo['stock.move'].sudo()
ML   = sudo['stock.move.line'].sudo()
LOC  = sudo['stock.location'].sudo()
RP   = sudo['res.partner'].sudo()

uom_unit = sudo.ref('uom.product_uom_unit')

# Ambil produk: hindari service & combo
products = PP.search([
    ('product_tmpl_id.name', 'ilike', PRODUCT_NAME_PREFIX),
    ('product_tmpl_id.type', 'not in', ['service', 'combo']),
], order='id', limit=PRODUCT_LIMIT_FOR_MOVES)

print(f"DB: {env.cr.dbname} | WH: {WH.code} | Products for moves: {len(products)}")

if not products:
    raise Exception("Tidak menemukan produk yang cocok untuk transaksi.")

# Lokasi standar
supplier_loc = LOC.search([('usage', '=', 'supplier')], limit=1) or \
               LOC.create({'name': 'Seed Supplier', 'usage': 'supplier'})
customer_loc = LOC.search([('usage', '=', 'customer')], limit=1) or \
               LOC.create({'name': 'Seed Customer', 'usage': 'customer'})
stock_loc    = WH.lot_stock_id

# Lokasi internal tambahan (tujuan internal transfer)
internal2 = LOC.search([
    ('usage', '=', 'internal'),
    ('id', '!=', stock_loc.id),
    ('company_id', '=', WH.company_id.id),
], limit=1)
if not internal2:
    internal2 = LOC.create({
        'name': f'{WH.code} Extra Stock',
        'usage': 'internal',
        'location_id': stock_loc.id,
        'company_id': WH.company_id.id,
    })

# Partner vendor & customer
vendor = RP.search([('supplier_rank', '>', 0)], limit=1) or RP.create({'name': 'Seed Vendor', 'supplier_rank': 1})
customer = RP.search([('customer_rank', '>', 0)], limit=1) or RP.create({'name': 'Seed Customer', 'customer_rank': 1})

# Picking types
picking_type_in  = WH.in_type_id
picking_type_out = WH.out_type_id
picking_type_int = WH.int_type_id

def _window(lst, size, offset):
    """Ambil window elemen 'size' dari list dengan offset melingkar."""
    n = len(lst)
    if n == 0:
        return []
    start = (offset * size) % n
    chunk = lst[start:start+size]
    if len(chunk) < size:
        chunk += lst[0:(size - len(chunk))]
    return chunk

def _create_moves_lines(picking, src, dest, product_ids, qty_each):
    """Buat stock.move untuk setiap product_id, lalu isi move_line qty_done."""
    move_vals = []
    for pid in product_ids:
        move_vals.append((0, 0, {
            'name': f'{picking.name or "SEED"}',
            'product_id': pid,
            'product_uom_qty': qty_each,          # planned qty
            'product_uom': uom_unit.id,
            'location_id': src.id,
            'location_dest_id': dest.id,
            'company_id': WH.company_id.id,
        }))

    picking.write({'move_ids_without_package': move_vals})

    # Confirm & try assign
    picking.action_confirm()
    try:
        picking.action_assign()
    except Exception:
        # Untuk consumable / no-reservation, assign bisa gagal → lanjut manual lines
        pass

    # Pastikan ada move_line dengan qty_done terisi
    for mv in picking.move_ids_without_package:
        done_qty = qty_each
        if not mv.move_line_ids:
            ML.create({
                'move_id': mv.id,
                'product_id': mv.product_id.id,
                'product_uom_id': mv.product_uom.id,
                'qty_done': done_qty,
                'location_id': src.id,
                'location_dest_id': dest.id,
                'company_id': WH.company_id.id,
                # lot_id bisa ditambahkan kalau perlu tracking lot/serial
            })
        else:
            # isi qty_done pada existing move_line pertama
            # (untuk kasus assigned)
            ml = mv.move_line_ids[0]
            ml.qty_done = done_qty

def _batch_picks(picking_type, src, dest, partner, num_picks, lines_per_pick, qty_each, label):
    if num_picks <= 0 or lines_per_pick <= 0 or qty_each <= 0:
        return 0

    prod_ids = products.ids
    created = 0
    for i in range(num_picks):
        # buat picking
        picking = PK.create({
            'picking_type_id': picking_type.id,
            'location_id': src.id,
            'location_dest_id': dest.id,
            'partner_id': partner.id if partner else False,
            'scheduled_date': datetime.utcnow(),
            'company_id': WH.company_id.id,
            'origin': f'SEED-{label}-{i+1:05d}',
        })

        # ambil jendela produk untuk lines
        chunk = _window(prod_ids, lines_per_pick, i)
        _create_moves_lines(picking, src, dest, chunk, qty_each)

        # selesai
        picking._action_done()
        created += 1

        if created % COMMIT_EVERY_PICKINGS == 0:
            env.cr.commit()
            print(f"  - {label}: {created}/{num_picks} pickings done")

    env.cr.commit()
    print(f"[OK] {label}: {created} pickings selesai.")
    return created

# ============ JALANKAN ============
total_receipts = total_internals = total_deliveries = 0

if MAKE_RECEIPTS:
    total_receipts = _batch_picks(
        picking_type=picking_type_in,
        src=supplier_loc,
        dest=stock_loc,
        partner=vendor,
        num_picks=RECEIPT_NUM_PICKS,
        lines_per_pick=RECEIPT_LINES_PER_PICK,
        qty_each=RECEIPT_QTY_PER_LINE,
        label='RECEIPT',
    )

if MAKE_INTERNALS:
    total_internals = _batch_picks(
        picking_type=picking_type_int,
        src=stock_loc,
        dest=internal2,
        partner=False,
        num_picks=INTERNAL_NUM_PICKS,
        lines_per_pick=INTERNAL_LINES_PER_PICK,
        qty_each=INTERNAL_QTY_PER_LINE,
        label='INTERNAL',
    )

if MAKE_DELIVERIES:
    total_deliveries = _batch_picks(
        picking_type=picking_type_out,
        src=stock_loc,
        dest=customer_loc,
        partner=customer,
        num_picks=DELIVERY_NUM_PICKS,
        lines_per_pick=DELIVERY_LINES_PER_PICK,
        qty_each=DELIVERY_QTY_PER_LINE,
        label='DELIVERY',
    )

print("===================================================")
print(f"[SEED MOVES DONE]")
print(f"  - Receipts : {total_receipts} pickings")
print(f"  - Internals: {total_internals} pickings")
print(f"  - Deliveries: {total_deliveries} pickings")
print("Cek di: Inventory → Operations → Transfers (hapus filter).")
print("===================================================")
