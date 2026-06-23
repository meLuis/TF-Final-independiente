"""Etapa 4 - Optimizacion de compras: baselines + min-cost flow.

Sin argumentos corre un caso demo con datos reales donde la capacidad global
de un proveedor es vinculante (el baseline por-SKU resulta infactible).
Para un pedido propio:

    py etapa4_optimizacion_compras.py --item 5615=2000 --item 5070=1500
"""

from pathlib import Path
import argparse
import json

from core.optimization_baseline import cheapest_split, greedy_time
from core.optimization_flow import compare_with_baseline
from core.purchase_options import build_supply_options


BASE_DIR = Path(__file__).parent
STAGE1_OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_datos"
SUPPLIERS_CSV = BASE_DIR / "data" / "base" / "proveedores.csv"
OUTPUT_DIR = BASE_DIR / "outputs" / "stage4_optimizacion"


def demo_order(options) -> dict[str, float]:
    """Pedido demo: SKUs del proveedor con mas catalogo cuya capacidad global
    es menor que la suma de sus ofertas (competencia real por capacidad)."""
    agg = options.groupby("supplier_norm").agg(
        total_offer=("capacity_units", "sum"),
        supplier_capacity=("supplier_capacity", "first"),
        n_products=("product_id", "nunique"),
    )
    binding = agg.loc[(agg["total_offer"] > agg["supplier_capacity"]) & (agg["n_products"] >= 2)]
    supplier_norm = binding.sort_values("n_products", ascending=False).index[0]
    rows = options.loc[options["supplier_norm"] == supplier_norm].sort_values(
        "capacity_units", ascending=False
    )
    return {
        str(row.product_id): float(row.capacity_units)
        for row in rows.head(4).itertuples()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimizacion de compras (Etapa 4).")
    parser.add_argument("--item", action="append", default=[], help="SKU=cantidad (repetible)")
    parser.add_argument("--stage1", default=str(STAGE1_OUTPUT_DIR))
    parser.add_argument("--suppliers", default=str(SUPPLIERS_CSV))
    parser.add_argument("--output", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    options = build_supply_options(args.stage1, args.suppliers)
    print(f"Opciones SKU-proveedor inferidas del historial: {len(options)}")

    if args.item:
        order = {}
        for item in args.item:
            sku, _, qty = item.partition("=")
            order[sku.strip()] = float(qty or 0)
    else:
        order = demo_order(options)
        print("Pedido demo (capacidad de proveedor vinculante):")
    print(json.dumps(order, indent=2))

    result = compare_with_baseline(options, order)
    per_sku_detail = {
        sku: {
            "cheapest_split": cheapest_split(options, sku, qty),
            "greedy_time": greedy_time(options, sku, qty),
        }
        for sku, qty in order.items()
    }

    flow = result["min_cost_flow"]
    base = result["baseline_per_sku"]
    print("\n--- Comparativa (antes vs ahora) ---")
    print(f"Baseline por-SKU : costo S/{base['total_cost']} | sin cubrir {base['units_unfilled']}")
    print(f"  factible: {result['baseline_is_feasible']}")
    if result["baseline_capacity_violations"]:
        print("  violaciones de capacidad:")
        for supplier, info in result["baseline_capacity_violations"].items():
            print(f"  - {supplier}: asigna {info['assigned']} > capacidad {info['capacity']}")
    print(f"Min-cost flow    : costo S/{flow['total_cost']} | sin cubrir {flow['units_unfilled']}")
    print(f"  caminos aumentantes: {flow['augmenting_paths']}")
    print("  plan:")
    for line in flow["plan"]:
        print(f"  - {line['from']} -> {line['to']}: {line['units']} u x S/{line['unit_cost']} = S/{line['subtotal']}")

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "optimization_comparison.json").write_text(
        json.dumps({"comparison": result, "per_sku_detail": per_sku_detail}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    options.to_csv(output_path / "supply_options.csv", index=False, encoding="utf-8-sig")
    print(f"\nOutputs en: {output_path}")


if __name__ == "__main__":
    main()
