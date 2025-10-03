# Hangry Odoo Developer Test Assignment

## 1. Reproduce the Issue

### Environment Setup
- **Odoo Version**: 18.0  
- **PostgreSQL**: 15  
- **Seed Data**:
  - Product Template = 40,000  
  - Variants = 40,000  
  - Stock Moves = 1,000  
  - Stock.Warehouse.Orderpoint = 40,000  

### Description
When I populate `product.template` I got bottleneck in `odoo.cli._populate` method, so I created a Python script to populate `product.template`.  
The code will be attached in the repo (see `seed_product.py`).  
Then I created stock moves with another Python script (`seed_move.py`).

In `stock.warehouse.orderpoint` there is a field called **trigger**.  

- When I first populated `stock.warehouse.orderpoint`, it had no problem because the value was set to **auto**.  
- Then I updated it from `auto` to **manual** (via query).  
- After that, the view became very slow.

### Steps to Reproduce
1. Login to Odoo  
2. Go to **Inventory → Operation → Replenishment**  
3. Make sure trigger is set to **manual**  
4. Wait until loading page is done  

### Observation
- With trigger = **auto** → view load time ~ **2–4 seconds**  
- With trigger = **manual** → view load time ~ **>20 seconds**
